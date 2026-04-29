# frozen_string_literal: true

# Idempotent chunk upload. The offline-safe client queue may retry the
# same (session, sequence_number) — we resolve the duplicate explicitly
# rather than relying on the unique-index 500.
class Api::V1::AudioChunksController < Api::V1::BaseController
  def create
    session = current_user.audio_sessions.find(params[:session_id])
    return render_error("session not active", :unprocessable_entity) unless session.active?

    seq = params[:sequence_number].to_i
    existing = session.audio_chunks.find_by(sequence_number: seq)

    if existing
      # (a) Re-upload before processing started: replace the audio.
      # (b) Re-upload after processing started: return what we have, do NOT overwrite.
      if existing.transcription_status == "pending" && params[:audio].present?
        existing.audio = params[:audio]
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
      audio:            params[:audio]
    )
    chunk.save!
    session.update!(total_duration_seconds: session.total_duration_seconds + chunk.duration_seconds.to_i) if chunk.duration_seconds.to_i > 0
    AudioChunkProcessJob.perform_later(chunk_id: chunk.id)

    render_success({ chunk: chunk_payload(chunk) }, :accepted)
  rescue ActiveRecord::RecordNotFound
    render_error("session not found", :not_found)
  rescue ActiveRecord::RecordInvalid => e
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
