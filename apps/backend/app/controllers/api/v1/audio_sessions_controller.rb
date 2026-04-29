# frozen_string_literal: true

# Lifecycle for an audio recording session: create → finish/cancel → wipe.
# Each session is a chronological container for AudioChunks; chunks are
# uploaded against an existing session's id.
#
# Quota gate runs at #create — a user already at-cap gets a 429 with the
# usage snapshot so the client can show a clear "límite diario alcanzado".
class Api::V1::AudioSessionsController < Api::V1::BaseController
  before_action :load_session, only: %i[show destroy finish cancel]

  def index
    sessions = current_user.audio_sessions.recent.limit(100)
    render_success(sessions: sessions.map { |s| summary(s) })
  end

  def show
    chunks = @session.audio_chunks.order(:sequence_number)
    render_success(
      session: summary(@session).merge(
        chunks: chunks.map { |c| chunk_payload(c) }
      )
    )
  end

  def create
    return unless enforce_enrollment!
    snap = AudioQuota.snapshot(current_user)
    unless snap.allowed
      render json: {
        error: "daily quota exceeded",
        quota: snap.to_h_safe
      }, status: :too_many_requests
      return
    end

    session = current_user.audio_sessions.create!(
      started_at: Time.current,
      status:     "recording",
      metadata:   { language: params[:language] }.compact
    )
    render_success({ session: summary(session).merge(quota: snap.to_h_safe) }, :created)
  end

  def finish
    return render_error("session not active", :unprocessable_entity) unless @session.active?
    @session.update!(status: "processing", ended_at: Time.current)
    AudioSessionFinalizeJob.perform_later(session_id: @session.id) if @session.audio_chunks.where(transcription_status: %w[pending running]).none?
    render_success(session: summary(@session))
  end

  def cancel
    @session.cancel!
    render_success(session: summary(@session))
  end

  def destroy
    AiAgentsClient.new.delete_insights_by_source(
      user_id: current_user.id, source: "audio:#{@session.id}", prefix: false
    ) rescue nil
    @session.destroy!
    render_success(deleted: true)
  end

  # Global wipe — destroys every session + all derived audio insights.
  def wipe_all
    AiAgentsClient.new.delete_insights_by_source(
      user_id: current_user.id, source: "audio", prefix: true
    ) rescue nil
    counts = current_user.audio_sessions.destroy_all
    render_success(deleted: { sessions: counts.size })
  end

  private

  def load_session
    @session = current_user.audio_sessions.find(params[:id])
  rescue ActiveRecord::RecordNotFound
    render_error("session not found", :not_found)
  end

  # Returns true to let the caller continue, or renders 428 + returns
  # false. Plain controller methods don't honour ``throw :abort`` (only
  # callbacks do), so we signal via the return value instead.
  def enforce_enrollment!
    return true if current_user.voice_enrollment&.ready?
    render json: { error: "voice enrollment required" }, status: :precondition_required
    false
  end

  def summary(session)
    {
      id:                      session.id,
      started_at:              session.started_at.iso8601,
      ended_at:                session.ended_at&.iso8601,
      status:                  session.status,
      total_duration_seconds:  session.total_duration_seconds,
      transcribed_seconds:     session.transcribed_seconds,
      chunk_count:             session.audio_chunks.size,
      transcript_preview:      preview_for(session)
    }
  end

  def preview_for(session)
    first = session.audio_chunks.where.not(transcript: [nil, ""]).order(:sequence_number).first
    first&.transcript_preview
  end

  def chunk_payload(chunk)
    {
      id:                   chunk.id,
      sequence_number:      chunk.sequence_number,
      started_at:           chunk.started_at.iso8601,
      duration_seconds:     chunk.duration_seconds,
      transcription_status: chunk.transcription_status,
      transcript:           chunk.transcript,
      segments:             chunk.segments,
      language:             chunk.language
    }
  end
end
