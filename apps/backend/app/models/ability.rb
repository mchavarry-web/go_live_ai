# frozen_string_literal: true

class Ability
  include CanCan::Ability

  def initialize(user)
    user ||= User.new # guest user (not logged in)

    if user.admin?
      # Administrators can manage everything
      can :manage, :all
    else
      # Basic read access for authenticated users
      can :read, User, id: user.id
    end
  end
end
