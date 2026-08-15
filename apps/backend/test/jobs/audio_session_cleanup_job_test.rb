# frozen_string_literal: true

require "test_helper"
require_relative "../support/audio_test_helpers"

class AudioSessionCleanupJobTest < ActiveJob::TestCase
  include AudioTestHelpers

  setup do
    @user = create_user!
  end

  # ── stale `recording` sessions ────────────────────────────────────────

  test "recording session older than 24h is abandoned with ended_at stamped" do
    stale = @user.audio_sessions.create!(started_at: 25.hours.ago, status: "recording")

    AudioSessionCleanupJob.perform_now

    stale.reload
    assert_equal "abandoned", stale.status
    assert_not_nil stale.ended_at
  end

  test "fresh recording session is untouched" do
    fresh = @user.audio_sessions.create!(started_at: 1.hour.ago, status: "recording")
    AudioSessionCleanupJob.perform_now
    assert_equal "recording", fresh.reload.status
    assert_nil fresh.ended_at
  end

  test "abandonment preserves a pre-existing ended_at" do
    stamp = 30.hours.ago.change(usec: 0)
    stale = @user.audio_sessions.create!(started_at: 31.hours.ago, ended_at: stamp, status: "recording")
    AudioSessionCleanupJob.perform_now
    assert_equal stamp, stale.reload.ended_at
  end

  # ── stuck `processing` sessions ───────────────────────────────────────

  test "stuck processing session with pending chunks re-enqueues them and touches the session" do
    session = @user.audio_sessions.create!(started_at: 10.hours.ago, status: "processing")
    pending = create_chunk!(session, sequence_number: 0, status: "pending")
    done    = create_chunk!(session, sequence_number: 1, status: "done")
    session.update_column(:updated_at, 7.hours.ago)

    assert_enqueued_with(job: AudioChunkProcessJob, args: [{ chunk_id: pending.id }]) do
      assert_no_enqueued_jobs(only: AudioSessionFinalizeJob) do
        AudioSessionCleanupJob.perform_now
      end
    end

    # touched → next hourly run won't double-enqueue until it goes stale again
    assert session.reload.updated_at > 1.minute.ago
    assert_equal "done", done.reload.transcription_status
  end

  test "stuck processing session with all chunks terminal gets finalized" do
    session = @user.audio_sessions.create!(started_at: 10.hours.ago, status: "processing")
    create_chunk!(session, sequence_number: 0, status: "done")
    create_chunk!(session, sequence_number: 1, status: "failed")
    session.update_column(:updated_at, 7.hours.ago)

    assert_enqueued_with(job: AudioSessionFinalizeJob, args: [{ session_id: session.id }]) do
      AudioSessionCleanupJob.perform_now
    end
  end

  test "stuck finalizing session is also rescued" do
    session = @user.audio_sessions.create!(started_at: 10.hours.ago, status: "finalizing")
    session.update_column(:updated_at, 7.hours.ago)

    assert_enqueued_with(job: AudioSessionFinalizeJob, args: [{ session_id: session.id }]) do
      AudioSessionCleanupJob.perform_now
    end
  end

  test "recently-updated processing session is left alone" do
    session = @user.audio_sessions.create!(started_at: 10.hours.ago, status: "processing")
    create_chunk!(session, sequence_number: 0, status: "pending")
    session.update_column(:updated_at, 1.hour.ago)

    assert_no_enqueued_jobs do
      AudioSessionCleanupJob.perform_now
    end
  end

  test "terminal sessions are never resurrected" do
    session = @user.audio_sessions.create!(started_at: 40.hours.ago, status: "cancelled")
    session.update_column(:updated_at, 40.hours.ago)
    AudioSessionCleanupJob.perform_now
    assert_equal "cancelled", session.reload.status
  end
end
