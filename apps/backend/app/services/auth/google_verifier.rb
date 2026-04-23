# frozen_string_literal: true

# Verifies a Google ID token obtained client-side by
# @react-native-google-signin/google-signin. Returns a normalised
# { provider:, provider_uid:, email:, name: } hash on success.
#
# See https://developers.google.com/identity/sign-in/android/backend-auth
module Auth
  class GoogleVerifier
    JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
    ISSUERS  = %w[https://accounts.google.com accounts.google.com].freeze

    def self.call(id_token)
      new.call(id_token)
    end

    def initialize
      @jwks = JwksVerifier.new(
        jwks_url:  JWKS_URL,
        audience:  ENV.fetch("GOOGLE_OAUTH_CLIENT_ID"),
        issuer:    ISSUERS, # jwt gem accepts an array
        cache_key: "auth/google/jwks"
      )
    end

    def call(id_token)
      claims = @jwks.verify!(id_token)
      {
        provider:       "google",
        provider_uid:   claims.fetch(:sub),
        email:          claims[:email]&.downcase,
        name:           claims[:name],
        email_verified: claims[:email_verified]
      }
    end
  end
end
