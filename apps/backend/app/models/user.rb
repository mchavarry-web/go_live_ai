class User < ApplicationRecord
  include UserImageUploader::Attachment(:user_image)

  # Include default devise modules. Others available are:
  # :confirmable, :lockable, :timeoutable, :omniauthable
  devise :database_authenticatable, :registerable,
         :recoverable, :rememberable, :validatable, :trackable

  # ── Associations ──────────────────────────────────────────────────────
  has_many :user_roles, dependent: :destroy
  has_many :roles, through: :user_roles
  has_one  :avatar,  dependent: :destroy
  has_many :conversations, dependent: :destroy
  has_many :messages, through: :conversations
  has_many :social_connections, dependent: :destroy

  after_create :ensure_default_role_and_avatar

  # ── Enums ─────────────────────────────────────────────────────────────
  FORMALITY_LEVELS = %w[formal neutral informal].freeze
  PROVIDERS        = %w[email google apple facebook].freeze

  validates :phone_number, uniqueness: true, allow_blank: true
  validates :formality_level, inclusion: { in: FORMALITY_LEVELS }, allow_nil: true
  validates :provider,        inclusion: { in: PROVIDERS },        allow_nil: true
  validates :country, length: { is: 2 }, allow_blank: true
  validates :provider_uid, uniqueness: { scope: :provider }, allow_blank: true

  # ── Role helpers ─────────────────────────────────────────────────────
  def admin?
    has_role?(:administrator)
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

  # User profile image URL (not to be confused with the AI `avatar` association).
  def user_image_display_url(size = :thumb)
    user_image.present? ? user_image_url(size) : nil
  end

  # ── Onboarding ────────────────────────────────────────────────────────
  def onboarded?
    onboarding_completed_at.present?
  end

  private

  def ensure_default_role_and_avatar
    add_role(:user) if roles.empty?
    Avatar.create!(user: self) unless avatar
  end
end
