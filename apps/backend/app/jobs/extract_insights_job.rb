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

    # If FastAPI updated the user's knowledge level, mirror it on Rails' side.
    if response.is_a?(Hash) && response["knowledge_level"]
      ai_level = response["knowledge_level"].to_i
      mirrored = [ai_level * 2, 10].min
      user.avatar&.update!(knowledge_level: mirrored) if mirrored >= (user.avatar&.knowledge_level || 1)
    end

    Rails.logger.info("ExtractInsightsJob: user=#{user.id} provider=#{provider} " \
                      "insights=#{response.is_a?(Hash) ? response['insights']&.size : '?'}")
  end
end
