# frozen_string_literal: true

# Wave C.2 (2026-05-06) — per-(user, capability) authorization for the
# autonomous-agent surface. Default-deny: a row absent OR
# `enabled: false` means the avatar may not use that capability.
#
# See docs/autonomous_agent_design.md for the full model.
class AgentPermission < ApplicationRecord
  belongs_to :user

  CAPABILITIES = %w[
    web_search
    read_calendar
    draft_calendar_event
    create_calendar_event
    draft_email
    send_email
    draft_message
    send_message
    create_reminder
    purchase
    post_social
    book_reservation
  ].freeze

  RISK_LEVELS = %w[
    read_only
    draft_only
    low_risk_execute
    external_commitment
    financial
    sensitive
  ].freeze

  validates :capability,    presence: true, inclusion: { in: CAPABILITIES }
  validates :max_risk_level, inclusion: { in: RISK_LEVELS }
  validates :user_id, uniqueness: { scope: :capability }

  scope :enabled,                 -> { where(enabled: true) }
  scope :for_capability,          ->(cap) { where(capability: cap.to_s) }
  scope :requires_approval,       -> { where(approval_required: true) }

  # Convenience predicates used by the agent decision path.
  def requires_approval?
    approval_required
  end

  def writes_allowed?
    enabled && %w[low_risk_execute external_commitment financial sensitive].include?(max_risk_level)
  end

  def in_quiet_hours?(now: Time.current)
    return false if quiet_hours.blank?
    tz_name = quiet_hours["tz"] || "UTC"
    ranges  = quiet_hours["ranges"] || []
    return false if ranges.empty?
    local = now.in_time_zone(tz_name)
    minutes = local.hour * 60 + local.min
    ranges.any? do |range|
      from = parse_minutes(range["from"])
      to   = parse_minutes(range["to"])
      next false if from.nil? || to.nil?
      if from <= to
        from <= minutes && minutes < to
      else
        # Overnight range, e.g. 22:00 → 06:00.
        minutes >= from || minutes < to
      end
    end
  end

  private

  def parse_minutes(s)
    return nil if s.blank?
    h, m = s.to_s.split(":").map(&:to_i)
    return nil if h.nil?
    h * 60 + (m || 0)
  end
end
