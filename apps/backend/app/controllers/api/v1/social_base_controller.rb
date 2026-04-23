# frozen_string_literal: true

# Shared helpers for the per-platform controllers (Instagram, Facebook,
# Twitter, Spotify). Each subclass declares its provider via `self.provider`
# and inherits `status`, `disconnect`, and `extract_insights`. Platform-
# specific actions (Spotify's `auth_url`/`callback`, Instagram's `ingest`
# upload) live in the subclass.
class Api::V1::SocialBaseController < Api::V1::BaseController
  class_attribute :provider, instance_writer: false

  # GET /api/v1/:provider/status
  def status
    conn = current_connection
    render_success(
      provider:      provider,
      connected:     conn.present?,
      external_user_id: conn&.external_user_id,
      scopes:        conn&.scopes,
      expires_at:    conn&.expires_at&.iso8601,
      expired:       conn&.expired? || false,
      metadata:      conn&.metadata || {}
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
end
