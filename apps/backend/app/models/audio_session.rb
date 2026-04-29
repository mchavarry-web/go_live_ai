# A continuous user-initiated audio capture session. The session owns
# many AudioChunks; cascade destroy walks Shrine attachments via the
# chunk model's destroy callback.
#
# Status state-machine:
#   recording   ── finish ──▶ finalizing ──▶ processing ──▶ ready
#                                                       └─▶ ready_with_errors
#                                                       └─▶ failed
#   recording   ── cancel ──▶ cancelled
#   recording   ── cleanup ─▶ abandoned   (> 24h stale)
#   ready/*     ── delete ──▶ deleted    (soft-flag; row is destroyed too)
class AudioSession < ApplicationRecord
  STATUSES = %w[
    recording finalizing processing ready ready_with_errors
    cancelled failed abandoned deleted
  ].freeze
  ACTIVE_STATUSES   = %w[recording finalizing processing].freeze
  TERMINAL_STATUSES = %w[ready ready_with_errors cancelled failed abandoned deleted].freeze

  belongs_to :user
  has_many :audio_chunks, -> { order(:sequence_number) }, dependent: :destroy

  validates :status, inclusion: { in: STATUSES }

  scope :recent, -> { order(started_at: :desc) }
  scope :active, -> { where(status: ACTIVE_STATUSES) }

  def active?
    ACTIVE_STATUSES.include?(status)
  end

  def terminal?
    TERMINAL_STATUSES.include?(status)
  end

  # User-triggered abort while still recording. Pending chunks are dropped;
  # already-transcribed ones stay so the user can review what they said.
  def cancel!
    return false unless active?
    transaction do
      update!(status: "cancelled", ended_at: ended_at || Time.current)
      audio_chunks.where(transcription_status: "pending").destroy_all
    end
    true
  end

  # Mark the session as ready_with_errors / failed depending on chunk results.
  # Called by AudioSessionFinalizeJob once every chunk has terminated.
  def finalize_outcome!
    # Strip the has_many's default ``order(:sequence_number)`` — Postgres
    # rejects an ORDER BY on a column that isn't in the GROUP BY clause.
    counts = audio_chunks.reorder(nil).group(:transcription_status).count
    done   = counts["done"].to_i
    failed = counts["failed"].to_i
    skipped = counts["skipped_quota"].to_i
    total  = counts.values.sum

    new_status =
      if total.zero?
        "failed"
      elsif failed.zero? && skipped.zero?
        "ready"
      elsif done.zero?
        "failed"
      else
        "ready_with_errors"
      end

    update!(
      status: new_status,
      metadata: metadata.merge(
        "outcome" => { "done" => done, "failed" => failed, "skipped_quota" => skipped, "total" => total }
      )
    )
  end
end
