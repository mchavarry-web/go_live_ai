# frozen_string_literal: true

# Streams a single conversation to its owner.
#
# Subscription:
#   /cable?token=<jwt>   →  ApplicationCable::Connection#find_verified_user
#   { channel: "ChatChannel", conversation_id: <uuid> }
#
# Broadcast envelope (from ChatGenerationJob):
#   { type: "delta",      content: "chunk of text" }
#   { type: "message",    message: { id, role, content, created_at } }
#   { type: "done",       assistant_message_id: <uuid> }
#   { type: "error",      message: "human-readable error" }
class ChatChannel < ApplicationCable::Channel
  def subscribed
    conversation = current_user.conversations.find_by(id: params[:conversation_id])
    return reject unless conversation

    stream_from stream_name_for(conversation.id)
  end

  def self.stream_name_for(conversation_id) = "chat:#{conversation_id}"

  def stream_name_for(conversation_id) = self.class.stream_name_for(conversation_id)
end
