# frozen_string_literal: true

# Runs the proactive-greeting pipeline for exactly one user. Extracted from
# ProactivePushJob so Sidekiq can parallelise per-user work and one slow
# FastAPI call doesn't stall the batch.
class ProactiveGreetingForUserJob < ApplicationJob
  queue_as :default

  def perform(user_id:, time_window: nil)
    user = User.find(user_id)
    tz   = user.timezone.presence || "America/Lima"
    now  = Time.current.in_time_zone(tz)

    registry = Proactive::SkillRegistry.default
    enabled  = Proactive::SkillRegistry.enabled_skill_ids_for(user, registry.skill_ids)
    return if enabled.empty?

    ctx = Proactive::SkillRegistry::SelectionContext.new(
      local_time:      now.strftime("%H:%M"),
      local_date:      now.strftime("%Y-%m-%d"),
      absence_minutes: absence_minutes(user),
      has_location:    user.last_latitude.present?,
      last_skill_id:   user.last_proactive_skill.to_s,
      timezone:        tz
    )

    skill = begin
              registry.select(ctx, enabled_skill_ids: enabled)
            rescue Proactive::SkillRegistry::NoEligibleSkillsError
              nil
            end
    return unless skill

    response = AiAgentsClient.new.generate_proactive(build_payload(user, skill, ctx))
    content  = (response.is_a?(Hash) && response["response"].to_s).presence
    return unless content

    conv = ensure_conversation_for(user)
    msg  = conv.messages.create!(
      role: "assistant",
      content: content,
      proactive_skill: skill.id,
      metadata: { generated_by: "proactive_push_job", skill_id: skill.id, time_window: time_window }
    )

    user.update!(last_proactive_skill: skill.id, last_proactive_at: Time.current)

    user.device_tokens.active.find_each do |dt|
      PushNotificationJob.perform_later(
        device_token_id: dt.id,
        title: skill.name,
        body:  content.truncate(140),
        data:  { kind: "proactive", skill: skill.id, conversation_id: conv.id, message_id: msg.id }
      )
    end
  end

  private

  def absence_minutes(user)
    return 30 if user.last_proactive_at.nil?
    ((Time.current - user.last_proactive_at) / 60).to_i
  end

  def ensure_conversation_for(user)
    user.conversations.recent.first || user.conversations.create!(title: "Conversación con mi avatar")
  end

  def build_payload(user, skill, ctx)
    {
      user_id:         user.id.to_s,
      conversation_id: ensure_conversation_for(user).id,
      user_profile: {
        display_name:    user.name,
        avatar_name:     user.avatar&.name.presence || "Avatar",
        country:         user.country,
        knowledge_level: [((user.avatar&.knowledge_level || 1) + 1) / 2, 5].min,
        interests:       []
      }.compact,
      skill_id:        skill.id,
      skill_context:   { has_location: ctx.has_location,
                         latitude:     user.last_latitude,
                         longitude:    user.last_longitude }.compact,
      local_time:      ctx.local_time,
      local_date:      ctx.local_date,
      absence_minutes: ctx.absence_minutes,
      conversation_history: []
    }
  end
end
