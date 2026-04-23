# frozen_string_literal: true

class Message < ApplicationRecord
  ROLES = %w[user assistant system].freeze

  belongs_to :conversation
  has_one :user, through: :conversation

  validates :role,    inclusion: { in: ROLES }
  validates :content, presence: true, length: { maximum: 10_000 }

  after_create_commit :bump_conversation_activity

  scope :assistant, -> { where(role: "assistant") }
  scope :user_msgs, -> { where(role: "user") }

  private

  def bump_conversation_activity
    conversation.touch_activity!
  end
end
