# frozen_string_literal: true

# Per-user override for a feature flag. Default semantics match
# FeatureSetting: a missing row means the user is opted in.
# A row with enabled=false means "this user has explicitly opted out".
class UserFeatureSetting < ApplicationRecord
  belongs_to :user
  validates :key, presence: true, uniqueness: { scope: :user_id }

  def self.enabled_keys_for(user, candidate_keys)
    disabled = where(user: user, key: candidate_keys, enabled: false).pluck(:key).to_set
    candidate_keys.reject { |k| disabled.include?(k) }
  end
end
