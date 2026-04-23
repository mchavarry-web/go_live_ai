# frozen_string_literal: true

# Source encryption keys from ENV so we can ship them via Kamal secrets in
# prod and .env in dev. These values must be stable — rotating any of them
# breaks existing ciphertext in social_connections. See
# `bin/rails db:encryption:init` to (re-)generate.
Rails.application.configure do
  if ENV["ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY"].present?
    config.active_record.encryption.primary_key          = ENV["ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY"]
    config.active_record.encryption.deterministic_key    = ENV["ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY"]
    config.active_record.encryption.key_derivation_salt  = ENV["ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT"]
  end
end
