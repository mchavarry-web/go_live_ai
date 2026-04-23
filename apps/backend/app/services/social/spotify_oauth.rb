# frozen_string_literal: true

# Server-side Spotify OAuth Authorization Code Flow.
# Docs: https://developer.spotify.com/documentation/web-api/concepts/authorization
#
# Flow:
#   1. Mobile app asks Rails for the auth URL (`#authorize_url`) carrying a
#      signed `state` derived from current_user.id + a fresh nonce cached in
#      Redis so we can verify the callback came from our session.
#   2. User authenticates on Spotify and Spotify redirects to
#      /api/v1/spotify/callback?code=...&state=...
#   3. `#exchange_code!` swaps the code for access + refresh tokens, saves
#      the SocialConnection, and returns it.
module Social
  class SpotifyOauth
    class Error < StandardError; end

    AUTH_URL     = "https://accounts.spotify.com/authorize"
    TOKEN_URL    = "https://accounts.spotify.com/api/token"
    DEFAULT_SCOPES = %w[
      user-read-email
      user-top-read
      user-read-recently-played
      user-library-read
      playlist-read-private
    ].freeze

    def initialize(user:)
      @user = user
    end

    def authorize_url(state:)
      q = {
        client_id:     client_id,
        response_type: "code",
        redirect_uri:  redirect_uri,
        scope:         DEFAULT_SCOPES.join(" "),
        state:         state
      }
      "#{AUTH_URL}?#{URI.encode_www_form(q)}"
    end

    # @return [SocialConnection]
    def exchange_code!(code)
      response = HTTParty.post(
        TOKEN_URL,
        body: {
          grant_type:   "authorization_code",
          code:         code,
          redirect_uri: redirect_uri
        },
        basic_auth: { username: client_id, password: client_secret },
        headers:    { "Content-Type" => "application/x-www-form-urlencoded" },
        timeout:    10
      )
      raise Error, "spotify token exchange failed: HTTP #{response.code}" unless response.code == 200

      body = response.parsed_response
      persist!(
        access_token:  body.fetch("access_token"),
        refresh_token: body["refresh_token"],
        scopes:        body["scope"],
        expires_in:    body["expires_in"].to_i
      )
    end

    private

    def persist!(access_token:, refresh_token:, scopes:, expires_in:)
      profile = fetch_profile(access_token)
      conn = SocialConnection.find_or_initialize_by(user: @user, provider: "spotify")
      conn.access_token     = access_token
      conn.refresh_token    = refresh_token if refresh_token.present?
      conn.scopes           = scopes
      conn.expires_at       = expires_in.positive? ? expires_in.seconds.from_now : nil
      conn.external_user_id = profile["id"]
      conn.metadata         = { display_name: profile["display_name"], country: profile["country"], email: profile["email"] }
      conn.save!
      conn
    end

    def fetch_profile(access_token)
      r = HTTParty.get("https://api.spotify.com/v1/me",
                       headers: { "Authorization" => "Bearer #{access_token}" },
                       timeout: 5)
      raise Error, "spotify /me failed: HTTP #{r.code}" unless r.code == 200
      r.parsed_response
    end

    def client_id      = ENV.fetch("SPOTIFY_CLIENT_ID")
    def client_secret  = ENV.fetch("SPOTIFY_CLIENT_SECRET")
    def redirect_uri   = ENV.fetch("SPOTIFY_REDIRECT_URI")
  end
end
