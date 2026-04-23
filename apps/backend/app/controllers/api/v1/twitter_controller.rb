# frozen_string_literal: true

# Twitter / X connection. Twitter's consumer OAuth 2.0 flow is similar to
# Spotify's; for now the Expo app completes the flow client-side and POSTs
# the bearer token to /ingest to persist the connection.
class Api::V1::TwitterController < Api::V1::SocialBaseController
  self.provider = "twitter"

  # POST /api/v1/twitter/ingest { access_token:, external_user_id:? }
  def ingest
    access_token = params.require(:access_token)
    conn = current_user.social_connections.find_or_initialize_by(provider: "twitter")
    conn.access_token     = access_token
    conn.external_user_id = params[:external_user_id]
    conn.save!

    FetchSocialDataJob.perform_later(user_id: current_user.id, provider: "twitter")
    render json: { status: "enqueued", provider: "twitter" }, status: :accepted
  rescue ActionController::ParameterMissing => e
    render_error(e.message, :unprocessable_entity)
  end
end
