# Adds go-live-specific columns to the users table.
# Replaces what the old Django api-back kept on UserProfile (country, timezone,
# proactive tracking, formality_level, location). Inlined onto User because the
# relationship is strictly 1:1.
class AddGoLiveFieldsToUsers < ActiveRecord::Migration[8.1]
  def change
    change_table :users do |t|
      t.string   :country,             limit: 2           # ISO 3166-1 alpha-2 (e.g. "PE")
      t.string   :timezone                                 # IANA (e.g. "America/Lima")
      t.float    :last_latitude
      t.float    :last_longitude
      t.string   :last_proactive_skill
      t.datetime :last_proactive_at
      t.string   :formality_level                          # "formal" | "neutral" | "informal"
      t.datetime :onboarding_completed_at
      t.string   :provider                                 # "email" | "google" | "apple" | "facebook"
      t.string   :provider_uid
    end

    add_index :users, %i[provider provider_uid], unique: true, where: "provider_uid IS NOT NULL"
  end
end
