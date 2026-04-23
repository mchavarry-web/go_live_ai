# frozen_string_literal: true

class Conversation < ApplicationRecord
  belongs_to :user
  has_many   :messages, -> { order(created_at: :asc) }, dependent: :destroy

  before_validation :set_last_active_at, on: :create
  validates :last_active_at, presence: true

  scope :recent, -> { order(last_active_at: :desc) }

  # Used to build `conversation_history` for FastAPI ChatGenerateRequest.
  # Oldest→newest, role/content only, capped to avoid prompt bloat.
  def history_payload(limit: 30)
    messages.order(created_at: :desc).limit(limit).reverse_each.map do |m|
      { "role" => m.role, "content" => m.content }
    end
  end

  def touch_activity!
    update!(last_active_at: Time.current)
  end

  private

  def set_last_active_at
    self.last_active_at ||= Time.current
  end
end
