# frozen_string_literal: true

# The Avatar is a 1:1 record on User. There is no "list" or "show by id" —
# every request is implicitly the current user's avatar.
#
#   GET   /api/v1/avatar  → { avatar: { ... } }
#   PATCH /api/v1/avatar  → { avatar: { ... } }
#
# `appearance` and `behavior` are jsonb columns and accept arbitrary keys;
# we deep-merge so partial updates don't wipe other fields. `name` is plain.
class Api::V1::AvatarsController < Api::V1::BaseController
  # Mirrors FastAPI's InsightCategory enum (apps/ai-agents/app/models/enums.py).
  # Unknown categories are dropped so FastAPI falls back to its default.
  TEACH_CATEGORIES = %w[
    personal_history preference relationship goal emotion health
    avatar_evolution language_style
  ].freeze

  before_action :load_avatar

  def show
    render_success(avatar: serialize(@avatar))
  end

  def update
    merged_appearance = (@avatar.appearance || {}).deep_merge(appearance_param)
    merged_behavior   = (@avatar.behavior   || {}).deep_merge(behavior_param)

    attrs = {
      name:       params[:name].presence || @avatar.name,
      appearance: merged_appearance,
      behavior:   merged_behavior
    }
    # active_mode is optional; only validate / set when the caller sends one.
    # Inclusion validation in Avatar::MODES handles invalid values via 422.
    attrs[:active_mode] = params[:active_mode] if params.key?(:active_mode)

    @avatar.assign_attributes(attrs)

    if @avatar.save
      render_success(avatar: serialize(@avatar))
    else
      render_error(@avatar.errors.full_messages.join(", "), :unprocessable_entity)
    end
  end

  # ── Memory / insights ────────────────────────────────────────────────
  # GET /api/v1/avatar/insights  → list everything FastAPI knows about the user
  def insights
    response = AiAgentsClient.new.list_insights(current_user.id.to_s) || {}
    render_success(
      total_insights:  response["total_insights"] || 0,
      knowledge_level: response["knowledge_level"] || 1,
      insights:        response["insights"] || []
    )
  end

  # DELETE /api/v1/avatar/insights/:id → drop a single memory
  def delete_insight
    ok = AiAgentsClient.new.delete_insight(
      user_id: current_user.id.to_s,
      insight_id: params[:id]
    )
    if ok
      render_success(deleted: true)
    else
      render_error("Could not delete memory", :unprocessable_entity)
    end
  end

  # DELETE /api/v1/avatar/insights → GDPR wipe; resets the avatar's knowledge
  def delete_all_insights
    ok = AiAgentsClient.new.delete_all_insights(current_user.id.to_s)
    @avatar.update_columns(insights_count: 0) if ok
    render_success(deleted: ok)
  end

  # POST /api/v1/avatar/teach  → manual fact, no chat reply triggered.
  # Synchronous direct storage (DEV-93/DEV-94): the insight is embedded and
  # active before we answer, so success here means "retrievable now".
  def teach
    text = params[:message].to_s.strip
    return render_error("Message required", :unprocessable_entity) if text.empty?

    category = params[:category].to_s.presence
    category = nil unless TEACH_CATEGORIES.include?(category)

    insight = AiAgentsClient.new.teach(
      user_id: current_user.id.to_s,
      message: text,
      category: category
    )

    if insight.is_a?(Hash) && insight["id"].present?
      # Bump the Rails-side counter immediately so UIs don't show a stale
      # zero until the nightly SyncAvatarCountersJob reconciles.
      Avatar.increment_counter(:insights_count, @avatar.id)
      render_success(
        {
          message: "Enseñanza guardada",
          insight: insight.slice("id", "category", "content", "confidence", "source", "created_at")
        },
        :created
      )
    else
      render_error("No se pudo guardar la enseñanza. Intenta de nuevo.", :bad_gateway)
    end
  end

  private

  def load_avatar
    @avatar = current_user.avatar || current_user.create_avatar!(name: current_user.first_name.presence || "Avatar")
  end

  def appearance_param
    h = params[:appearance]
    h.respond_to?(:to_unsafe_h) ? h.to_unsafe_h.transform_keys(&:to_s) : (h || {}).to_h.transform_keys(&:to_s)
  end

  def behavior_param
    h = params[:behavior]
    h.respond_to?(:to_unsafe_h) ? h.to_unsafe_h.transform_keys(&:to_s) : (h || {}).to_h.transform_keys(&:to_s)
  end

  def serialize(avatar)
    {
      id:              avatar.id,
      name:            avatar.name,
      knowledge_level: avatar.knowledge_level,
      stage:           avatar.stage,
      appearance:      avatar.appearance || {},
      behavior:        avatar.behavior   || {},
      active_mode:           avatar.active_mode,
      mode_message_counts:   avatar.mode_message_counts || {},
      insights_count:           avatar.insights_count,
      messages_count:           avatar.messages_count,
      conversations_count:      avatar.conversations_count,
      social_connections_count: avatar.social_connections_count,
    }
  end
end
