# Per-user store for the start/stop trigger phrases captured at the gate
# of audio-training onboarding. Phase 1 stores audio + transcript text;
# Phase 2 will compute a voice embedding and ship to FastAPI pgvector.
class VoiceEnrollment < ApplicationRecord
  include AudioChunkUploader::Attachment(:start_phrase_audio)
  include AudioChunkUploader::Attachment(:stop_phrase_audio)

  STATUSES = %w[pending ready enrolling failed].freeze

  belongs_to :user

  validates :status, inclusion: { in: STATUSES }

  def ready?
    status == "ready"
  end
end
