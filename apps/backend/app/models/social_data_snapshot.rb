# frozen_string_literal: true

# Phase 16 — immutable archive row for one social-platform fetch.
#
# Written by FetchSocialDataJob right before SocialConnection.metadata
# is overwritten with the new raw_data. Bounded retention: keep the
# latest RETENTION_PER_USER_PLATFORM rows per (user, platform); older
# rows are evicted on the same write path so we never need a cron sweep.
class SocialDataSnapshot < ApplicationRecord
  RETENTION_PER_USER_PLATFORM = 12

  belongs_to :user

  validates :platform,           presence: true, length: { maximum: 50 }
  validates :fetched_at,         presence: true
  validates :raw_data,           presence: true
  validates :byte_size,          numericality: { greater_than_or_equal_to: 0 }
  validates :extraction_version, numericality: { greater_than: 0 }

  scope :for_user_platform, ->(user, platform) {
    where(user: user, platform: platform).order(fetched_at: :desc)
  }

  # Persist the snapshot and prune older rows in one transaction.
  def self.archive!(user:, platform:, raw_data:, fetched_at: Time.current, extraction_version: 1)
    transaction do
      json = raw_data.is_a?(String) ? raw_data : raw_data.to_json
      snapshot = create!(
        user:               user,
        platform:           platform.to_s,
        fetched_at:         fetched_at,
        raw_data:           raw_data,
        byte_size:          json.bytesize,
        extraction_version: extraction_version
      )
      keepers = for_user_platform(user, platform).limit(RETENTION_PER_USER_PLATFORM).pluck(:id)
      where(user: user, platform: platform.to_s)
        .where.not(id: keepers)
        .delete_all
      snapshot
    end
  end
end
