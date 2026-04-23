class Api::V1::Mobile::SessionsController < Api::V1::BaseController
  skip_before_action :authenticate_api_user!, only: [:create]

  def create
    user = User.find_by(email: params[:email]&.downcase&.strip)

    if user&.valid_password?(params[:password])
      # Complete login without 2FA (simplified for admin panel)
      complete_login(user)
    else
      render_error("Email o contraseña inválidos", :unauthorized)
    end
  end

  def show
    render_success({
      user: user_json(current_user)
    })
  end

  def destroy
    # JWT tokens are stateless, so logout is handled on client side
    render_success({ message: 'Sesión cerrada exitosamente' })
  end

  private

  def complete_login(user)
    token = generate_jwt_token(user)
    refresh_token = generate_refresh_token(user)

    render_success({
      user: user_json(user),
      token: token,
      refresh_token: refresh_token,
      expires_at: 90.days.from_now
    })
  end

  def generate_jwt_token(user)
    payload = {
      user_id: user.id,
      email: user.email,
      roles: user.roles.pluck(:name),
      exp: 90.days.from_now.to_i,
      type: "access"
    }
    JWT.encode(payload, Rails.application.secret_key_base, "HS256")
  end

  def generate_refresh_token(user)
    payload = {
      user_id: user.id,
      exp: 30.days.from_now.to_i,
      type: "refresh"
    }
    JWT.encode(payload, Rails.application.secret_key_base, "HS256")
  end

  def user_json(user)
    {
      id: user.id,
      email: user.email,
      first_name: user.first_name,
      last_name: user.last_name,
      phone_number: user.phone_number,
      roles: user.roles.pluck(:name),
      created_at: user.created_at,
      updated_at: user.updated_at
    }
  end
end
