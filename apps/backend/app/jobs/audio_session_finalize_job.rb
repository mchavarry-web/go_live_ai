# Resolves the terminal status of a session once every chunk has finished
# processing. Decides between ready / ready_with_errors / failed and writes
# a per-session outcome summary into metadata.
class AudioSessionFinalizeJob < ApplicationJob
  queue_as :low

  def perform(session_id:)
    session = AudioSession.find_by(id: session_id)
    unless session
      Rails.logger.warn("[audio-finalize] session not found session=#{session_id}")
      return
    end
    if session.terminal?
      Rails.logger.info("[audio-finalize] already terminal session=#{session.id} status=#{session.status}")
      return
    end

    counts = session.audio_chunks.reorder(nil).group(:transcription_status).count
    Rails.logger.info(
      "[audio-finalize] start session=#{session.id} prior_status=#{session.status} chunks=#{counts.inspect}"
    )

    session.finalize_outcome!

    Rails.logger.info(
      "[audio-finalize] done session=#{session.id} new_status=#{session.status} " \
      "chunks=#{counts.inspect} total_duration=#{session.total_duration_seconds}s"
    )
  end
end
