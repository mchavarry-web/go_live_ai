# frozen_string_literal: true

# Instagram does not have a server-to-server OAuth flow for pulling a user's
# own content in this app's tier, so ingestion here is upload-based: the
# mobile app uploads the user's Instagram Data Download archive (or a JSON
# payload extracted from it) and Rails forwards that payload to FastAPI for
# insight extraction.
#
#   GET  /api/v1/instagram/status   → has anything been uploaded yet?
#   POST /api/v1/instagram/ingest   → { payload: {...} } — forwards to FastAPI
#   POST /api/v1/instagram/extract  → re-run extraction on the last payload
#   DELETE /api/v1/instagram        → remove the marker
class Api::V1::InstagramController < Api::V1::SocialBaseController
  self.provider = "instagram"

  def ingest
    payload = params.require(:payload).to_unsafe_h
    raise ActionController::ParameterMissing.new(:payload) if payload.empty?

    conn = current_user.social_connections.find_or_initialize_by(provider: "instagram")
    conn.metadata = conn.metadata.merge(
      "last_ingested_at" => Time.current.iso8601,
      "item_count"       => extract_item_count(payload)
    )
    conn.save!

    InstagramIngestJob.perform_later(user_id: current_user.id, payload: payload)
    render json: { status: "enqueued", provider: "instagram" }, status: :accepted
  rescue ActionController::ParameterMissing => e
    render_error(e.message, :unprocessable_entity)
  end

  private

  # Best-effort item count for the status payload; keys depend on the IG
  # archive format but common ones are media[], posts[], stories[].
  def extract_item_count(payload)
    %w[media posts stories].map { |k| payload[k].is_a?(Array) ? payload[k].size : 0 }.sum
  end
end
