# frozen_string_literal: true

# Global feature flag keyed by a dotted string id (e.g. "proactive.news").
# Admins toggle these in /admin/feature_settings; a missing row is treated
# as enabled=true by default so adding a new flag doesn't auto-disable it.
class FeatureSetting < ApplicationRecord
  validates :key, presence: true, uniqueness: true

  # Returns true unless an explicitly-disabled row exists.
  def self.enabled?(key)
    row = find_by(key: key)
    row.nil? || row.enabled?
  end

  # Bulk lookup for the registry — returns the set of keys that are
  # **not** disabled globally (missing keys count as enabled).
  def self.enabled_keys(candidate_keys)
    disabled = where(key: candidate_keys, enabled: false).pluck(:key).to_set
    candidate_keys.reject { |k| disabled.include?(k) }
  end
end
