# frozen_string_literal: true

# Streams an avatar response for a just-created user message.
#
# Sequence:
#   1. Build the FastAPI payload (user profile + conversation history).
#   2. Open a streamed POST to FastAPI /internal/chat/stream.
#   3. Broadcast each chunk as { type: "delta", content: <chunk> }.
#   4. Persist the accumulated body as an assistant Message.
#   5. Broadcast { type: "message", message: {...} } + { type: "done", ... }.
#
# Errors are reported as { type: "error", message: ... } on the same channel.
class ChatGenerationJob < ApplicationJob
  queue_as :default

  def perform(conversation_id:, user_message_id:)
    conversation = Conversation.find(conversation_id)
    user_message = Message.find(user_message_id)
    user         = conversation.user
    stream_name  = ChatChannel.stream_name_for(conversation.id)

    payload = build_payload(conversation, user_message, user)
    accumulated = +""
    chunk_count = 0

    AiAgentsClient.new.stream_chat(payload) do |chunk|
      next if chunk.blank?
      chunk_count += 1
      accumulated << chunk
      ActionCable.server.broadcast(stream_name, { type: "delta", content: chunk })
    end

    Rails.logger.info(
      "ChatGenerationJob: conversation=#{conversation.id} chunks=#{chunk_count} " \
      "accumulated=#{accumulated.length}b"
    )

    if accumulated.strip.empty?
      # FastAPI returned no text (e.g. missing LLM key, upstream error).
      # Persist a placeholder so the conversation stays consistent, and
      # surface the failure on the channel.
      assistant = conversation.messages.create!(
        role: "assistant",
        content: "⚠️ The avatar couldn't respond right now. Please try again.",
        metadata: { generated_by: "chat_generation_job", status: "empty_stream" }
      )
      ActionCable.server.broadcast(stream_name, {
        type: "error",
        message: "Empty response from avatar; please retry.",
        assistant_message_id: assistant.id
      })
      return
    end

    assistant = conversation.messages.create!(
      role: "assistant",
      content: accumulated,
      metadata: { generated_by: "chat_generation_job", status: "ok" }
    )
    ActionCable.server.broadcast(stream_name, {
      type: "message",
      message: message_payload(assistant)
    })
    ActionCable.server.broadcast(stream_name, {
      type: "done",
      assistant_message_id: assistant.id
    })
  rescue StandardError => e
    Rails.logger.error("ChatGenerationJob failed: #{e.class}: #{e.message}\n#{e.backtrace&.first(5)&.join("\n")}")
    ActionCable.server.broadcast(stream_name, {
      type: "error",
      message: "Error generating response. Please retry."
    }) if defined?(stream_name) && stream_name
    # don't re-raise — we've already surfaced the error to the client and
    # retrying with the same params will just hit the same upstream failure.
  end

  private

  # FastAPI ChatGenerateRequest — see apps/ai-agents/app/models/schemas.py
  def build_payload(conversation, user_message, user)
    {
      user_id:         user.id.to_s,
      message:         user_message.content,
      conversation_id: conversation.id,
      user_profile:    user_profile(user),
      conversation_history: conversation.history_payload
    }
  end

  def user_profile(user)
    avatar = user.avatar
    {
      display_name:    user.name,
      avatar_name:     avatar&.name.presence || "Avatar",
      country:         user.country,
      interests:       [],
      knowledge_level: [((avatar&.knowledge_level || 1) + 1) / 2, 5].min,
      # Behavior mode + the user's lifetime message count *in that mode*.
      # FastAPI uses both: the mode picks the prompt block (Profesional /
      # Amigos / Citas) and the count drives the Citas ramp thresholds.
      active_mode:        avatar&.active_mode || "friends",
      mode_message_count: avatar&.message_count_in_active_mode || 0
    }.compact
  end

  def message_payload(message)
    {
      id:         message.id,
      role:       message.role,
      content:    message.content,
      created_at: message.created_at.iso8601
    }
  end
end
