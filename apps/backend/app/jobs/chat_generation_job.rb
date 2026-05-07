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
#
# Roundtrip telemetry: every assistant Message persists a `metadata.telemetry`
# blob with hop-by-hop timestamps so testers can spot slowdowns. Even on
# failure (empty stream, exception, upstream timeout) we still write
# whatever timestamps we have — partial logs are useful for triage.
class ChatGenerationJob < ApplicationJob
  queue_as :default

  def perform(conversation_id:, user_message_id:, client_sent_at: nil, api_received_at: nil)
    conversation = Conversation.find(conversation_id)
    user_message = Message.find(user_message_id)
    user         = conversation.user
    stream_name  = ChatChannel.stream_name_for(conversation.id)

    telemetry = {
      "client_sent_at"     => client_sent_at,
      "api_received_at"    => api_received_at,
      "api_to_ai_sent_at"  => Time.current.iso8601(3)
    }.compact

    payload = build_payload(conversation, user_message, user)
    accumulated = +""
    chunk_count = 0

    begin
      stream_result = AiAgentsClient.new.stream_chat(payload) do |chunk|
        next if chunk.blank?
        chunk_count += 1
        accumulated << chunk
        ActionCable.server.broadcast(stream_name, { type: "delta", content: chunk })
      end
      if stream_result.is_a?(Hash) && stream_result[:telemetry].is_a?(Hash)
        telemetry.merge!(stream_result[:telemetry])
      end
    rescue StandardError => e
      telemetry["api_to_app_done_at"] = Time.current.iso8601(3)
      telemetry["status"] = "error"
      telemetry["error"]  = "#{e.class}: #{e.message}"
      persist_assistant_failure(
        conversation:   conversation,
        stream_name:    stream_name,
        telemetry:      telemetry,
        public_message: "Error generating response. Please retry."
      )
      Rails.logger.error("ChatGenerationJob failed: #{e.class}: #{e.message}\n#{e.backtrace&.first(5)&.join("\n")}")
      return
    end

    Rails.logger.info(
      "ChatGenerationJob: conversation=#{conversation.id} chunks=#{chunk_count} " \
      "accumulated=#{accumulated.length}b"
    )

    if accumulated.strip.empty?
      telemetry["api_to_app_done_at"] = Time.current.iso8601(3)
      telemetry["status"] = "empty"
      assistant = conversation.messages.create!(
        role: "assistant",
        content: "⚠️ The avatar couldn't respond right now. Please try again.",
        metadata: {
          "generated_by" => "chat_generation_job",
          "status"       => "empty_stream",
          "telemetry"    => telemetry
        }
      )
      ActionCable.server.broadcast(stream_name, {
        type: "error",
        message: "Empty response from avatar; please retry.",
        assistant_message_id: assistant.id
      })
      return
    end

    telemetry["api_to_app_done_at"] = Time.current.iso8601(3)
    telemetry["status"] = "ok"

    assistant = conversation.messages.create!(
      role: "assistant",
      content: accumulated,
      metadata: {
        "generated_by" => "chat_generation_job",
        "status"       => "ok",
        "telemetry"    => telemetry
      }
    )
    ActionCable.server.broadcast(stream_name, {
      type: "message",
      message: message_payload(assistant)
    })
    ActionCable.server.broadcast(stream_name, {
      type: "done",
      assistant_message_id: assistant.id
    })

    # Wave B.4 — durable post-turn learning. Sidekiq retries handle
    # transient failures so the learning pass survives worker restarts,
    # unlike the in-process FastAPI create_task path.
    PostTurnLearningJob.perform_later(
      conversation_id:     conversation.id,
      user_message_id:     user_message.id,
      assistant_message_id: assistant.id
    )
  end

  private

  # FastAPI ChatGenerateRequest — see apps/ai-agents/app/models/schemas.py
  def build_payload(conversation, user_message, user)
    {
      user_id:         user.id.to_s,
      message:         user_message.content,
      conversation_id: conversation.id,
      user_profile:    user_profile(user),
      conversation_history: conversation.history_payload,
      message_created_at: user_message.created_at.utc.iso8601
    }
  end

  def user_profile(user)
    avatar = user.avatar
    {
      display_name:    user.name,
      avatar_name:     avatar&.name.presence || "Avatar",
      country:         user.country,
      timezone:        user.timezone,
      last_location:   user.current_location_payload,
      age_range:       user.try(:age_range),
      # Wave A.1 (2026-05-06) — interests / values / personality / behavior
      # were previously hardcoded empty. They live on the Avatar's
      # `appearance` (interests, values, intro/extro, rational/emotional)
      # and `behavior` (tone_*, language, *_topics) jsonb columns; the
      # accessors below pull only the shape FastAPI's `UserProfile`
      # schema expects and drop blanks so .compact removes empty fields.
      interests:           avatar&.interests_list,
      values:              avatar&.values_list,
      introvert_extrovert: avatar&.introvert_extrovert_score,
      rational_emotional:  avatar&.rational_emotional_score,
      behavior_settings:   avatar&.behavior_settings_payload,
      # Pass canonical Rails 1-10 knowledge_level. FastAPI accepts as-is and
      # renders as 1-5 in the prompt for stylistic stability.
      knowledge_level: avatar&.knowledge_level || 1,
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
      metadata:   message.metadata,
      created_at: message.created_at.iso8601
    }
  end

  def persist_assistant_failure(conversation:, stream_name:, telemetry:, public_message:)
    assistant = conversation.messages.create!(
      role:    "assistant",
      content: "⚠️ #{public_message}",
      metadata: {
        "generated_by" => "chat_generation_job",
        "status"       => "error",
        "telemetry"    => telemetry
      }
    )
    ActionCable.server.broadcast(stream_name, {
      type: "error",
      message: public_message,
      assistant_message_id: assistant.id
    })
  rescue StandardError => e
    Rails.logger.error("ChatGenerationJob: failed to persist failure record — #{e.class}: #{e.message}")
    ActionCable.server.broadcast(stream_name, { type: "error", message: public_message })
  end
end
