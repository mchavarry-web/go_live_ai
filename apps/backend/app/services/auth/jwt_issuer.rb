# frozen_string_literal: true

# Centralised JWT issuance + decoding for the API. Every access token now
# carries a `jti` (UUID) so we can revoke it on sign-out; revocation lives
# in JwtDenylist.
module Auth
  module JwtIssuer
    # Sessions are intentionally long-lived (10 years) so users effectively
    # never get logged out by expiry. Invalid/revoked tokens still fail to
    # decode and trigger the client's silent redirect-to-login path.
    ACCESS_TTL  = 10.years
    REFRESH_TTL = 10.years
    ALG         = "HS256"

    module_function

    def access_token(user)
      exp = ACCESS_TTL.from_now.to_i
      jti = SecureRandom.uuid
      encode(user_id: user.id, role: user.role, jti: jti, exp: exp, type: "access")
    end

    def refresh_token(user)
      encode(user_id: user.id, jti: SecureRandom.uuid, exp: REFRESH_TTL.from_now.to_i, type: "refresh")
    end

    def decode!(token)
      JWT.decode(token, Rails.application.secret_key_base, true, algorithm: ALG).first
    end

    def encode(payload)
      JWT.encode(payload, Rails.application.secret_key_base, ALG)
    end

    # Denylist the jti of an access token until its natural exp. Idempotent.
    def revoke!(payload)
      return unless payload["jti"] && payload["exp"]
      JwtDenylist.find_or_create_by!(jti: payload["jti"]) do |row|
        row.exp = Time.at(payload["exp"].to_i)
      end
    end
  end
end
