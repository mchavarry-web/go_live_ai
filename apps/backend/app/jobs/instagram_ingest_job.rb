# frozen_string_literal: true

# Forwards a user-uploaded Instagram payload to FastAPI for insight
# extraction. Also refreshes the last-ingested marker on the
# SocialConnection.
class InstagramIngestJob < ApplicationJob
  queue_as :default

  def perform(user_id:, payload:)
    ExtractInsightsJob.perform_later(
      user_id:  user_id,
      provider: "instagram",
      payload:  payload
    )
  end
end
