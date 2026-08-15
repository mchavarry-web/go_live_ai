# frozen_string_literal: true

require "test_helper"
require_relative "../support/audio_test_helpers"

class AudioChunkProcessJobTest < ActiveJob::TestCase
  include AudioTestHelpers

  setup do
    @user    = create_user!
    @session = create_recording_session!(@user)
  end

  def perform_with(fake, chunk)
    stub_ai_client(fake) do
      AudioChunkProcessJob.perform_now(chunk_id: chunk.id)
    end
  end

  # ── success path ──────────────────────────────────────────────────────

  test "success: persists transcript, records quota, extracts insights" do
    chunk = attach_wav!(create_chunk!(@session, sequence_number: 0, duration: 120.0))
    fake  = FakeAiAgentsClient.new(
      transcription: {
        "text"     => "hola, esto es una prueba",
        "segments" => [{ "start" => 0.0, "end" => 2.0, "text" => "hola" }],
        "language" => "es",
        "model"    => "test-model"
      }
    )

    perform_with(fake, chunk)

    chunk.reload
    assert_equal "done", chunk.transcription_status
    assert_equal "hola, esto es una prueba", chunk.transcript
    assert_equal 1, chunk.segments.size
    assert_equal "es", chunk.language
    assert_equal 1, chunk.transcription_attempts

    usage = AudioUsage.find_by!(user: @user, usage_date: Date.current)
    assert_equal 120, usage.transcribed_seconds

    extract = fake.calls_for(:extract_audio_insights).first
    assert extract, "insight extraction should be invoked after transcription"
    assert_equal "audio:#{@session.id}", extract[:args][:source]
    assert_equal chunk.id, extract[:args][:audio_chunk_id]

    assert_equal 1, @user.avatar.reload.insights_count
  end

  test "success on a processing session with all chunks terminal enqueues finalize" do
    @session.update!(status: "processing")
    chunk = attach_wav!(create_chunk!(@session, sequence_number: 0, duration: 60.0))
    fake  = FakeAiAgentsClient.new(transcription: { "text" => "listo" })

    assert_enqueued_with(job: AudioSessionFinalizeJob, args: [{ session_id: @session.id }]) do
      perform_with(fake, chunk)
    end
  end

  test "success while session still recording does not finalize" do
    chunk = attach_wav!(create_chunk!(@session, sequence_number: 0, duration: 60.0))
    assert_no_enqueued_jobs(only: AudioSessionFinalizeJob) do
      perform_with(FakeAiAgentsClient.new(transcription: { "text" => "listo" }), chunk)
    end
  end

  test "insight-extraction failure is swallowed; transcript survives" do
    chunk = attach_wav!(create_chunk!(@session, sequence_number: 0, duration: 60.0))
    fake  = FakeAiAgentsClient.new(transcription: { "text" => "texto util" })
    def fake.extract_audio_insights(**) = raise(StandardError, "insights down")

    perform_with(fake, chunk)

    chunk.reload
    assert_equal "done", chunk.transcription_status
    assert_equal "texto util", chunk.transcript
    assert_equal 60, AudioUsage.find_by!(user: @user, usage_date: Date.current).transcribed_seconds
  end

  # ── quota path ────────────────────────────────────────────────────────

  test "quota exceeded: chunk skipped, transcription never called" do
    with_audio_quota_cap(100) do
      AudioUsage.create!(user: @user, usage_date: Date.current, transcribed_seconds: 100)
      chunk = create_chunk!(@session, sequence_number: 0, duration: 120.0) # no audio needed — quota gate is first
      fake  = FakeAiAgentsClient.new

      perform_with(fake, chunk)

      assert_equal "skipped_quota", chunk.reload.transcription_status
      refute fake.called?(:transcribe_chunk), "must not stream bytes upstream when at cap"
      assert_equal 100, AudioUsage.find_by!(user: @user, usage_date: Date.current).transcribed_seconds
    end
  end

  # ── failure paths ─────────────────────────────────────────────────────

  test "nil transcription response marks the chunk failed with a reason" do
    chunk = attach_wav!(create_chunk!(@session, sequence_number: 0, duration: 60.0))
    fake  = FakeAiAgentsClient.new(transcription: nil)

    perform_with(fake, chunk)

    chunk.reload
    assert_equal "failed", chunk.transcription_status
    assert chunk.metadata["last_error"].present?
    assert_nil chunk.transcript
    assert_nil AudioUsage.find_by(user: @user, usage_date: Date.current), "failed chunks must not burn quota"
  end

  test "blank transcription text marks the chunk failed" do
    chunk = attach_wav!(create_chunk!(@session, sequence_number: 0, duration: 60.0))
    perform_with(FakeAiAgentsClient.new(transcription: { "text" => "   " }), chunk)
    assert_equal "failed", chunk.reload.transcription_status
  end

  test "nil transcription on a processing session still triggers finalize" do
    @session.update!(status: "processing")
    chunk = attach_wav!(create_chunk!(@session, sequence_number: 0, duration: 60.0))
    assert_enqueued_with(job: AudioSessionFinalizeJob, args: [{ session_id: @session.id }]) do
      perform_with(FakeAiAgentsClient.new(transcription: nil), chunk)
    end
  end

  test "transcription raising marks the chunk failed and schedules a retry" do
    chunk = attach_wav!(create_chunk!(@session, sequence_number: 0, duration: 60.0))
    fake  = FakeAiAgentsClient.new(transcription: RuntimeError.new("boom"))

    # retry_on StandardError captures the re-raise and re-enqueues the job
    assert_enqueued_with(job: AudioChunkProcessJob, args: [{ chunk_id: chunk.id }]) do
      perform_with(fake, chunk)
    end

    chunk.reload
    assert_equal "failed", chunk.transcription_status
    assert_includes chunk.metadata["last_error"].to_s, "boom"
  end

  # ── guard clauses ─────────────────────────────────────────────────────

  test "already-terminal chunk is left untouched" do
    chunk = create_chunk!(@session, sequence_number: 0, status: "done", transcript: "ya está")
    fake  = FakeAiAgentsClient.new(transcription: RuntimeError.new("should never be called"))

    perform_with(fake, chunk)

    chunk.reload
    assert_equal "done", chunk.transcription_status
    assert_equal "ya está", chunk.transcript
    assert_empty fake.calls
  end

  test "missing chunk id is a quiet no-op" do
    assert_nothing_raised do
      AudioChunkProcessJob.perform_now(chunk_id: SecureRandom.uuid)
    end
  end
end
