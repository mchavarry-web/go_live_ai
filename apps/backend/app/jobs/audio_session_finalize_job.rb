# Resolves the terminal status of a session once every chunk has finished
# processing. Decides between ready / ready_with_errors / failed and writes
# a per-session outcome summary into metadata.
class AudioSessionFinalizeJob < ApplicationJob
  queue_as :default

  def perform(session_id:)
    session = AudioSession.find_by(id: session_id)
    return unless session
    return if session.terminal?

    session.finalize_outcome!
    Rails.logger.info("AudioSession finalized: id=#{session.id} status=#{session.status}")
  end
end
