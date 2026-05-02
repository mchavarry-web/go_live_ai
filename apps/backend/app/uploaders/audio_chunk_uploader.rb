# Shrine uploader for audio chunks and voice-enrollment phrase clips.
# Uses :store_private — these files are never publicly served.
#
# 25MB cap matches OpenAI's transcription API limit; AAC/m4a is the default
# encoding from expo-audio. Cap is generous enough to absorb misconfigured
# clients that emit larger m4a; smaller files are fine.
#
# MIME allowlist covers:
#   - audio/* (the obvious cases)
#   - video/mp4 + video/3gpp because expo-audio on Android writes audio-only
#     MPEG-4 containers that Marcel sometimes sniffs as a video type.
#   - application/octet-stream as a last-resort fallback when Marcel can't
#     identify a very short clip — guarded by a filename-extension check
#     so we don't accept arbitrary blobs.
class AudioChunkUploader < Shrine
  storages[:store] = Shrine.storages[:store_private]

  plugin :determine_mime_type
  plugin :validation_helpers

  ALLOWED_MIME_TYPES = %w[
    audio/mp4
    audio/m4a
    audio/x-m4a
    audio/aac
    audio/mpeg
    audio/wav
    audio/x-wav
    audio/3gpp
    video/mp4
    video/3gpp
  ].freeze

  AUDIO_EXTENSIONS = %w[.m4a .mp4 .aac .mp3 .wav .3gp .3gpp].freeze

  Attacher.validate do
    validate_max_size 25.megabytes, message: "max 25MB per chunk"

    mime = file.mime_type
    filename = file.original_filename.to_s.downcase

    accepted =
      ALLOWED_MIME_TYPES.include?(mime) ||
      (mime == "application/octet-stream" &&
        AUDIO_EXTENSIONS.any? { |ext| filename.end_with?(ext) })

    unless accepted
      Shrine.logger.warn(
        "AudioChunkUploader: rejected mime=#{mime.inspect} filename=#{filename.inspect}"
      )
      errors << "audio file format not supported (detected #{mime.inspect})"
    end
  end
end
