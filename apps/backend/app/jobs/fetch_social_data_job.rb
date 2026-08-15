# frozen_string_literal: true

# Pulls paginated raw data from a connected social provider, caches it on
# SocialConnection.metadata.raw_data, then chains ExtractInsightsJob.
#
# Hardening over the Phase-3 first pass:
#   - Pagination (Spotify `next`, FB paging.next, Twitter pagination_token)
#   - Rate-limit backoff via Retry-After
#   - Spotify token auto-refresh when expires_at is past
#   - Incremental fetch via metadata.last_sync_at
class FetchSocialDataJob < ApplicationJob
  queue_as :low

  MAX_PAGES       = 5
  BACKOFF_DEFAULT = 5.0

  def perform(user_id:, provider:)
    conn = SocialConnection.find_by!(user_id: user_id, provider: provider)
    ensure_fresh_token!(conn)

    last_sync = conn.metadata["last_sync_at"]
    raw_data  = fetch(conn, since: last_sync)
    fetched_at = Time.current

    # Phase 16 — archive raw_data before overwriting metadata so future
    # extraction-chain improvements can redrive against the original
    # provider payload.
    begin
      SocialDataSnapshot.archive!(
        user:       conn.user,
        platform:   provider,
        raw_data:   raw_data,
        fetched_at: fetched_at
      )
    rescue StandardError => e
      Rails.logger.warn(
        "[fetch-social] snapshot failed user=#{user_id} platform=#{provider} #{e.class}: #{e.message}"
      )
    end

    conn.update!(
      metadata: conn.metadata.merge(
        "raw_data"         => raw_data,
        "last_sync_at"     => fetched_at.iso8601,
        "fetched_at"       => fetched_at.iso8601,
        # DEV-99 — surfaced in GET /:provider/status. A successful fetch also
        # clears any stale flag set by SocialResyncJob.
        "last_ingested_at" => fetched_at.iso8601,
        "stale"            => false
      )
    )

    ExtractInsightsJob.perform_later(user_id: user_id, provider: provider)
  end

  private

  # ── Token refresh (Spotify only for now; FB/Twitter use long-lived tokens) ──
  def ensure_fresh_token!(conn)
    return unless conn.expires_at.present? && conn.expires_at < 2.minutes.from_now
    return unless conn.provider == "spotify"
    return unless conn.refresh_token.present?

    r = HTTParty.post(
      "https://accounts.spotify.com/api/token",
      body: { grant_type: "refresh_token", refresh_token: conn.refresh_token },
      basic_auth: { username: ENV.fetch("SPOTIFY_CLIENT_ID"),
                    password: ENV.fetch("SPOTIFY_CLIENT_SECRET") },
      headers:   { "Content-Type" => "application/x-www-form-urlencoded" },
      timeout:   10
    )
    return unless r.code == 200

    body = r.parsed_response
    conn.update!(
      access_token: body.fetch("access_token"),
      expires_at:   body["expires_in"].to_i.seconds.from_now
    )
  end

  def fetch(conn, since:)
    case conn.provider
    when "spotify"  then fetch_spotify(conn)
    when "facebook" then fetch_facebook(conn, since: since)
    when "twitter"  then fetch_twitter(conn, since: since)
    else raise ArgumentError, "unknown provider: #{conn.provider.inspect}"
    end
  end

  # ── Spotify — no built-in `since`, but recently-played is bounded to 50 ──
  def fetch_spotify(conn)
    headers = { "Authorization" => "Bearer #{conn.access_token}" }
    {
      "top_artists"     => paginate("https://api.spotify.com/v1/me/top/artists?limit=50", headers, key: "next"),
      "top_tracks"      => paginate("https://api.spotify.com/v1/me/top/tracks?limit=50", headers, key: "next"),
      "recently_played" => http_get("https://api.spotify.com/v1/me/player/recently-played?limit=50", headers)
    }
  end

  # ── Facebook — posts since last_sync ──
  def fetch_facebook(conn, since:)
    fields = "id,message,story,created_time,type"
    url = "https://graph.facebook.com/me/posts?fields=#{fields}&limit=50" \
          "&access_token=#{conn.access_token}"
    url += "&since=#{Time.parse(since).to_i}" if since.present?
    {
      "profile" => http_get("https://graph.facebook.com/me?fields=id,name,email,about,birthday&access_token=#{conn.access_token}"),
      "posts"   => paginate_fb(url)
    }
  end

  # ── Twitter — timeline since_id with token pagination ──
  def fetch_twitter(conn, since:)
    headers = { "Authorization" => "Bearer #{conn.access_token}" }
    me = http_get("https://api.twitter.com/2/users/me", headers)
    user_id = me.dig("data", "id") || conn.external_user_id
    return { "me" => me } unless user_id.present?

    url = "https://api.twitter.com/2/users/#{user_id}/tweets?max_results=100" \
          "&tweet.fields=created_at,public_metrics,lang"
    url += "&start_time=#{CGI.escape(since)}" if since.present?

    {
      "me"     => me,
      "tweets" => paginate_twitter(url, headers)
    }
  end

  # ── HTTP helpers ──────────────────────────────────────────────────────

  def paginate(start_url, headers, key:)
    items = []
    url   = start_url
    MAX_PAGES.times do
      r = http_get_raw(url, headers)
      body = r.parsed_response
      items.concat(Array(body["items"]))
      url = body[key]
      break if url.blank?
    end
    items
  end

  def paginate_fb(start_url)
    items = []
    url   = start_url
    MAX_PAGES.times do
      r = http_get_raw(url)
      body = r.parsed_response
      items.concat(Array(body["data"]))
      url = body.dig("paging", "next")
      break if url.blank?
    end
    items
  end

  def paginate_twitter(start_url, headers)
    items = []
    url   = start_url
    MAX_PAGES.times do
      r = http_get_raw(url, headers)
      body = r.parsed_response
      items.concat(Array(body["data"]))
      next_token = body.dig("meta", "next_token")
      break if next_token.blank?
      url = start_url.include?("?") ? "#{start_url}&pagination_token=#{next_token}" : "#{start_url}?pagination_token=#{next_token}"
    end
    items
  end

  # Plain GET returning parsed body; respects Retry-After once.
  def http_get(url, headers = {})
    r = http_get_raw(url, headers)
    r.code == 200 ? r.parsed_response : { "error" => r.code, "body" => r.body.to_s[0, 500] }
  end

  # Raw GET with one Retry-After wait on 429.
  def http_get_raw(url, headers = {})
    r = HTTParty.get(url, headers: headers, timeout: 10)
    if r.code == 429
      wait = (r.headers["Retry-After"] || BACKOFF_DEFAULT).to_f
      Rails.logger.warn("FetchSocialDataJob: 429 from #{url}, sleeping #{wait}s")
      sleep [wait, 30.0].min
      r = HTTParty.get(url, headers: headers, timeout: 10)
    end
    r
  end
end
