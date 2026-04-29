# Transcribe one AudioChunk and feed the result into the insights pipeline.
#
# Flow:
#   1. Quota check via AudioQuota (server-side cap; defaults to 480 min/day).
#      If at-cap, mark chunk skipped_quota and stop — no upstream call.
#   2. Open the Shrine attachment, multipart-stream bytes to FastAPI.
#   3. Persist transcript + segments back onto the chunk (plaintext in v1).
#   4. Tag insight extraction with source="audio:<session_id>".
#   5. Roll up successful seconds into AudioUsage (today's user-local date).
#   6. If every chunk in the session has terminated, kick AudioSessionFinalizeJob.
class AudioChunkProcessJob < ApplicationJob
  queue_as :default

  MAX_ATTEMPTS = 5
  retry_on StandardError, wait: :polynomially_longer, attempts: MAX_ATTEMPTS

  def perform(chunk_id:)
    chunk = AudioChunk.find_by(id: chunk_id)
    return unless chunk
    return if chunk.transcription_status.in?(%w[done failed skipped_quota])

    user    = chunk.user
    session = chunk.audio_session

    unless AudioQuota.allow_chunk_seconds?(user, seconds: chunk.duration_seconds)
      chunk.update!(transcription_status: "skipped_quota")
      check_session_done(session)
      return
    end

    chunk.update!(
      transcription_status: "running",
      transcription_attempts: chunk.transcription_attempts + 1
    )

    transcription = call_transcribe(chunk, user)
    text          = transcription.is_a?(Hash) ? transcription["text"].to_s : ""
    segments      = transcription.is_a?(Hash) ? Array(transcription["segments"]) : []
    language      = transcription.is_a?(Hash) ? transcription["language"] : nil

    if text.strip.empty?
      mark_failed(chunk, "empty transcription response")
      check_session_done(session)
      return
    end

    chunk.update!(
      transcript: text,
      segments:   segments,
      language:   language || chunk.language,
      transcription_status: "done"
    )

    AudioQuota.record!(user, seconds: chunk.duration_seconds.to_i)

    extract_insights(chunk, text)
    Avatar.where(user_id: user.id).first&.tap { |a| a.update!(insights_count: a.insights_count.to_i + 1) }

    check_session_done(session)
  rescue HTTParty::Error, Timeout::Error => e
    Rails.logger.warn("AudioChunkProcessJob transport error chunk=#{chunk_id}: #{e.class}: #{e.message}")
    raise
  rescue StandardError => e
    Rails.logger.error("AudioChunkProcessJob failed chunk=#{chunk_id}: #{e.class}: #{e.message}")
    mark_failed(chunk, e.message) if chunk
    check_session_done(session) if session
    raise
  end

  private

  def call_transcribe(chunk, user)
    chunk.audio.open do |io|
      AiAgentsClient.new.transcribe_chunk(
        user_id:  user.id,
        audio_io: io,
        language: chunk.language.presence || (user.country == "pe" ? "es" : nil)
      )
    end
  end

  def extract_insights(chunk, text)
    AiAgentsClient.new.extract_audio_insights(
      user_id:    chunk.user.id,
      transcript: text,
      source:     "audio:#{chunk.audio_session_id}",
      context:    "Audio session chunk ##{chunk.sequence_number}"
    )
  rescue StandardError => e
    Rails.logger.warn("Audio insight extraction failed chunk=#{chunk.id}: #{e.class}: #{e.message}")
    # don't re-raise — transcript is already persisted; insights can be
    # re-derived later via a maintenance task.
  end

  def mark_failed(chunk, reason)
    return unless chunk
    chunk.update!(
      transcription_status: "failed",
      metadata: chunk.metadata.merge("last_error" => reason)
    )
  end

  def check_session_done(session)
    return unless session
    pending_or_running = session.audio_chunks.where(transcription_status: %w[pending running]).exists?
    return if pending_or_running
    return unless session.status.in?(%w[finalizing processing])
    AudioSessionFinalizeJob.perform_later(session_id: session.id)
  end
end
