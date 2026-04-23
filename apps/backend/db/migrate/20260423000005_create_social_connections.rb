# One OAuth connection per (user, provider). access_token + refresh_token
# are encrypted at rest via Rails 8 ActiveRecord encryption (see
# config/initializers/active_record_encryption.rb and the :encrypts calls on
# the SocialConnection model). `metadata` is a free-form jsonb bucket for
# anything provider-specific we want to keep handy without its own column
# (scopes granted, account name, IG business account id, etc.).
class CreateSocialConnections < ActiveRecord::Migration[8.1]
  def change
    create_table :social_connections, id: :uuid do |t|
      t.references :user, null: false, foreign_key: true, type: :bigint, index: true
      t.string   :provider,         null: false    # instagram | facebook | twitter | spotify
      t.string   :external_user_id                  # provider's own ID for this user
      t.text     :access_token                      # encrypted (AR encryption)
      t.text     :refresh_token                     # encrypted (nullable — not all providers issue)
      t.string   :scopes                            # space-separated provider scopes
      t.datetime :expires_at
      t.jsonb    :metadata,         null: false, default: {}
      t.timestamps
    end

    add_index :social_connections, %i[user_id provider], unique: true
  end
end
