# frozen_string_literal: true

# Spotify connection + ingestion.
#
#   GET  /api/v1/spotify/auth_url   → { url } — mobile opens this in WebView
#   GET  /api/v1/spotify/callback   → Spotify redirects here with ?code=&state=
#   GET  /api/v1/spotify/status     → connection state (inherited)
#   POST /api/v1/spotify/ingest     → enqueue raw-data fetch
#   POST /api/v1/spotify/extract    → enqueue insight extraction (inherited)
#   DELETE /api/v1/spotify          → disconnect (inherited)
class Api::V1::SpotifyController < Api::V1::SocialBaseController
  self.provider = "spotify"

  # The callback is hit by Spotify's redirect with no Authorization header.
  # We carry the caller's identity in `state` (a signed message + nonce).
  skip_before_action :authenticate_api_user!, only: :callback

  STATE_CACHE_PREFIX = "spotify:oauth:state:"

  def auth_url
    state = SecureRandom.urlsafe_base64(24)
    Rails.cache.write(state_key(state), current_user.id, expires_in: 10.minutes)
    url = Social::SpotifyOauth.new(user: current_user).authorize_url(state: state)
    render_success(url: url, state: state)
  end

  def callback
    user_id = Rails.cache.read(state_key(params[:state]))
    return render_error("invalid or expired state", :unauthorized) unless user_id

    user = User.find(user_id)
    Rails.cache.delete(state_key(params[:state]))

    conn = Social::SpotifyOauth.new(user: user).exchange_code!(params.require(:code))
    ExtractInsightsJob.perform_later(user_id: user.id, provider: "spotify")
    render_success(provider: "spotify", connected: true, external_user_id: conn.external_user_id)
  rescue Social::SpotifyOauth::Error, ActionController::ParameterMissing => e
    render_error(e.message, :unprocessable_entity)
  end

  def ingest
    return render_error("not connected", :not_found) unless current_connection
    FetchSocialDataJob.perform_later(user_id: current_user.id, provider: "spotify")
    render json: { status: "enqueued", provider: "spotify" }, status: :accepted
  end

  private

  def state_key(state) = "#{STATE_CACHE_PREFIX}#{state}"
end
