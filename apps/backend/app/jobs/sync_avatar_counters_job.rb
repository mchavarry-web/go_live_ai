# frozen_string_literal: true

# Nightly sync of Avatar.insights_count from FastAPI pgvector (the source of
# truth for insight records). Other counters are maintained in real-time by
# after_create_commit hooks on Message / Conversation / SocialConnection.
#
# Run via Whenever: every day at 04:00 local (see config/schedule.rb).
class SyncAvatarCountersJob < ApplicationJob
  queue_as :low

  def perform(user_id: nil)
    scope = user_id.present? ? User.where(id: user_id) : User.all
    client = AiAgentsClient.new
    scope.find_each do |user|
      avatar = user.avatar or next
      insights = safe_list_insights(client, user.id)
      next unless insights.is_a?(Array)
      avatar.update_columns(insights_count: insights.size)
    end
  end

  private

  def safe_list_insights(client, user_id)
    client.list_insights(user_id)
  rescue StandardError => e
    Rails.logger.warn("SyncAvatarCountersJob: insights fetch failed for user=#{user_id}: #{e.message}")
    nil
  end
end
