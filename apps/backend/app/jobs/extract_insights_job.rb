# frozen_string_literal: true

# Asks FastAPI to run platform-specific insight extraction for a user.
# Idempotent: running it again just refreshes insights.
class ExtractInsightsJob < ApplicationJob
  queue_as :default

  def perform(user_id:, provider:, payload: nil)
    user = User.find(user_id)
    client = AiAgentsClient.new

    # Use whatever platform data is available. For Spotify/FB/Twitter, the
    # FetchSocialDataJob will have stashed the raw payload on the
    # SocialConnection's `metadata.raw_data`; for Instagram the payload is
    # passed through directly.
    conn = user.social_connections.find_by(provider: provider)
    data = payload || conn&.metadata&.dig("raw_data") || {}

    response = client.extract_insights(
      platform: provider,
      user_id:  user.id.to_s,
      payload:  data
    )

    # knowledge_level is now a derived method — nothing to mirror in Rails.
    # Insight counts are synced nightly by SyncAvatarCountersJob, but if the
    # response surfaces a count directly, opportunistically bump the avatar.
    if response.is_a?(Hash) && response["insights_count"]
      avatar = user.avatar
      avatar&.update_columns(insights_count: response["insights_count"].to_i)
    end

    Rails.logger.info("ExtractInsightsJob: user=#{user.id} provider=#{provider} " \
                      "insights=#{response.is_a?(Hash) ? response['insights']&.size : '?'}")
  end
end
