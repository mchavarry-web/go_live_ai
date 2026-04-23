# frozen_string_literal: true

# Base class for verifying a provider ID token signed with RS256 via JWKS.
#
# Google and Apple both publish their signing keys at a JWKS endpoint and
# rotate them periodically. We cache the JWKS payload in Rails.cache for
# one hour; if verification fails due to "key not found" we refetch once
# (to handle mid-rotation requests).
module Auth
  class JwksVerifier
    class VerificationError < StandardError; end

    JWKS_CACHE_TTL = 1.hour

    def initialize(jwks_url:, audience:, issuer:, cache_key:)
      @jwks_url  = jwks_url
      @audience  = audience
      @issuer    = issuer
      @cache_key = cache_key
    end

    # @param id_token [String] the provider-signed JWT
    # @return [Hash] the decoded claims (symbolized) on success
    # @raise [VerificationError] on any failure
    def verify!(id_token)
      begin
        return decode(id_token, fetch_jwks)
      rescue JWT::VerificationError, JWT::DecodeError
        # key may have rotated — refetch JWKS once and retry exactly once
        decode(id_token, fetch_jwks(force: true))
      end
    rescue JWT::ExpiredSignature
      raise VerificationError, "id token expired"
    rescue JWT::InvalidAudError
      raise VerificationError, "id token audience mismatch"
    rescue JWT::InvalidIssuerError
      raise VerificationError, "id token issuer mismatch"
    rescue StandardError => e
      raise VerificationError, "id token verification failed: #{e.class}: #{e.message}"
    end

    private

    def decode(id_token, jwks)
      payload, _header = JWT.decode(
        id_token,
        nil, # key resolved via jwks below
        true,
        algorithms: ["RS256"],
        iss: @issuer,
        verify_iss: true,
        aud: @audience,
        verify_aud: true,
        jwks: jwks
      )
      payload.symbolize_keys
    end

    def fetch_jwks(force: false)
      Rails.cache.delete(@cache_key) if force
      Rails.cache.fetch(@cache_key, expires_in: JWKS_CACHE_TTL) do
        response = HTTParty.get(@jwks_url, timeout: 5)
        raise VerificationError, "JWKS fetch failed: HTTP #{response.code}" unless response.code == 200
        { keys: response.parsed_response.fetch("keys") }
      end
    end
  end
end
