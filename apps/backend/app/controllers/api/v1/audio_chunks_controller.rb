# frozen_string_literal: true

# Idempotent chunk upload. The offline-safe client queue may retry the
# same (session, sequence_number) — we resolve the duplicate explicitly
# rather than relying on the unique-index 500.
class Api::V1::AudioChunksController < Api::V1::BaseController
  def create
    seq      = params[:sequence_number].to_i
    audio    = params[:audio]
    file_log = "content_type=#{audio&.content_type.inspect} filename=#{audio&.original_filename.inspect} size=#{audio&.size}"
    Rails.logger.info(
      "[audio-chunk] upload received user=#{current_user&.id} session=#{params[:session_id]} " \
      "seq=#{seq} duration=#{params[:duration_seconds]} #{file_log}"
    )

    session = current_user.audio_sessions.find(params[:session_id])
    unless session.active?
      Rails.logger.warn(
        "[audio-chunk] session not active user=#{current_user.id} session=#{session.id} " \
        "status=#{session.status}"
      )
      return render_error("session not active", :unprocessable_entity)
    end

    existing = session.audio_chunks.find_by(sequence_number: seq)

    if existing
      # (a) Re-upload before processing started: replace the audio.
      # (b) Re-upload after processing started: return what we have, do NOT overwrite.
      Rails.logger.info(
        "[audio-chunk] duplicate seq user=#{current_user.id} session=#{session.id} seq=#{seq} " \
        "chunk=#{existing.id} status=#{existing.transcription_status} replacing=#{(existing.transcription_status == "pending" && audio.present?)}"
      )
      if existing.transcription_status == "pending" && audio.present?
        existing.audio = audio
        existing.idempotency_key = idempotency_key
        existing.save!
        AudioChunkProcessJob.perform_later(chunk_id: existing.id) unless existing.audio_data.blank?
      end
      render_success(chunk: chunk_payload(existing))
      return
    end

    chunk = session.audio_chunks.new(
      sequence_number:  seq,
      started_at:       parse_time(params[:started_at]) || Time.current,
      duration_seconds: params[:duration_seconds]&.to_f,
      transcription_status: "pending",
      idempotency_key:  idempotency_key,
      audio:            audio
    )
    chunk.save!
    session.update!(total_duration_seconds: session.total_duration_seconds + chunk.duration_seconds.to_i) if chunk.duration_seconds.to_i > 0
    AudioChunkProcessJob.perform_later(chunk_id: chunk.id)

    Rails.logger.info(
      "[audio-chunk] persisted chunk=#{chunk.id} user=#{current_user.id} session=#{session.id} " \
      "seq=#{seq} mime=#{chunk.audio&.mime_type.inspect} bytes=#{chunk.audio&.size} " \
      "duration=#{chunk.duration_seconds} → AudioChunkProcessJob enqueued"
    )

    render_success({ chunk: chunk_payload(chunk) }, :accepted)
  rescue ActiveRecord::RecordNotFound
    Rails.logger.warn(
      "[audio-chunk] session not found user=#{current_user&.id} session=#{params[:session_id]}"
    )
    render_error("session not found", :not_found)
  rescue ActiveRecord::RecordInvalid => e
    Rails.logger.warn(
      "[audio-chunk] validation failed user=#{current_user&.id} session=#{params[:session_id]} " \
      "seq=#{seq} #{file_log} errors=#{e.record.errors.full_messages.inspect}"
    )
    render_error(e.record.errors.full_messages.join(", "), :unprocessable_entity)
  end

  private

  def idempotency_key
    request.headers["Idempotency-Key"].presence
  end

  def parse_time(value)
    return nil if value.blank?
    Time.iso8601(value.to_s)
  rescue ArgumentError
    nil
  end

  def chunk_payload(chunk)
    {
      id:                   chunk.id,
      sequence_number:      chunk.sequence_number,
      transcription_status: chunk.transcription_status
    }
  end
end
