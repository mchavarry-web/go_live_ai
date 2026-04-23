# frozen_string_literal: true

# Centralised JWT issuance + decoding for the API. Every token is signed with
# HS256 + Rails.application.secret_key_base. Access tokens live 7 days;
# refresh tokens live 30 days and carry type: "refresh".
module Auth
  module JwtIssuer
    ACCESS_TTL  = 7.days
    REFRESH_TTL = 30.days
    ALG         = "HS256"

    module_function

    def access_token(user)
      encode(user_id: user.id, role: user.role, exp: ACCESS_TTL.from_now.to_i, type: "access")
    end

    def refresh_token(user)
      encode(user_id: user.id, exp: REFRESH_TTL.from_now.to_i, type: "refresh")
    end

    def decode!(token)
      JWT.decode(token, Rails.application.secret_key_base, true, algorithm: ALG).first
    end

    def encode(payload)
      JWT.encode(payload, Rails.application.secret_key_base, ALG)
    end
  end
end
