# frozen_string_literal: true

# Forwards a user-uploaded Instagram payload to FastAPI for insight
# extraction. Also refreshes the last-ingested marker on the
# SocialConnection.
class InstagramIngestJob < ApplicationJob
  queue_as :low

  def perform(user_id:, payload:)
    # DEV-99 — stamp the ingestion marker at processing time too (the
    # controller stamps it at upload time; this covers direct enqueues).
    # Non-destructive merge: metadata is a shared jsonb grab-bag.
    conn = SocialConnection.find_by(user_id: user_id, provider: "instagram")
    conn&.update!(metadata: conn.metadata.merge("last_ingested_at" => Time.current.iso8601))

    ExtractInsightsJob.perform_later(
      user_id:  user_id,
      provider: "instagram",
      payload:  payload
    )
  end
end
