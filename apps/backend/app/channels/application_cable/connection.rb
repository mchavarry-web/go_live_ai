# frozen_string_literal: true

# ActionCable connection handler. Authenticates the WebSocket handshake using
# the same JWT strategy as the REST API (secret_key_base, HS256). The Expo
# client passes the token as a `?token=<jwt>` query param.
module ApplicationCable
  class Connection < ActionCable::Connection::Base
    identified_by :current_user

    def connect
      self.current_user = find_verified_user
    end

    private

    def find_verified_user
      token = request.params[:token]
      reject_unauthorized_connection if token.blank?

      decoded = JWT.decode(
        token,
        Rails.application.secret_key_base,
        true,
        { algorithm: "HS256" }
      )
      User.find(decoded.first["user_id"])
    rescue JWT::DecodeError, ActiveRecord::RecordNotFound
      reject_unauthorized_connection
    end
  end
end
