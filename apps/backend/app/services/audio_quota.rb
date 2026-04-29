# Server-side daily transcription cap. The decision (default 480 min/user/day)
# is enforced HERE, not in the client; client display is just a cache.
#
# Used in two places:
#   1. AudioSessionsController#create — refuse if user is already at-cap.
#   2. AudioChunkProcessJob — guard before invoking the OpenAI transcription
#      API. If a single chunk would push the user over the cap, the chunk is
#      stored but its transcription_status flips to "skipped_quota" and the
#      bytes are never sent upstream.
class AudioQuota
  DEFAULT_DAILY_SECONDS = 480 * 60   # 480 minutes / 8 hours
  ENV_KEY = "AUDIO_DAILY_QUOTA_SECONDS"

  Result = Struct.new(:allowed, :used_seconds, :daily_cap_seconds, :remaining_seconds, keyword_init: true) do
    def to_h_safe
      { used_seconds: used_seconds, daily_cap_seconds: daily_cap_seconds, remaining_seconds: remaining_seconds }
    end
  end

  def self.daily_cap_seconds
    ENV.fetch(ENV_KEY, DEFAULT_DAILY_SECONDS).to_i
  end

  def self.local_today_for(user)
    tz = ActiveSupport::TimeZone[user.timezone || "UTC"] || ActiveSupport::TimeZone["UTC"]
    Time.current.in_time_zone(tz).to_date
  end

  def self.usage_record_for(user, date: nil)
    AudioUsage.find_or_initialize_by(user: user, usage_date: date || local_today_for(user))
  end

  # Snapshot of where the user stands, no side-effects.
  def self.snapshot(user)
    cap   = daily_cap_seconds
    used  = usage_record_for(user).transcribed_seconds.to_i
    Result.new(
      allowed:           used < cap,
      used_seconds:      used,
      daily_cap_seconds: cap,
      remaining_seconds: [cap - used, 0].max
    )
  end

  # True if the user has any room left at all today (used at session create).
  def self.allow_session_start?(user)
    snapshot(user).allowed
  end

  # True if processing a chunk of `seconds` length would still leave the user
  # at or under the cap. Slight over-budget is acceptable on the last chunk —
  # we don't refuse a chunk that would push the user 30s past the cap, but a
  # 10-min chunk against a 0-second remainder would be skipped.
  def self.allow_chunk_seconds?(user, seconds:)
    return true if seconds.to_i <= 0
    snap = snapshot(user)
    return false unless snap.allowed
    snap.used_seconds + (seconds.to_i / 2) <= snap.daily_cap_seconds
  end

  # Atomic upsert; called only after a successful transcription.
  def self.record!(user, seconds:)
    AudioUsage.upsert_seconds!(user: user, seconds: seconds, date: local_today_for(user))
  end
end
