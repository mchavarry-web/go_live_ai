# frozen_string_literal: true

# OmniAuth callback landing for the web flow. Each provider (Google / Apple /
# Facebook) delivers the user's profile here; we upsert via User.from_omniauth
# and sign_in_and_redirect them as a Devise cookie session.
#
# The mobile API does NOT come through here — it hits
# POST /api/v1/auth/{google,apple,facebook} with a provider-issued ID token
# and gets back a Rails JWT (see Api::V1::AuthController).
class Users::OmniauthCallbacksController < Devise::OmniauthCallbacksController
  def google_oauth2 = handle(:google_oauth2, "Google")
  def apple         = handle(:apple,         "Apple")
  def facebook      = handle(:facebook,      "Facebook")

  def failure
    redirect_to new_user_session_path, alert: "No se pudo completar el inicio de sesión."
  end

  private

  def handle(provider_key, display_name)
    user = User.from_omniauth(request.env["omniauth.auth"])
    if user.persisted?
      sign_in_and_redirect user, event: :authentication
      set_flash_message(:notice, :success, kind: display_name) if is_flashing_format?
    else
      session["devise.#{provider_key}_data"] = request.env["omniauth.auth"].except("extra")
      redirect_to new_user_registration_url, alert: user.errors.full_messages.join(", ")
    end
  end
end
