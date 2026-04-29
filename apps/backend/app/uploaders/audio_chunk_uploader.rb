# Shrine uploader for audio chunks and voice-enrollment phrase clips.
# Uses :store_private — these files are never publicly served.
#
# 25MB cap matches OpenAI's transcription API limit; AAC/m4a is the default
# encoding from expo-audio. Cap is generous enough to absorb misconfigured
# clients that emit larger m4a; smaller files are fine.
class AudioChunkUploader < Shrine
  storages[:store] = Shrine.storages[:store_private]

  plugin :determine_mime_type
  plugin :validation_helpers

  Attacher.validate do
    validate_max_size 25.megabytes, message: "max 25MB per chunk"
    validate_mime_type %w[
      audio/mp4
      audio/m4a
      audio/x-m4a
      audio/aac
      audio/mpeg
      audio/wav
      audio/x-wav
    ]
  end
end
