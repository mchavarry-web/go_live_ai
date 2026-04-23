# frozen_string_literal: true

# Facebook social connection.
#
# Signup/login already accepts a Facebook access token (see AuthController#facebook).
# For *data ingestion* the Expo app POSTs a fresh Graph API token plus the
# desired scopes to /ingest and we store it as a SocialConnection. Until a
# real Graph-data-fetch job is wired we only persist the token.
class Api::V1::FacebookController < Api::V1::SocialBaseController
  self.provider = "facebook"

  # POST /api/v1/facebook/ingest  { access_token:, scopes:?, expires_in:? }
  def ingest
    access_token = params.require(:access_token)
    conn = current_user.social_connections.find_or_initialize_by(provider: "facebook")
    conn.access_token = access_token
    conn.scopes       = params[:scopes] if params[:scopes]
    conn.expires_at   = params[:expires_in].present? ? params[:expires_in].to_i.seconds.from_now : nil
    conn.save!

    FetchSocialDataJob.perform_later(user_id: current_user.id, provider: "facebook")
    render json: { status: "enqueued", provider: "facebook" }, status: :accepted
  rescue ActionController::ParameterMissing => e
    render_error(e.message, :unprocessable_entity)
  end
end
