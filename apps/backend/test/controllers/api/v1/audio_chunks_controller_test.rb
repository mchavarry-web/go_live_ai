# frozen_string_literal: true

require "test_helper"
require_relative "../../../support/audio_test_helpers"

class Api::V1::AudioChunksControllerTest < ActionDispatch::IntegrationTest
  include ActiveJob::TestHelper
  include AudioTestHelpers

  setup do
    @user    = create_user!
    @session = create_recording_session!(@user)
    @path    = "/api/v1/audio/sessions/#{@session.id}/chunks"
  end

  def upload_chunk(seq: 0, key: "idem-key-1", duration: 120.5, file: wav_upload, headers: {})
    post @path,
         params:  { sequence_number: seq, duration_seconds: duration, started_at: Time.current.iso8601, audio: file },
         headers: auth_headers(@user).merge("Idempotency-Key" => key).merge(headers)
  end

  test "requires a JWT" do
    post @path, params: { sequence_number: 0 }
    assert_response :unauthorized
  end

  test "create persists the chunk, stores the audio, and enqueues processing" do
    assert_difference("AudioChunk.count", 1) do
      upload_chunk(seq: 0, key: "idem-key-1")
    end
    assert_response :accepted

    chunk = @session.audio_chunks.sole
    assert_equal 0, chunk.sequence_number
    assert_equal "pending", chunk.transcription_status
    assert_equal "idem-key-1", chunk.idempotency_key
    assert_equal 120.5, chunk.duration_seconds
    assert chunk.audio.present?, "audio file should be attached"
    assert_equal File.size(wav_fixture_path), chunk.audio.size
    assert_equal 120, @session.reload.total_duration_seconds

    assert_enqueued_with(job: AudioChunkProcessJob, args: [{ chunk_id: chunk.id }])
  end

  test "retrying the same Idempotency-Key and sequence creates only one chunk" do
    upload_chunk(seq: 0, key: "idem-key-1")
    assert_response :accepted
    first_id = @session.audio_chunks.sole.id

    assert_no_difference("AudioChunk.count") do
      upload_chunk(seq: 0, key: "idem-key-1")
    end
    assert_response :ok # duplicate resolves to the existing chunk, not a new 202
    assert_equal first_id, JSON.parse(response.body).dig("chunk", "id")
    assert_equal 1, @session.audio_chunks.count
  end

  test "different keys and sequences create separate chunks" do
    upload_chunk(seq: 0, key: "idem-key-1")
    upload_chunk(seq: 1, key: "idem-key-2")
    assert_equal 2, @session.audio_chunks.count
    assert_equal [0, 1], @session.audio_chunks.order(:sequence_number).pluck(:sequence_number)
  end

  test "duplicate upload while still pending replaces the audio and re-enqueues" do
    upload_chunk(seq: 0, key: "idem-key-1")
    chunk = @session.audio_chunks.sole

    assert_enqueued_with(job: AudioChunkProcessJob, args: [{ chunk_id: chunk.id }]) do
      upload_chunk(seq: 0, key: "idem-key-retry")
    end
    assert_response :ok
    assert_equal 1, @session.audio_chunks.count
    assert_equal "idem-key-retry", chunk.reload.idempotency_key
  end

  test "duplicate upload after processing started returns state without overwriting" do
    upload_chunk(seq: 0, key: "idem-key-1")
    chunk = @session.audio_chunks.sole
    chunk.update!(transcription_status: "running")
    original_audio_data = chunk.audio_data

    assert_no_enqueued_jobs(only: AudioChunkProcessJob) do
      upload_chunk(seq: 0, key: "idem-key-2")
    end
    assert_response :ok
    body = JSON.parse(response.body)
    assert_equal "running", body.dig("chunk", "transcription_status")
    chunk.reload
    assert_equal original_audio_data, chunk.audio_data, "audio must not be replaced mid-processing"
    assert_equal "idem-key-1", chunk.idempotency_key
  end

  test "upload to an inactive session → 422" do
    @session.update!(status: "cancelled")
    assert_no_difference("AudioChunk.count") do
      upload_chunk(seq: 0)
    end
    assert_response :unprocessable_entity
    assert JSON.parse(response.body).key?("error")
  end

  test "upload to another user's session → 404" do
    other_session = create_recording_session!(create_user!)
    post "/api/v1/audio/sessions/#{other_session.id}/chunks",
         params:  { sequence_number: 0, audio: wav_upload },
         headers: auth_headers(@user)
    assert_response :not_found
  end

  test "non-audio file is rejected with 422" do
    txt = Rack::Test::UploadedFile.new(
      Rails.root.join("test/fixtures/files/not_audio.txt"), "text/plain"
    )
    assert_no_difference("AudioChunk.count") do
      upload_chunk(seq: 0, file: txt)
    end
    assert_response :unprocessable_entity
    assert JSON.parse(response.body).key?("error")
  end
end
