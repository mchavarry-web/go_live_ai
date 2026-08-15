# frozen_string_literal: true

# Shared helpers for the per-platform controllers (Instagram, Facebook,
# Twitter, Spotify). Each subclass declares its provider via `self.provider`
# and inherits `status`, `disconnect`, and `extract_insights`. Platform-
# specific actions (Spotify's `auth_url`/`callback`, Instagram's `ingest`
# upload) live in the subclass.
class Api::V1::SocialBaseController < Api::V1::BaseController
  class_attribute :provider, instance_writer: false

  # GET /api/v1/:provider/status
  #
  # Enriched (DEV-99) so clients can tell whether the connection actually fed
  # the avatar:
  #   ingested_items_count — best-effort size of the cached raw payload
  #                          (metadata.item_count for Instagram uploads, else
  #                          the summed array sizes inside metadata.raw_data
  #                          as stashed by FetchSocialDataJob)
  #   last_ingested_at     — stamped by FetchSocialDataJob / the Instagram
  #                          ingest path (falls back to legacy fetched_at)
  #   last_extracted_at    — stamped by ExtractInsightsJob on FastAPI success
  #   insights_count       — per-platform insight count from FastAPI
  #                          (/internal/memory/:id/sources; nil when the
  #                          sidecar is unreachable — never fails the request)
  #   stale                — set by SocialResyncJob when an expired pasted
  #                          token can no longer be refreshed server-side
  def status
    conn = current_connection
    md   = conn&.metadata || {}
    render_success(
      provider:             provider,
      connected:            conn.present?,
      external_user_id:     conn&.external_user_id,
      scopes:               conn&.scopes,
      expires_at:           conn&.expires_at&.iso8601,
      expired:              conn&.expired? || false,
      stale:                md["stale"] == true,
      ingested_items_count: ingested_items_count(md),
      last_ingested_at:     md["last_ingested_at"] || md["fetched_at"],
      last_extracted_at:    md["last_extracted_at"],
      insights_count:       conn.present? ? platform_insights_count : nil,
      metadata:             md
    )
  end

  # DELETE /api/v1/:provider
  def disconnect
    conn = current_connection
    return render_error("not connected", :not_found) unless conn
    conn.destroy!
    head :no_content
  end

  # POST /api/v1/:provider/extract
  # Fires an async job that pulls raw data + asks FastAPI to extract insights.
  def extract_insights
    ExtractInsightsJob.perform_later(
      user_id:  current_user.id,
      provider: provider
    )
    render json: { status: "enqueued", provider: provider }, status: :accepted
  end

  private

  def current_connection
    current_user.social_connections.find_by(provider: provider)
  end

  # Best-effort count of raw items already pulled from the platform.
  # Instagram uploads stamp an explicit item_count; fetch-based providers
  # cache the provider payload under metadata.raw_data, where every array is
  # a list of items (posts, tweets, top_tracks, …) — sum their sizes without
  # descending into the items themselves. nil when nothing was ingested yet.
  def ingested_items_count(md)
    return md["item_count"].to_i if md["item_count"].present?

    raw = md["raw_data"]
    return nil unless raw.is_a?(Hash)
    count_array_items(raw)
  end

  def count_array_items(node)
    case node
    when Array then node.size
    when Hash  then node.values.sum { |v| count_array_items(v) }
    else 0
    end
  end

  # Per-platform insight count from FastAPI. Social insights are stored with
  # source == platform name (see apps/ai-agents/app/api/routes/insights.py),
  # so the sources map keys line up with `provider` directly. Any failure
  # (sidecar down, timeout, malformed body) degrades to nil.
  def platform_insights_count
    response = AiAgentsClient.new.insight_sources(current_user.id)
    sources  = response.is_a?(Hash) ? response["sources"] : nil
    return nil unless sources.is_a?(Hash)
    sources[provider].to_i
  rescue StandardError => e
    Rails.logger.warn("[social-status] insight_sources failed user=#{current_user.id} " \
                      "provider=#{provider} #{e.class}: #{e.message}")
    nil
  end
end
