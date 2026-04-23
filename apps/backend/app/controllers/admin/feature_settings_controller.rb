# Admin toggles for global feature flags. Today scoped to proactive.*
# skills; generalises to any flag key.
class Admin::FeatureSettingsController < Admin::AdminController
  def index
    authorize! :manage, :all
    skill_ids = Proactive::SkillRegistry.default.skill_ids
    keys      = skill_ids.map { |id| "proactive.#{id}" }
    rows      = FeatureSetting.where(key: keys).index_by(&:key)
    @features = skill_ids.map do |id|
      key = "proactive.#{id}"
      row = rows[key]
      {
        id:      id,
        key:     key,
        skill:   Proactive::SkillRegistry.default.find(id),
        enabled: row.nil? || row.enabled?,
        row:     row
      }
    end
  end

  def update
    authorize! :manage, :all
    key     = params.require(:key)
    enabled = ActiveModel::Type::Boolean.new.cast(params.require(:enabled))

    row = FeatureSetting.find_or_initialize_by(key: key)
    row.enabled = enabled
    row.save!
    redirect_to admin_feature_settings_path,
                notice: "#{key} → #{enabled ? 'habilitado' : 'deshabilitado'}"
  end
end
