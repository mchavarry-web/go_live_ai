# frozen_string_literal: true

# Per-user feature-flag toggles. Currently gates the proactive skill
# catalog; generalises to any future flag keyed "proactive.<skill>" or
# any other namespace.
#
#   GET  /api/v1/settings/features         → { features: [{key, enabled, globally_enabled}] }
#   POST /api/v1/settings/features         → { key, enabled }
class Api::V1::FeatureSettingsController < Api::V1::BaseController
  def index
    skills = Proactive::SkillRegistry.default.skill_ids
    keys   = skills.map { |id| "proactive.#{id}" }
    global_disabled = FeatureSetting.where(key: keys, enabled: false).pluck(:key).to_set
    user_rows       = current_user.user_feature_settings.where(key: keys).index_by(&:key)

    features = keys.map do |key|
      globally_enabled = !global_disabled.include?(key)
      user_row = user_rows[key]
      user_opted_in = user_row.nil? || user_row.enabled?
      {
        key: key,
        enabled: globally_enabled && user_opted_in,
        globally_enabled: globally_enabled,
        user_opted_in: user_opted_in
      }
    end
    render_success(features: features)
  end

  def update
    key     = params.require(:key)
    enabled = ActiveModel::Type::Boolean.new.cast(params.require(:enabled))

    row = current_user.user_feature_settings.find_or_initialize_by(key: key)
    row.enabled = enabled
    row.save!

    render_success(key: key, enabled: enabled)
  rescue ActionController::ParameterMissing => e
    render_error(e.message, :unprocessable_entity)
  end
end
