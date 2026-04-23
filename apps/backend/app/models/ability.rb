# frozen_string_literal: true

class Ability
  include CanCan::Ability

  def initialize(user)
    user ||= User.new

    if user.admin?
      can :manage, :all
    else
      can %i[read update], User,   id: user.id
      can %i[read update], Avatar, user_id: user.id
    end
  end
end
