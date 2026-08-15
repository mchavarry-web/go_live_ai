# frozen_string_literal: true

require "test_helper"
require_relative "../support/audio_test_helpers"

class AudioQuotaTest < ActiveSupport::TestCase
  include AudioTestHelpers
  include ActiveSupport::Testing::TimeHelpers

  setup do
    @user = create_user!
  end

  # ── snapshot ──────────────────────────────────────────────────────────

  test "snapshot with no usage row: zero used, full cap remaining, allowed" do
    with_audio_quota_cap(100) do
      snap = AudioQuota.snapshot(@user)
      assert snap.allowed
      assert_equal 0,   snap.used_seconds
      assert_equal 100, snap.daily_cap_seconds
      assert_equal 100, snap.remaining_seconds
    end
  end

  test "snapshot reflects today's usage" do
    with_audio_quota_cap(100) do
      AudioUsage.create!(user: @user, usage_date: Date.current, transcribed_seconds: 40)
      snap = AudioQuota.snapshot(@user)
      assert snap.allowed
      assert_equal 40, snap.used_seconds
      assert_equal 60, snap.remaining_seconds
    end
  end

  test "snapshot at cap is not allowed" do
    with_audio_quota_cap(100) do
      AudioUsage.create!(user: @user, usage_date: Date.current, transcribed_seconds: 100)
      refute AudioQuota.snapshot(@user).allowed
      assert_equal 0, AudioQuota.snapshot(@user).remaining_seconds
    end
  end

  test "snapshot over cap clamps remaining to zero" do
    with_audio_quota_cap(100) do
      AudioUsage.create!(user: @user, usage_date: Date.current, transcribed_seconds: 150)
      snap = AudioQuota.snapshot(@user)
      refute snap.allowed
      assert_equal 150, snap.used_seconds
      assert_equal 0,   snap.remaining_seconds
    end
  end

  test "snapshot ignores usage from other days" do
    with_audio_quota_cap(100) do
      AudioUsage.create!(user: @user, usage_date: Date.current - 1, transcribed_seconds: 100)
      assert AudioQuota.snapshot(@user).allowed
      assert_equal 0, AudioQuota.snapshot(@user).used_seconds
    end
  end

  test "to_h_safe exposes only the client-safe keys" do
    snap = AudioQuota.snapshot(@user)
    assert_equal %i[used_seconds daily_cap_seconds remaining_seconds], snap.to_h_safe.keys
  end

  # ── allow_session_start? ──────────────────────────────────────────────

  test "allow_session_start? true below cap, false at cap" do
    with_audio_quota_cap(100) do
      assert AudioQuota.allow_session_start?(@user)
      AudioUsage.create!(user: @user, usage_date: Date.current, transcribed_seconds: 99)
      assert AudioQuota.allow_session_start?(@user)
      AudioUsage.find_by(user: @user, usage_date: Date.current).update!(transcribed_seconds: 100)
      refute AudioQuota.allow_session_start?(@user)
    end
  end

  # ── allow_chunk_seconds? ──────────────────────────────────────────────

  test "allow_chunk_seconds? always true for zero or negative durations" do
    with_audio_quota_cap(100) do
      AudioUsage.create!(user: @user, usage_date: Date.current, transcribed_seconds: 100)
      assert AudioQuota.allow_chunk_seconds?(@user, seconds: 0)
      assert AudioQuota.allow_chunk_seconds?(@user, seconds: -5)
      assert AudioQuota.allow_chunk_seconds?(@user, seconds: nil)
    end
  end

  test "allow_chunk_seconds? false once cap is reached" do
    with_audio_quota_cap(100) do
      AudioUsage.create!(user: @user, usage_date: Date.current, transcribed_seconds: 100)
      refute AudioQuota.allow_chunk_seconds?(@user, seconds: 1)
    end
  end

  test "allow_chunk_seconds? grants half-length grace at the boundary" do
    with_audio_quota_cap(100) do
      AudioUsage.create!(user: @user, usage_date: Date.current, transcribed_seconds: 90)
      # used + seconds/2 <= cap → 90 + 10 = 100 → allowed
      assert AudioQuota.allow_chunk_seconds?(@user, seconds: 20)
      # 90 + 11 = 101 > 100 → refused
      refute AudioQuota.allow_chunk_seconds?(@user, seconds: 22)
    end
  end

  # ── record! ───────────────────────────────────────────────────────────

  test "record! creates the daily row on first call" do
    AudioQuota.record!(@user, seconds: 30)
    usage = AudioUsage.find_by!(user: @user, usage_date: Date.current)
    assert_equal 30, usage.transcribed_seconds
    assert_equal 1,  usage.uploaded_chunks
  end

  test "record! twice accumulates into the same row" do
    AudioQuota.record!(@user, seconds: 30)
    AudioQuota.record!(@user, seconds: 45)
    assert_equal 1, AudioUsage.where(user: @user).count
    usage = AudioUsage.find_by!(user: @user, usage_date: Date.current)
    assert_equal 75, usage.transcribed_seconds
    assert_equal 2,  usage.uploaded_chunks
  end

  test "record! is a no-op for non-positive seconds" do
    AudioQuota.record!(@user, seconds: 0)
    AudioQuota.record!(@user, seconds: -10)
    assert_equal 0, AudioUsage.where(user: @user).count
  end

  test "recording pushes the user over the session-start gate" do
    with_audio_quota_cap(60) do
      assert AudioQuota.allow_session_start?(@user)
      AudioQuota.record!(@user, seconds: 60)
      refute AudioQuota.allow_session_start?(@user)
    end
  end

  # ── timezone handling ─────────────────────────────────────────────────

  test "local_today_for uses the user's timezone" do
    lima_user = create_user!(timezone: "America/Lima") # UTC-5
    utc_user  = create_user!(timezone: "UTC")
    travel_to Time.utc(2026, 8, 15, 3, 0) do
      assert_equal Date.new(2026, 8, 15), AudioQuota.local_today_for(utc_user)
      assert_equal Date.new(2026, 8, 14), AudioQuota.local_today_for(lima_user)
    end
  end

  test "local_today_for falls back to UTC for nil or bogus timezones" do
    no_tz  = create_user!(timezone: nil)
    bad_tz = create_user!(timezone: "Not/AZone")
    travel_to Time.utc(2026, 8, 15, 3, 0) do
      assert_equal Date.new(2026, 8, 15), AudioQuota.local_today_for(no_tz)
      assert_equal Date.new(2026, 8, 15), AudioQuota.local_today_for(bad_tz)
    end
  end

  test "record! books usage against the user-local date" do
    lima_user = create_user!(timezone: "America/Lima")
    travel_to Time.utc(2026, 8, 15, 3, 0) do
      AudioQuota.record!(lima_user, seconds: 10)
      assert AudioUsage.exists?(user: lima_user, usage_date: Date.new(2026, 8, 14))
    end
  end
end
