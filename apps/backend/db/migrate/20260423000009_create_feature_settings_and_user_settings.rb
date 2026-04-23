# Two-layer gating for proactive skills (and future feature flags):
#   feature_settings  — global, admin-controlled, keyed by string id
#   user_feature_settings — per-user opt-outs (a row exists only when the
#                            user explicitly changes the default)
class CreateFeatureSettingsAndUserSettings < ActiveRecord::Migration[8.1]
  def change
    create_table :feature_settings, id: :uuid do |t|
      t.string  :key,     null: false           # e.g. "proactive.weather"
      t.boolean :enabled, null: false, default: true
      t.jsonb   :metadata, null: false, default: {}
      t.timestamps
    end
    add_index :feature_settings, :key, unique: true

    create_table :user_feature_settings, id: :uuid do |t|
      t.references :user, null: false, foreign_key: true, type: :bigint, index: true
      t.string  :key,     null: false
      t.boolean :enabled, null: false, default: true
      t.timestamps
    end
    add_index :user_feature_settings, %i[user_id key], unique: true
  end
end
