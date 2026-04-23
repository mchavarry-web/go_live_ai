# frozen_string_literal: true

class Users::PasswordsController < Devise::PasswordsController
  # Use no layout for mobile-friendly standalone pages
  layout false, only: [:edit, :update]

  # PUT /users/password
  def update
    self.resource = resource_class.reset_password_by_token(resource_params)
    yield resource if block_given?

    if resource.errors.empty?
      resource.unlock_access! if unlockable?(resource)
      # Don't sign in the user - just show success page
      # Mobile users should go back to the app to login
      render :reset_success and return
    else
      set_minimum_password_length
      respond_with resource
    end
  end

  protected

  def after_resetting_password_path_for(resource)
    root_path
  end
end
