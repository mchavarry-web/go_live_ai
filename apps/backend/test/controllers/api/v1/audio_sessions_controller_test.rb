# frozen_string_literal: true

require "test_helper"
require_relative "../../../support/audio_test_helpers"

class Api::V1::AudioSessionsControllerTest < ActionDispatch::IntegrationTest
  include ActiveJob::TestHelper
  include AudioTestHelpers

  setup do
    @user = create_user!
    @fake = FakeAiAgentsClient.new
  end

  test "endpoints require a JWT" do
    post "/api/v1/audio/sessions"
    assert_response :unauthorized

    post "/api/v1/audio/wipe"
    assert_response :unauthorized
  end

  # ── create ────────────────────────────────────────────────────────────

  test "create requires a ready voice enrollment (428)" do
    post "/api/v1/audio/sessions", headers: auth_headers(@user)
    assert_response :precondition_required
    assert JSON.parse(response.body).key?("error")
    assert_equal 0, @user.audio_sessions.count
  end

  test "create refuses with 429 and a quota snapshot when at cap" do
    enroll_voice!(@user)
    with_audio_quota_cap(100) do
      AudioUsage.create!(user: @user, usage_date: Date.current, transcribed_seconds: 100)
      post "/api/v1/audio/sessions", headers: auth_headers(@user)
      assert_response :too_many_requests
      body = JSON.parse(response.body)
      assert body.key?("error")
      assert_equal 100, body.dig("quota", "used_seconds")
      assert_equal 0,   body.dig("quota", "remaining_seconds")
      assert_equal 0, @user.audio_sessions.count
    end
  end

  test "create starts a recording session with the quota snapshot" do
    enroll_voice!(@user)
    post "/api/v1/audio/sessions", headers: auth_headers(@user)
    assert_response :created
    body = JSON.parse(response.body)
    session = @user.audio_sessions.find(body.dig("session", "id"))
    assert_equal "recording", session.status
    assert body.dig("session", "quota").key?("remaining_seconds")
  end

  # ── finish / cancel ───────────────────────────────────────────────────

  test "finish moves a recording session to processing and enqueues finalize when idle" do
    session = create_recording_session!(@user)
    assert_enqueued_with(job: AudioSessionFinalizeJob, args: [{ session_id: session.id }]) do
      post "/api/v1/audio/sessions/#{session.id}/finish", headers: auth_headers(@user)
    end
    assert_response :success
    session.reload
    assert_equal "processing", session.status
    assert_not_nil session.ended_at
  end

  test "finish does not enqueue finalize while chunks are still pending" do
    session = create_recording_session!(@user)
    create_chunk!(session, sequence_number: 0, status: "pending")
    assert_no_enqueued_jobs(only: AudioSessionFinalizeJob) do
      post "/api/v1/audio/sessions/#{session.id}/finish", headers: auth_headers(@user)
    end
    assert_response :success
    assert_equal "processing", session.reload.status
  end

  test "finish on an already-terminal session → 422" do
    session = create_recording_session!(@user)
    session.update!(status: "ready")
    post "/api/v1/audio/sessions/#{session.id}/finish", headers: auth_headers(@user)
    assert_response :unprocessable_entity
  end

  test "cancel cancels an active session" do
    session = create_recording_session!(@user)
    create_chunk!(session, sequence_number: 0, status: "pending")
    post "/api/v1/audio/sessions/#{session.id}/cancel", headers: auth_headers(@user)
    assert_response :success
    assert_equal "cancelled", session.reload.status
    assert_equal 0, session.audio_chunks.count
  end

  test "sessions are scoped to the current user" do
    other = create_user!
    session = create_recording_session!(other)
    post "/api/v1/audio/sessions/#{session.id}/cancel", headers: auth_headers(@user)
    assert_response :not_found
    assert_equal "recording", session.reload.status
  end

  # ── wipe_all ──────────────────────────────────────────────────────────

  test "wipe destroys every session and chunk and clears audio insights" do
    s1 = create_recording_session!(@user)
    s2 = create_recording_session!(@user)
    create_chunk!(s1, sequence_number: 0)
    create_chunk!(s2, sequence_number: 0)
    other = create_user!
    keep  = create_recording_session!(other)

    stub_ai_client(@fake) do
      post "/api/v1/audio/wipe", headers: auth_headers(@user)
    end

    assert_response :success
    assert_equal 2, JSON.parse(response.body).dig("deleted", "sessions")
    assert_equal 0, @user.audio_sessions.count
    assert_equal 0, AudioChunk.joins(:audio_session).where(audio_sessions: { user_id: @user.id }).count
    assert AudioSession.exists?(keep.id), "other users' sessions must survive a wipe"

    call = @fake.calls_for(:delete_insights_by_source).first
    assert call, "expected the audio insights to be wiped in FastAPI"
    assert_equal "audio", call[:args][:source]
    assert_equal true,    call[:args][:prefix]
  end

  # ── destroy ───────────────────────────────────────────────────────────

  test "destroy deletes one session and its FastAPI insights by exact source" do
    session = create_recording_session!(@user)
    create_chunk!(session, sequence_number: 0)

    stub_ai_client(@fake) do
      delete "/api/v1/audio/sessions/#{session.id}", headers: auth_headers(@user)
    end

    assert_response :success
    refute AudioSession.exists?(session.id)
    call = @fake.calls_for(:delete_insights_by_source).first
    assert_equal "audio:#{session.id}", call[:args][:source]
    assert_equal false, call[:args][:prefix]
  end
end
