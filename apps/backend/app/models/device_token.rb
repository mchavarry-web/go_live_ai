# frozen_string_literal: true

class DeviceToken < ApplicationRecord
  PLATFORMS = %w[ios android web].freeze

  belongs_to :user

  validates :token,    presence: true, uniqueness: true
  validates :platform, inclusion: { in: PLATFORMS }

  scope :active, -> { where(active: true) }

  def deactivate!
    update!(active: false)
  end
end
