# Daily quota rollup. Source of truth for the 480-min/user/day cap.
# Updated only after a chunk's transcription succeeds, so failed jobs
# don't burn quota.
class AudioUsage < ApplicationRecord
  belongs_to :user

  # `usage_date` is the date in the user's local timezone, not UTC, so a
  # session that crosses midnight in the user's TZ rolls over correctly.
  def self.upsert_seconds!(user:, seconds:, date: Date.current)
    return if seconds.to_i <= 0
    record = find_or_create_by!(user: user, usage_date: date)
    record.with_lock do
      record.transcribed_seconds += seconds.to_i
      record.uploaded_chunks     += 1
      record.save!
    end
    record
  end
end
