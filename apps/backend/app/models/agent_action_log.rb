# frozen_string_literal: true

# Wave C.3 (2026-05-06) — append-only audit row for every agent action,
# proposed or executed.
class AgentActionLog < ApplicationRecord
  belongs_to :user

  STATUSES      = %w[proposed approved rejected executed failed rolled_back].freeze
  RISK_LEVELS   = AgentPermission::RISK_LEVELS

  validates :capability,       presence: true, inclusion: { in: AgentPermission::CAPABILITIES }
  validates :requested_action, presence: true
  validates :risk_level,       inclusion: { in: RISK_LEVELS }
  validates :approval_status,  inclusion: { in: STATUSES }

  scope :recent,        -> { order(created_at: :desc) }
  scope :pending,       -> { where(approval_status: "proposed") }
  scope :for_user,      ->(user) { where(user: user) }
  scope :for_conversation, ->(conversation_id) { where(conversation_id: conversation_id) }

  def pending?
    approval_status == "proposed"
  end

  def executed?
    approval_status == "executed"
  end

  # Append-only contract: status flips through validate_state_machine
  # rather than direct attribute writes when we want the row to reflect
  # the lifecycle correctly.
  def transition_to!(next_status, error: nil, executed_at: nil)
    raise ArgumentError, "invalid status #{next_status}" unless STATUSES.include?(next_status.to_s)
    update!(
      approval_status: next_status.to_s,
      status:          next_status.to_s,
      error:           error.presence,
      executed_at:     executed_at
    )
  end
end
