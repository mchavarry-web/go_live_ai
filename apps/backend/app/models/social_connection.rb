# frozen_string_literal: true

class SocialConnection < ApplicationRecord
  PROVIDERS = %w[instagram facebook twitter spotify].freeze

  belongs_to :user

  encrypts :access_token
  encrypts :refresh_token

  validates :provider, inclusion: { in: PROVIDERS }
  validates :provider, uniqueness: { scope: :user_id }

  scope :for, ->(provider) { where(provider: provider) }

  def active?
    expires_at.nil? || expires_at > Time.current
  end

  def expired?
    !active?
  end
end
