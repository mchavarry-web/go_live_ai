# frozen_string_literal: true

# Verifies a Facebook access token (not an id_token) by asking the Graph API
# to echo the associated user. If Graph returns 200 we trust the token.
# See https://developers.facebook.com/docs/graph-api/reference/user/
module Auth
  class FacebookVerifier
    class VerificationError < StandardError; end

    GRAPH_URL = "https://graph.facebook.com/me"

    def self.call(access_token)
      new.call(access_token)
    end

    def call(access_token)
      raise VerificationError, "missing access token" if access_token.blank?

      response = HTTParty.get(
        GRAPH_URL,
        query: { access_token: access_token, fields: "id,email,name" },
        timeout: 5
      )

      unless response.code == 200
        raise VerificationError, "facebook rejected token: HTTP #{response.code}"
      end

      body = response.parsed_response
      {
        provider:       "facebook",
        provider_uid:   body.fetch("id"),
        email:          body["email"]&.downcase,
        name:           body["name"],
        email_verified: true # Facebook only returns emails it has verified
      }
    end
  end
end
