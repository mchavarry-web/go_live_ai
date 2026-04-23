# frozen_string_literal: true

# Builds a proactive-greeting context, picks a skill via the registry,
# forwards it to FastAPI's /internal/chat/proactive-generate, persists the
# response as an assistant Message (with proactive_skill stamped), and
# records the last_proactive_skill / last_proactive_at on the User for
# anti-repetition.
#
#   POST /api/v1/chat/proactive-greeting
#        {
#          local_time: "08:15", local_date: "2026-04-23",
#          absence_minutes: 45,
#          latitude: -12.04, longitude: -77.03
#        }
#
# Returns { message, conversation_id, skill }.
class Api::V1::ProactiveGreetingsController < Api::V1::BaseController
  def create
    ctx = build_context
    registry = Proactive::SkillRegistry.default
    enabled  = Proactive::SkillRegistry.enabled_skill_ids_for(current_user, registry.skill_ids)
    skill    = registry.select(ctx, enabled_skill_ids: enabled)

    # Persist the user's reported location if we got GPS coords; they feed
    # future dialect + skill-context decisions.
    update_location_if_given!

    conversation = ensure_conversation_for_proactive
    response = AiAgentsClient.new.generate_proactive(build_payload(conversation, skill))

    content = response.is_a?(Hash) ? response["response"].to_s : ""
    assistant = conversation.messages.create!(
      role: "assistant",
      content: content.presence || "👋 ¡Hola!",
      proactive_skill: skill.id,
      metadata: { generated_by: "proactive_greeting", skill_id: skill.id }
    )

    current_user.update!(last_proactive_skill: skill.id, last_proactive_at: Time.current)

    render_success(
      conversation_id: conversation.id,
      skill: { id: skill.id, name: skill.name },
      message: message_json(assistant)
    )
  rescue Proactive::SkillRegistry::NoEligibleSkillsError => e
    render_error(e.message, :unprocessable_entity)
  end

  private

  def build_context
    Proactive::SkillRegistry::SelectionContext.new(
      local_time:      params[:local_time].to_s,
      local_date:      params[:local_date].to_s,
      absence_minutes: params[:absence_minutes].to_i,
      has_location:    params[:latitude].present? || current_user.last_latitude.present?,
      last_skill_id:   current_user.last_proactive_skill.to_s,
      timezone:        params[:timezone].to_s.presence || current_user.timezone.to_s
    )
  end

  def update_location_if_given!
    return if params[:latitude].blank? || params[:longitude].blank?
    current_user.update!(last_latitude: params[:latitude].to_f,
                         last_longitude: params[:longitude].to_f)
  end

  # Proactive messages always land in the user's most-recent conversation;
  # create one on the fly if the user is brand new.
  def ensure_conversation_for_proactive
    current_user.conversations.recent.first || current_user.conversations.create!(
      title: "Conversación con mi avatar"
    )
  end

  def build_payload(conversation, skill)
    {
      user_id:         current_user.id.to_s,
      conversation_id: conversation.id,
      user_profile:    user_profile_payload,
      skill_id:        skill.id,
      skill_context:   {
        has_location: params[:latitude].present?,
        latitude:     params[:latitude],
        longitude:    params[:longitude]
      }.compact,
      local_time:      params[:local_time],
      local_date:      params[:local_date],
      absence_minutes: params[:absence_minutes].to_i,
      conversation_history: conversation.history_payload(limit: 10)
    }
  end

  def user_profile_payload
    {
      display_name:    current_user.name,
      avatar_name:     current_user.avatar&.name.presence || "Avatar",
      country:         current_user.country,
      knowledge_level: [((current_user.avatar&.knowledge_level || 1) + 1) / 2, 5].min,
      interests:       []
    }.compact
  end

  def message_json(m)
    {
      id:              m.id,
      role:            m.role,
      content:         m.content,
      proactive_skill: m.proactive_skill,
      metadata:        m.metadata,
      created_at:      m.created_at.iso8601
    }
  end
end
