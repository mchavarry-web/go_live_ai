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
#
# Logging: every leg of the trip emits an [audio-job] line with chunk_id,
# session_id, and a hop label (start / quota / transcribe / insights / done /
# fail). Pair with [audio-chunk] (controller) and [audio-up] (frontend) and
# audio.transcribe / audio.insights (FastAPI) for a full grep-able trail.
class AudioChunkProcessJob < ApplicationJob
  queue_as :default

  MAX_ATTEMPTS = 5
  retry_on StandardError, wait: :polynomially_longer, attempts: MAX_ATTEMPTS

  def perform(chunk_id:)
    chunk = AudioChunk.find_by(id: chunk_id)
    unless chunk
      Rails.logger.warn("[audio-job] start: chunk not found chunk=#{chunk_id}")
      return
    end

    if chunk.transcription_status.in?(%w[done failed skipped_quota])
      Rails.logger.info("[audio-job] skip already-terminal chunk=#{chunk_id} status=#{chunk.transcription_status}")
      return
    end

    user    = chunk.user
    session = chunk.audio_session
    Rails.logger.info(
      "[audio-job] start chunk=#{chunk.id} session=#{session.id} user=#{user.id} " \
      "seq=#{chunk.sequence_number} duration=#{chunk.duration_seconds} " \
      "bytes=#{chunk.audio&.size} mime=#{chunk.audio&.mime_type.inspect} attempt=#{chunk.transcription_attempts + 1}"
    )

    unless AudioQuota.allow_chunk_seconds?(user, seconds: chunk.duration_seconds)
      Rails.logger.info("[audio-job] quota exceeded chunk=#{chunk.id} user=#{user.id} → skipped_quota")
      chunk.update!(transcription_status: "skipped_quota")
      check_session_done(session)
      return
    end

    chunk.update!(
      transcription_status: "running",
      transcription_attempts: chunk.transcription_attempts + 1
    )

    started_at  = monotonic_ms
    transcription = call_transcribe(chunk, user)
    transcribe_ms = monotonic_ms - started_at

    text     = transcription.is_a?(Hash) ? transcription["text"].to_s : ""
    segments = transcription.is_a?(Hash) ? Array(transcription["segments"]) : []
    language = transcription.is_a?(Hash) ? transcription["language"] : nil
    model    = transcription.is_a?(Hash) ? transcription["model"]    : nil

    Rails.logger.info(
      "[audio-job] transcribe done chunk=#{chunk.id} took=#{transcribe_ms.to_i}ms " \
      "chars=#{text.length} segments=#{segments.size} lang=#{language.inspect} model=#{model.inspect}"
    )

    if text.strip.empty?
      Rails.logger.warn(
        "[audio-job] transcribe empty chunk=#{chunk.id} took=#{transcribe_ms.to_i}ms " \
        "raw_response_keys=#{transcription.is_a?(Hash) ? transcription.keys.inspect : transcription.class.name}"
      )
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

    Rails.logger.info(
      "[audio-job] complete chunk=#{chunk.id} session=#{session.id} status=done " \
      "total_took=#{(monotonic_ms - started_at).to_i}ms"
    )

    check_session_done(session)
  rescue HTTParty::Error, Timeout::Error => e
    Rails.logger.warn(
      "[audio-job] transport error chunk=#{chunk_id} #{e.class}: #{e.message} (will retry)"
    )
    raise
  rescue StandardError => e
    Rails.logger.error(
      "[audio-job] failed chunk=#{chunk_id} #{e.class}: #{e.message}\n" \
      "#{e.backtrace&.first(5)&.join("\n")}"
    )
    mark_failed(chunk, "#{e.class}: #{e.message}") if chunk
    check_session_done(session) if session
    raise
  end

  private

  def call_transcribe(chunk, user)
    lang = chunk.language.presence || (user.country == "pe" ? "es" : nil)
    Rails.logger.info(
      "[audio-job] transcribe → FastAPI chunk=#{chunk.id} user=#{user.id} " \
      "bytes=#{chunk.audio&.size} mime=#{chunk.audio&.mime_type.inspect} lang=#{lang.inspect}"
    )
    chunk.audio.open do |io|
      AiAgentsClient.new.transcribe_chunk(
        user_id:  user.id,
        audio_io: io,
        language: lang
      )
    end
  end

  def extract_insights(chunk, text)
    started_at = monotonic_ms
    Rails.logger.info(
      "[audio-job] insights → FastAPI chunk=#{chunk.id} user=#{chunk.user.id} " \
      "transcript_chars=#{text.length} source=audio:#{chunk.audio_session_id}"
    )
    response = AiAgentsClient.new.extract_audio_insights(
      user_id:    chunk.user.id,
      transcript: text,
      source:     "audio:#{chunk.audio_session_id}",
      context:    "Audio session chunk ##{chunk.sequence_number}"
    )
    stored = response.is_a?(Hash) ? response["stored"] : nil
    Rails.logger.info(
      "[audio-job] insights done chunk=#{chunk.id} took=#{(monotonic_ms - started_at).to_i}ms stored=#{stored.inspect}"
    )
  rescue StandardError => e
    Rails.logger.warn(
      "[audio-job] insights failed chunk=#{chunk.id} #{e.class}: #{e.message} " \
      "(transcript persisted; insight pass swallowed)"
    )
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
    if pending_or_running
      Rails.logger.info(
        "[audio-job] session=#{session.id} still has pending/running chunks → skip finalize"
      )
      return
    end
    unless session.status.in?(%w[finalizing processing])
      Rails.logger.info(
        "[audio-job] session=#{session.id} status=#{session.status} not in finalize-eligible state → skip"
      )
      return
    end
    Rails.logger.info("[audio-job] session=#{session.id} → AudioSessionFinalizeJob enqueued")
    AudioSessionFinalizeJob.perform_later(session_id: session.id)
  end

  def monotonic_ms
    Process.clock_gettime(Process::CLOCK_MONOTONIC) * 1000.0
  end
end
