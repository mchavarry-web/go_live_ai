# frozen_string_literal: true

# Messages nested under a conversation. Sending a user message enqueues
# ChatGenerationJob which streams the assistant reply back on the
# conversation's ActionCable channel.
#
#   GET  /api/v1/chat/conversations/:conversation_id/messages   ?limit=30&before=<message_id>
#   POST /api/v1/chat/conversations/:conversation_id/messages   { content, client_sent_at? }
#
# DEV-95: #index is cursor-paginated so long conversations open instantly.
# Without params it returns the LATEST `limit` messages; `before=<id>`
# returns messages strictly older than that message. Pages are ordered
# oldest → newest within the page, plus `has_more` for the client.
#
# Roundtrip telemetry: an optional `client_sent_at` ISO8601 timestamp from
# the client, plus `api_received_at` stamped here, are persisted on the
# user message metadata and threaded into the job so the assistant
# message's metadata.telemetry has the full hop-by-hop log.
class Api::V1::MessagesController < Api::V1::BaseController
  before_action :load_conversation

  DEFAULT_PAGE_SIZE = 30
  MAX_PAGE_SIZE     = 100

  def index
    limit = params[:limit].to_i
    limit = DEFAULT_PAGE_SIZE if limit <= 0
    limit = [limit, MAX_PAGE_SIZE].min

    # Walk backwards from the newest message (or from the `before` cursor).
    # `id` is a UUID so it can't order chronologically on its own, but it
    # works as a stable tiebreaker for messages created in the same instant
    # (Postgres row-value comparison keeps the cursor exact, no OFFSET drift).
    scope = @conversation.messages.reorder(created_at: :desc, id: :desc)
    if params[:before].present?
      anchor = @conversation.messages.find_by(id: params[:before])
      return render_error("Cursor message not found", :not_found) unless anchor
      scope = scope.where(
        "(messages.created_at, messages.id) < (?, ?)",
        anchor.created_at, anchor.id
      )
    end

    page     = scope.limit(limit + 1).to_a
    has_more = page.size > limit
    render_success(
      messages: page.first(limit).reverse.map { |m| message_json(m) },
      has_more: has_more
    )
  end

  def create
    client_sent_at  = parse_iso8601(params[:client_sent_at])
    api_received_at = Time.current

    user_telemetry = {
      "client_sent_at"  => client_sent_at&.iso8601(3),
      "api_received_at" => api_received_at.iso8601(3)
    }.compact

    msg = @conversation.messages.create!(
      role:     "user",
      content:  params.require(:content),
      metadata: { "telemetry" => user_telemetry }
    )
    # Bump the per-mode lifetime counter so the Citas ramp can graduate
    # nascent → warming → established. Counts the user's outgoing
    # messages only (avatar replies don't count). The increment is atomic
    # via jsonb_set on the avatar row; see Avatar#increment_mode_message_count!.
    current_user.avatar&.increment_mode_message_count!
    ChatGenerationJob.perform_later(
      conversation_id: @conversation.id,
      user_message_id: msg.id,
      client_sent_at:  client_sent_at&.iso8601(3),
      api_received_at: api_received_at.iso8601(3)
    )
    render json: { message: message_json(msg) }, status: :accepted
  rescue ActionController::ParameterMissing => e
    render_error(e.message, :unprocessable_entity)
  end

  # POST /api/v1/chat/conversations/:conversation_id/messages/voice
  # Multipart upload from the mic button. We transcribe synchronously here
  # (so the user message persists with the actual transcript before the
  # assistant job runs) then enqueue ChatGenerationJob with voice_response:
  # true so the assistant reply also gets rendered to TTS.
  def voice
    audio_param = params[:audio]
    return render_error("audio file required", :unprocessable_entity) unless audio_param.respond_to?(:read)

    client_sent_at  = parse_iso8601(params[:client_sent_at])
    api_received_at = Time.current
    language        = params[:language].presence

    # Stream the raw upload directly to FastAPI — no need to persist the
    # user-side audio long-term. We attach it to the Message anyway so a
    # tester can replay what was sent (and so a future "edit transcript"
    # surface has the source bytes).
    transcribe_io = audio_param.respond_to?(:tempfile) ? audio_param.tempfile : audio_param
    transcribe_io.rewind if transcribe_io.respond_to?(:rewind)

    transcription = AiAgentsClient.new.transcribe_chunk(
      user_id:  current_user.id,
      audio_io: transcribe_io,
      language: language
    )
    transcript = transcription.is_a?(Hash) ? transcription["text"].to_s.strip : ""
    error_kind = transcription.is_a?(Hash) ? transcription["error"].presence : nil

    if transcript.empty?
      # FastAPI's /internal/audio/transcribe reports the failure mode in the
      # additive `error` field: "quota" | "unsupported_format" |
      # "provider_error". Absent/nil error + empty text means the provider
      # answered but heard nothing intelligible (silence, background noise).
      Rails.logger.warn(
        "[messages#voice] empty transcript user=#{current_user.id} conv=#{@conversation.id} " \
        "lang=#{language.inspect} error=#{error_kind.inspect} resp=#{transcription.inspect.first(300)}"
      )
      return render_error(voice_transcription_error_message(error_kind), :unprocessable_entity)
    end

    user_telemetry = {
      "client_sent_at"  => client_sent_at&.iso8601(3),
      "api_received_at" => api_received_at.iso8601(3)
    }.compact

    audio_param.rewind if audio_param.respond_to?(:rewind)
    msg = @conversation.messages.new(
      role:     "user",
      content:  transcript,
      metadata: {
        "telemetry"   => user_telemetry,
        "voice_input" => true,
        "language"    => transcription.is_a?(Hash) ? transcription["language"] : nil
      }.compact
    )
    msg.audio = audio_param
    msg.save!

    current_user.avatar&.increment_mode_message_count!
    ChatGenerationJob.perform_later(
      conversation_id: @conversation.id,
      user_message_id: msg.id,
      client_sent_at:  client_sent_at&.iso8601(3),
      api_received_at: api_received_at.iso8601(3),
      voice_response:  true
    )
    render json: { message: message_json(msg) }, status: :accepted
  rescue Shrine::Error => e
    Rails.logger.warn("[messages#voice] shrine error: #{e.class}: #{e.message}")
    render_error("audio upload failed: #{e.message}", :unprocessable_entity)
  rescue ActiveRecord::RecordInvalid => e
    render_error(e.record.errors.full_messages.join(", "), :unprocessable_entity)
  end

  private

  # Distinct Spanish copy per transcription failure mode (DEV-97).
  #   nil / unknown       → provider heard nothing → coach the user
  #   "quota"             → daily audio cap reached
  #   "provider_error" /
  #   "unsupported_format"→ upstream/service problem → try later
  def voice_transcription_error_message(error_kind)
    case error_kind
    when "quota"
      "Has alcanzado el límite de audio por hoy."
    when "provider_error", "unsupported_format"
      "El servicio de audio no está disponible en este momento. Intenta más tarde."
    else
      "No pudimos entender el audio. Intenta hablar más cerca del micrófono."
    end
  end

  def load_conversation
    @conversation = current_user.conversations.find(params[:conversation_id])
  rescue ActiveRecord::RecordNotFound
    render_error("Conversation not found", :not_found)
  end

  def parse_iso8601(value)
    return nil if value.blank?
    Time.iso8601(value.to_s)
  rescue ArgumentError
    nil
  end

  def message_json(m)
    {
      id:              m.id,
      role:            m.role,
      content:         m.content,
      proactive_skill: m.proactive_skill,
      metadata:        m.metadata,
      has_audio:       m.audio?,
      created_at:      m.created_at.iso8601
    }
  end
end
