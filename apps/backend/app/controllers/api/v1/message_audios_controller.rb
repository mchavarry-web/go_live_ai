# frozen_string_literal: true

# Streams the audio attached to a Message — either a user voice clip or
# the assistant's TTS reply.
#
#   GET /api/v1/chat/messages/:id/audio
#
# Auth: standard JWT bearer (BaseController). The message must belong to
# a conversation the current user owns. We send the bytes inline so
# expo-audio can play them via a remote URL on platforms that support it
# (web), or via a fetched-then-cached file URI on native (handled in JS).
class Api::V1::MessageAudiosController < Api::V1::BaseController
  def show
    message = Message
      .joins(:conversation)
      .where(conversations: { user_id: current_user.id })
      .find(params[:id])

    unless message.audio?
      return render_error("audio not available for this message", :not_found)
    end

    # Read bytes through the attacher so it works identically on local
    # FileSystem (dev) and S3 (prod). Audio replies are <1MB; the disk
    # I/O hit doesn't justify a streaming Rack response.
    bytes = message.audio.open(&:read)

    send_data(
      bytes,
      type:        message.audio.mime_type || "audio/mpeg",
      disposition: "inline",
      filename:    "message-#{message.id}.#{audio_extension(message)}"
    )
  rescue ActiveRecord::RecordNotFound
    render_error("Message not found", :not_found)
  end

  private

  def audio_extension(message)
    case message.audio.mime_type
    when "audio/mpeg"             then "mp3"
    when "audio/wav", "audio/x-wav" then "wav"
    when "audio/mp4", "audio/m4a", "audio/x-m4a" then "m4a"
    when "audio/aac"              then "aac"
    when "audio/ogg"              then "ogg"
    when "audio/flac"             then "flac"
    else "bin"
    end
  end
end
