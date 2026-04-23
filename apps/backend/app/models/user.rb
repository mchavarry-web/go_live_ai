class User < ApplicationRecord
  include UserImageUploader::Attachment(:user_image)

  # Include default devise modules. Others available are:
  # :confirmable, :lockable, :timeoutable, :omniauthable
  devise :database_authenticatable, :registerable,
         :recoverable, :rememberable, :validatable, :trackable

  # Multi-role associations
  has_many :user_roles, dependent: :destroy
  has_many :roles, through: :user_roles

  validates :phone_number, uniqueness: true, allow_blank: true

  # Helper methods for roles
  def admin?
    has_role?(:administrator)
  end

  def client?
    has_role?(:client)
  end

  def emergency_contact?
    has_role?(:emergency_contact)
  end

  def has_role?(role_name)
    roles.exists?(name: role_name.to_s)
  end

  def add_role(role_name)
    role = Role.find_by(name: role_name.to_s)
    roles << role unless roles.include?(role) || role.nil?
  end

  def remove_role(role_name)
    role = Role.find_by(name: role_name.to_s)
    roles.delete(role) if role
  end

  def name
    if first_name.present? || last_name.present?
      "#{first_name} #{last_name}".strip
    else
      email.split("@").first.humanize
    end
  end

  def avatar_initials
    if name.present?
      name.split(" ").map(&:first).first(2).join.upcase
    else
      email.first.upcase
    end
  end

  # Avatar helper method
  def avatar_url(size = :thumb)
    if user_image.present?
      user_image_url(size)
    else
      nil # Return nil to allow fallback to initials
    end
  end
end
