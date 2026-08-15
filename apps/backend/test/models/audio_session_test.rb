# frozen_string_literal: true

require "test_helper"
require_relative "../support/audio_test_helpers"

class AudioSessionTest < ActiveSupport::TestCase
  include AudioTestHelpers

  setup do
    @user    = create_user!
    @session = create_recording_session!(@user)
  end

  test "status must be one of the known states" do
    @session.status = "recording"
    assert @session.valid?
    @session.status = "warp-speed"
    refute @session.valid?
  end

  test "active? and terminal? partition the state machine" do
    AudioSession::ACTIVE_STATUSES.each do |s|
      @session.status = s
      assert @session.active?,  "#{s} should be active"
      refute @session.terminal?, "#{s} should not be terminal"
    end
    AudioSession::TERMINAL_STATUSES.each do |s|
      @session.status = s
      refute @session.active?,  "#{s} should not be active"
      assert @session.terminal?, "#{s} should be terminal"
    end
  end

  # ── cancel! ───────────────────────────────────────────────────────────

  test "cancel! moves an active session to cancelled and stamps ended_at" do
    assert_nil @session.ended_at
    assert @session.cancel!
    @session.reload
    assert_equal "cancelled", @session.status
    assert_not_nil @session.ended_at
  end

  test "cancel! drops pending chunks but keeps transcribed ones" do
    pending = create_chunk!(@session, sequence_number: 0, status: "pending")
    done    = create_chunk!(@session, sequence_number: 1, status: "done")
    assert @session.cancel!
    refute AudioChunk.exists?(pending.id)
    assert AudioChunk.exists?(done.id)
  end

  test "cancel! preserves an existing ended_at" do
    stamp = 2.hours.ago.change(usec: 0)
    @session.update!(ended_at: stamp)
    @session.cancel!
    assert_equal stamp, @session.reload.ended_at
  end

  test "cancel! refuses on a terminal session" do
    @session.update!(status: "ready")
    refute @session.cancel!
    assert_equal "ready", @session.reload.status
  end

  # ── finalize_outcome! ─────────────────────────────────────────────────

  test "finalize_outcome! with no chunks → failed" do
    @session.update!(status: "processing")
    @session.finalize_outcome!
    assert_equal "failed", @session.reload.status
    assert_equal 0, @session.metadata.dig("outcome", "total")
  end

  test "finalize_outcome! all chunks done → ready" do
    create_chunk!(@session, sequence_number: 0, status: "done")
    create_chunk!(@session, sequence_number: 1, status: "done")
    @session.finalize_outcome!
    assert_equal "ready", @session.reload.status
    assert_equal({ "done" => 2, "failed" => 0, "skipped_quota" => 0, "total" => 2 },
                 @session.metadata["outcome"])
  end

  test "finalize_outcome! mixed done and failed → ready_with_errors" do
    create_chunk!(@session, sequence_number: 0, status: "done")
    create_chunk!(@session, sequence_number: 1, status: "failed")
    @session.finalize_outcome!
    assert_equal "ready_with_errors", @session.reload.status
  end

  test "finalize_outcome! mixed done and skipped_quota → ready_with_errors" do
    create_chunk!(@session, sequence_number: 0, status: "done")
    create_chunk!(@session, sequence_number: 1, status: "skipped_quota")
    @session.finalize_outcome!
    assert_equal "ready_with_errors", @session.reload.status
  end

  test "finalize_outcome! nothing transcribed → failed" do
    create_chunk!(@session, sequence_number: 0, status: "failed")
    create_chunk!(@session, sequence_number: 1, status: "skipped_quota")
    @session.finalize_outcome!
    assert_equal "failed", @session.reload.status
    assert_equal({ "done" => 0, "failed" => 1, "skipped_quota" => 1, "total" => 2 },
                 @session.metadata["outcome"])
  end

  # ── associations ──────────────────────────────────────────────────────

  test "destroying a session cascades to its chunks" do
    create_chunk!(@session, sequence_number: 0)
    create_chunk!(@session, sequence_number: 1)
    assert_difference("AudioChunk.count", -2) { @session.destroy! }
  end

  test "chunk sequence_number is unique per session" do
    create_chunk!(@session, sequence_number: 0)
    dup = @session.audio_chunks.new(sequence_number: 0, started_at: Time.current)
    refute dup.valid?
  end
end
