# frozen_string_literal: true

# Pulls raw data from a connected social provider (using the stored OAuth
# token) and caches it on the SocialConnection's `metadata.raw_data`. On
# success, chains ExtractInsightsJob so FastAPI can process it.
#
# Per-provider fetch details are deliberately minimal for now — just enough
# to prove the pipeline end-to-end. Expand as product scope hardens.
class FetchSocialDataJob < ApplicationJob
  queue_as :default

  def perform(user_id:, provider:)
    conn = SocialConnection.find_by!(user_id: user_id, provider: provider)
    raw_data = fetch(conn)
    conn.update!(metadata: conn.metadata.merge("raw_data" => raw_data, "fetched_at" => Time.current.iso8601))

    ExtractInsightsJob.perform_later(user_id: user_id, provider: provider)
  end

  private

  def fetch(conn)
    case conn.provider
    when "spotify"  then fetch_spotify(conn)
    when "facebook" then fetch_facebook(conn)
    when "twitter"  then fetch_twitter(conn)
    else raise ArgumentError, "unknown provider: #{conn.provider.inspect}"
    end
  end

  # Minimal reference pulls — top artists, top tracks, recently played.
  def fetch_spotify(conn)
    headers = { "Authorization" => "Bearer #{conn.access_token}" }
    {
      "top_artists"       => http_get("https://api.spotify.com/v1/me/top/artists?limit=50", headers),
      "top_tracks"        => http_get("https://api.spotify.com/v1/me/top/tracks?limit=50", headers),
      "recently_played"   => http_get("https://api.spotify.com/v1/me/player/recently-played?limit=50", headers)
    }
  end

  # Graph API pulls; scope depends on what the user granted client-side.
  def fetch_facebook(conn)
    { "profile" => http_get("https://graph.facebook.com/me?fields=id,name,email,link&access_token=#{conn.access_token}") }
  end

  # Twitter API v2 minimal
  def fetch_twitter(conn)
    headers = { "Authorization" => "Bearer #{conn.access_token}" }
    { "me" => http_get("https://api.twitter.com/2/users/me", headers) }
  end

  def http_get(url, headers = {})
    r = HTTParty.get(url, headers: headers, timeout: 10)
    r.code == 200 ? r.parsed_response : { "error" => r.code, "body" => r.body.to_s[0, 500] }
  end
end
