# frozen_string_literal: true

# Messages nested under a conversation. Sending a user message enqueues
# ChatGenerationJob which streams the assistant reply back on the
# conversation's ActionCable channel.
#
#   GET  /api/v1/chat/conversations/:conversation_id/messages
#   POST /api/v1/chat/conversations/:conversation_id/messages   { content }
class Api::V1::MessagesController < Api::V1::BaseController
  before_action :load_conversation

  def index
    render_success(messages: @conversation.messages.map { |m| message_json(m) })
  end

  def create
    msg = @conversation.messages.create!(role: "user", content: params.require(:content))
    # Bump the per-mode lifetime counter so the Citas ramp can graduate
    # nascent → warming → established. Counts the user's outgoing
    # messages only (avatar replies don't count). The increment is atomic
    # via jsonb_set on the avatar row; see Avatar#increment_mode_message_count!.
    current_user.avatar&.increment_mode_message_count!
    ChatGenerationJob.perform_later(
      conversation_id: @conversation.id,
      user_message_id: msg.id
    )
    render json: { message: message_json(msg) }, status: :accepted
  rescue ActionController::ParameterMissing => e
    render_error(e.message, :unprocessable_entity)
  end

  private

  def load_conversation
    @conversation = current_user.conversations.find(params[:conversation_id])
  rescue ActiveRecord::RecordNotFound
    render_error("Conversation not found", :not_found)
  end

  def message_json(m)
    {
      id:              m.id,
      role:            m.role,
      content:         m.content,
      proactive_skill: m.proactive_skill,
      metadata:        m.metadata,
      created_at:      m.created_at.iso8601
    }
  end
end
