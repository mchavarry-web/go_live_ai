class Api::V1::BaseController < ApplicationController
  protect_from_forgery with: :null_session
  before_action :authenticate_api_user!

  respond_to :json

  private

  def authenticate_api_user!
    token = request.headers['Authorization']&.split(' ')&.last

    if token.blank?
      render json: { error: 'Token missing' }, status: :unauthorized
      return
    end

    begin
      payload = JWT.decode(token, Rails.application.secret_key_base, true, { algorithm: 'HS256' }).first
      if payload["jti"] && JwtDenylist.denylisted?(payload["jti"])
        render json: { error: 'Token revoked' }, status: :unauthorized
        return
      end
      @current_user   = User.find(payload["user_id"])
      @current_payload = payload
    rescue JWT::DecodeError, ActiveRecord::RecordNotFound
      render json: { error: 'Invalid token' }, status: :unauthorized
    end
  end

  def current_user
    @current_user
  end

  def render_error(message, status = :unprocessable_entity)
    render json: { error: message }, status: status
  end

  def render_success(data, status = :ok)
    render json: data, status: status
  end
end
