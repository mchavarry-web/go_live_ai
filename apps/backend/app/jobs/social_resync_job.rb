# frozen_string_literal: true

# Weekly re-sync of connected social platforms so imported data does not go
# permanently stale after the initial connect (DEV-99). Scheduled Sundays at
# 03:00 via Whenever (config/schedule.rb).
#
# Per-provider behavior:
#
#   spotify   — enqueue FetchSocialDataJob for every connection that can
#               still authenticate: either a refresh_token is stored
#               (FetchSocialDataJob#ensure_fresh_token! auto-refreshes the
#               access token against accounts.spotify.com before fetching)
#               or the current access token has not expired yet. Connections
#               with no refresh token AND a past expires_at are marked
#               metadata.stale = true instead of fetching.
#
#   facebook, — tokens are pasted by the client (see the /ingest actions) and
#   twitter     cannot be refreshed server-side: there is no OAuth app flow
#               wired for these providers yet. If expires_at has passed we
#               mark metadata.stale = true — the app then shows "Vuelve a
#               conectar tu cuenta" — instead of burning a fetch that would
#               401. A missing expires_at is treated as still-valid (Twitter
#               bearer tokens are stored without an expiry).
#
#   instagram — skipped entirely: ingestion is upload-based (there is no
#               server-side token to fetch with); users re-upload their
#               archive to refresh data.
#
# A later successful FetchSocialDataJob run clears the stale flag. All
# metadata writes here are non-destructive merges — metadata is a jsonb
# grab-bag shared with raw_data / profile fields.
class SocialResyncJob < ApplicationJob
  queue_as :low

  RESYNC_PROVIDERS = %w[spotify facebook twitter].freeze

  def perform
    SocialConnection.where(provider: RESYNC_PROVIDERS).find_each do |conn|
      if resyncable?(conn)
        FetchSocialDataJob.perform_later(user_id: conn.user_id, provider: conn.provider)
      else
        mark_stale!(conn)
      end
    rescue StandardError => e
      Rails.logger.warn("[social-resync] failed user=#{conn.user_id} " \
                        "provider=#{conn.provider} #{e.class}: #{e.message}")
    end
  end

  private

  def resyncable?(conn)
    case conn.provider
    when "spotify"
      # FetchSocialDataJob refreshes the access token itself when a
      # refresh_token exists; otherwise the current token must still be live.
      conn.refresh_token.present? || conn.active?
    else
      # facebook / twitter — no server-side refresh; expires_at nil counts
      # as active (SocialConnection#active?).
      conn.active?
    end
  end

  def mark_stale!(conn)
    return if conn.metadata["stale"] == true

    conn.update!(
      metadata: conn.metadata.merge(
        "stale"           => true,
        "stale_marked_at" => Time.current.iso8601
      )
    )
    Rails.logger.info("[social-resync] marked stale user=#{conn.user_id} provider=#{conn.provider}")
  end
end
