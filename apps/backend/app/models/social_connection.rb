# frozen_string_literal: true

class SocialConnection < ApplicationRecord
  PROVIDERS = %w[instagram facebook twitter spotify].freeze

  belongs_to :user

  encrypts :access_token
  encrypts :refresh_token

  validates :provider, inclusion: { in: PROVIDERS }
  validates :provider, uniqueness: { scope: :user_id }

  scope :for, ->(provider) { where(provider: provider) }

  after_create_commit  :bump_avatar_counter
  after_destroy_commit :decrement_avatar_counter

  def active?
    expires_at.nil? || expires_at > Time.current
  end

  def expired?
    !active?
  end

  private

  def bump_avatar_counter
    return unless user&.avatar
    user.avatar.class.increment_counter(:social_connections_count, user.avatar.id)
  end

  def decrement_avatar_counter
    return unless user&.avatar
    user.avatar.class.decrement_counter(:social_connections_count, user.avatar.id)
  end
end
