# frozen_string_literal: true

# Conversation CRUD for the mobile client.
#
#   GET    /api/v1/chat/conversations            list (most-recent first)
#   POST   /api/v1/chat/conversations            create (optional title)
#   GET    /api/v1/chat/conversations/:id        show
#   DELETE /api/v1/chat/conversations/:id        delete
class Api::V1::ConversationsController < Api::V1::BaseController
  def index
    conversations = current_user.conversations.recent.limit(100)
    render_success(conversations: conversations.map { |c| summary(c) })
  end

  def show
    conv = current_user.conversations.find(params[:id])
    render_success(conversation: summary(conv).merge(messages: conv.messages.map { |m| message_json(m) }))
  rescue ActiveRecord::RecordNotFound
    render_error("Conversation not found", :not_found)
  end

  def create
    conv = current_user.conversations.create!(title: params[:title])
    render json: { conversation: summary(conv) }, status: :created
  end

  def destroy
    current_user.conversations.find(params[:id]).destroy!
    head :no_content
  rescue ActiveRecord::RecordNotFound
    render_error("Conversation not found", :not_found)
  end

  private

  def summary(conv)
    {
      id:            conv.id,
      title:         conv.title,
      last_active_at: conv.last_active_at.iso8601,
      message_count: conv.messages.count,
      created_at:    conv.created_at.iso8601
    }
  end

  def message_json(m)
    {
      id:               m.id,
      role:             m.role,
      content:          m.content,
      proactive_skill:  m.proactive_skill,
      metadata:         m.metadata,
      created_at:       m.created_at.iso8601
    }
  end
end
