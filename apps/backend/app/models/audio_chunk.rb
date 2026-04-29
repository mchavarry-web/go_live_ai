# A single 5-minute slice of an AudioSession. Each chunk is uploaded
# independently from the client, transcribed asynchronously, and stores
# its transcript inline.
#
# transcription_status:
#   pending        → just uploaded, waiting for AudioChunkProcessJob
#   running        → job picked it up, transcription in flight
#   done           → transcript persisted; insights extracted
#   failed         → max retries exhausted
#   skipped_quota  → user hit daily cap; chunk stored but not transcribed
class AudioChunk < ApplicationRecord
  include AudioChunkUploader::Attachment(:audio)

  STATUSES = %w[pending running done failed skipped_quota].freeze

  belongs_to :audio_session

  validates :sequence_number, presence: true, numericality: { only_integer: true, greater_than_or_equal_to: 0 }
  validates :sequence_number, uniqueness: { scope: :audio_session_id }
  validates :transcription_status, inclusion: { in: STATUSES }

  delegate :user, :user_id, to: :audio_session

  def transcript_preview(limit: 80)
    return nil if transcript.blank?
    transcript.length > limit ? "#{transcript[0, limit]}…" : transcript
  end
end
