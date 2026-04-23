class Role < ApplicationRecord
  has_many :user_roles, dependent: :destroy
  has_many :users, through: :user_roles

  validates :name, presence: true, uniqueness: true

  # Predefined roles
  ADMINISTRATOR = 'administrator'
  CLIENT = 'client'
  EMERGENCY_CONTACT = 'emergency_contact'
end
