# frozen_string_literal: true

# Wave B.4 (2026-05-06) — durable post-turn learning.
#
# Enqueued from ChatGenerationJob right after the assistant Message has
# been persisted. Calls FastAPI /internal/chat/learn synchronously and
# stamps the resulting counts onto the assistant Message metadata for
# observability. Sidekiq retries handle transient failures so the
# learning pass survives worker restarts.
#
# When the FastAPI flag `post_turn_inline` is True, FastAPI ALSO runs
# the post-turn batch in-process via asyncio.create_task. Setting the
# Rails-side feature flag below to false during cutover would cause
# duplicate writes — but the dedupe path (Wave A.3) makes that safe.
class PostTurnLearningJob < ApplicationJob
  queue_as :default

  def perform(conversation_id:, user_message_id:, assistant_message_id:)
    conversation     = Conversation.find(conversation_id)
    user_message     = Message.find(user_message_id)
    assistant_message = Message.find(assistant_message_id)
    user             = conversation.user
    avatar           = user.avatar

    payload = {
      user_id:              user.id.to_s,
      conversation_id:      conversation.id,
      user_message:         user_message.content,
      assistant_response:   assistant_message.content,
      conversation_history: conversation.history_payload,
      active_mode:          avatar&.active_mode || "friends",
      display_name:         user.name || "el usuario",
      turn_count:           avatar&.message_count_in_active_mode || 0,
      timezone:             user.timezone,
      message_created_at:   user_message.created_at.utc.iso8601
    }.compact

    response = AiAgentsClient.new.run_post_turn_learning(payload)

    if response.is_a?(Hash)
      stamp_telemetry(assistant_message, response)
    else
      Rails.logger.warn(
        "[post-turn-learn] non-hash response chunk=#{assistant_message_id} response=#{response.inspect.first(200)}"
      )
    end
  rescue StandardError => e
    Rails.logger.error(
      "[post-turn-learn] failed: assistant=#{assistant_message_id} #{e.class}: #{e.message}"
    )
    raise # let Sidekiq retry
  end

  private

  def stamp_telemetry(message, response)
    metadata = (message.metadata || {}).merge(
      "post_turn_learning" => {
        "insights_new"        => response["insights_new"],
        "insights_superseded" => response["insights_superseded"],
        "events_new"          => response["events_new"],
        "persona_notes"       => response["persona_notes"],
        "summary_written"     => response["summary_written"],
        "slang_calibrated"    => response["slang_calibrated"],
        "took_ms"             => response["took_ms"],
        "completed_at"        => Time.current.iso8601(3)
      }
    )
    message.update!(metadata: metadata)
  end
end
