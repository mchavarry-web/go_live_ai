# Hourly maintenance job:
#   • Sessions stuck in `recording` for >24h → `abandoned` (phone died,
#     app force-killed, lost-network forever scenarios).
#   • Sessions stuck in `processing` for >6h → re-enqueue any pending /
#     running chunks once, then finalize so the session resolves.
#
# Wired into config/schedule.rb (whenever).
class AudioSessionCleanupJob < ApplicationJob
  queue_as :default

  STALE_RECORDING_AFTER  = 24.hours
  STALE_PROCESSING_AFTER = 6.hours

  def perform
    abandon_stale_recordings
    rescue_stuck_processing
  end

  private

  def abandon_stale_recordings
    AudioSession.where(status: "recording")
                .where("started_at < ?", STALE_RECORDING_AFTER.ago)
                .find_each do |session|
      Rails.logger.info("AudioSession abandoned: id=#{session.id} started_at=#{session.started_at}")
      session.update!(status: "abandoned", ended_at: session.ended_at || Time.current)
    end
  end

  def rescue_stuck_processing
    AudioSession.where(status: %w[finalizing processing])
                .where("updated_at < ?", STALE_PROCESSING_AFTER.ago)
                .find_each do |session|
      stuck = session.audio_chunks.where(transcription_status: %w[pending running])
      if stuck.any?
        stuck.find_each { |chunk| AudioChunkProcessJob.perform_later(chunk_id: chunk.id) }
        session.touch
      else
        AudioSessionFinalizeJob.perform_later(session_id: session.id)
      end
    end
  end
end
