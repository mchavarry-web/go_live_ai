class Admin::AdminController < ApplicationController
  before_action :authenticate_user!
  before_action :ensure_admin!

  layout 'admin'

  private

  def ensure_admin!
    unless current_user.admin?
      redirect_to root_path, alert: 'No tienes permisos para acceder a esta sección'
    end
  end

  def current_ability
    @current_ability ||= Ability.new(current_user)
  end
end
