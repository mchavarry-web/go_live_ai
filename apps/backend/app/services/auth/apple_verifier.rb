# frozen_string_literal: true

# Verifies an Apple ID token from expo-apple-authentication.
# See https://developer.apple.com/documentation/sign_in_with_apple/verifying_a_user
module Auth
  class AppleVerifier
    JWKS_URL = "https://appleid.apple.com/auth/keys"
    ISSUER   = "https://appleid.apple.com"

    def self.call(id_token)
      new.call(id_token)
    end

    def initialize
      @jwks = JwksVerifier.new(
        jwks_url:  JWKS_URL,
        # Apple sets `aud` to the Service ID (web) or Bundle ID (native). The
        # Expo app is native, so we use the bundle / service id here; rotate
        # via env.
        audience:  ENV.fetch("APPLE_OAUTH_SERVICE_ID"),
        issuer:    ISSUER,
        cache_key: "auth/apple/jwks"
      )
    end

    def call(id_token)
      claims = @jwks.verify!(id_token)
      {
        provider:       "apple",
        provider_uid:   claims.fetch(:sub),
        email:          claims[:email]&.downcase,
        name:           nil, # Apple never returns the name in the id_token; Expo passes it separately
        email_verified: claims[:email_verified] == "true" || claims[:email_verified] == true
      }
    end
  end
end
