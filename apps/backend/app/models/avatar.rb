# frozen_string_literal: true

# 1:1 per-user avatar metadata + unbounded learning counters.
#
# `knowledge_level` is now a **derived** 1-10 view of the raw counters —
# never stored, never caps hard. `stage` is a bracketed label for the UI.
# Counter caches are bumped by after_create_commit hooks on Message +
# SocialConnection; insights_count is synced nightly from FastAPI by
# SyncAvatarCountersJob.
class Avatar < ApplicationRecord
  belongs_to :user

  STAGES = %w[awakening apprentice attuned kindred mirror].freeze

  # ── Derived read models ──────────────────────────────────────────────
  # Log-scaled, multiplier chosen so:
  #   modest user   (≈36 signal  =  10 insights + 5 msgs + 1 day)        → 3
  #   active user   (≈315 signal =  50 insights + 100 msgs + 30 days)    → 6
  #   power user    (≈3050      =  500 insights + 1000 msgs + 300 days)  → 8
  #   mastered      (≥30000)                                             → 10
  # Signal keeps climbing even past 10; the cap is purely cosmetic.
  def knowledge_level
    (Math.log10(raw_knowledge_signal + 1) * 2.5).floor.clamp(1, 10)
  end

  def stage
    case knowledge_level
    when 1..2 then "awakening"
    when 3..4 then "apprentice"
    when 5..6 then "attuned"
    when 7..8 then "kindred"
    else           "mirror"
    end
  end

  # Mobile + admin panels read this instead of the legacy bounded int.
  def raw_knowledge
    {
      insights_count:            insights_count,
      conversations_count:       conversations_count,
      messages_count:            messages_count,
      social_connections_count:  social_connections_count,
      days_active:               days_active,
      last_interaction_at:       last_interaction_at&.iso8601
    }
  end

  # Called by the counter-cache hooks. Also updates last_interaction_at
  # and increments days_active when the interaction crosses a date boundary.
  def register_interaction!
    now = Time.current
    prev = last_interaction_at
    updates = { last_interaction_at: now }
    if prev.nil? || prev.to_date != now.to_date
      updates[:days_active] = days_active + 1
    end
    update!(updates)
  end

  private

  # Weighted signal across dimensions so no single counter dominates.
  # Insights (real AI-extracted facts) count 3x a message.
  def raw_knowledge_signal
    (insights_count * 3) +
      messages_count +
      (conversations_count * 2) +
      (social_connections_count * 5) +
      days_active
  end
end
