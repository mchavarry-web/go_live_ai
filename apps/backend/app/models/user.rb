class User < ApplicationRecord
  include UserImageUploader::Attachment(:user_image)

  # Devise — email + password + OAuth (Google / Apple / Facebook via omniauth).
  devise :database_authenticatable, :registerable,
         :recoverable, :rememberable, :validatable, :trackable,
         :omniauthable, omniauth_providers: %i[google_oauth2 apple facebook]

  # ── Associations ──────────────────────────────────────────────────────
  has_one  :avatar,           dependent: :destroy
  has_many :conversations,    dependent: :destroy
  has_many :messages,         through:   :conversations
  has_many :social_connections, dependent: :destroy
  has_many :device_tokens,    dependent: :destroy

  after_create :ensure_avatar

  # ── Enums ─────────────────────────────────────────────────────────────
  ROLES            = %w[user administrator].freeze
  FORMALITY_LEVELS = %w[formal neutral informal].freeze
  PROVIDERS        = %w[email google apple facebook].freeze

  validates :phone_number, uniqueness: true, allow_blank: true
  validates :role,            inclusion: { in: ROLES }
  validates :formality_level, inclusion: { in: FORMALITY_LEVELS }, allow_nil: true
  validates :provider,        inclusion: { in: PROVIDERS },        allow_nil: true
  validates :country, length: { is: 2 }, allow_blank: true
  validates :provider_uid, uniqueness: { scope: :provider }, allow_blank: true

  # ── Role helpers (single-role model) ──────────────────────────────────
  def admin?             = role == "administrator"
  def has_role?(r)       = role == r.to_s
  def make_admin!        = update!(role: "administrator")
  def revoke_admin!      = update!(role: "user")

  # ── OmniAuth (web flows; mobile uses /api/v1/auth/* ID-token endpoints) ──
  def self.from_omniauth(auth)
    provider     = omniauth_provider_name(auth.provider)
    provider_uid = auth.uid.to_s
    user = find_by(provider: provider, provider_uid: provider_uid)
    user ||= find_by(email: auth.info.email) if auth.info.email.present?

    if user
      user.update!(provider: provider, provider_uid: provider_uid)
      return user
    end

    create!(
      email:        auth.info.email || "#{provider}_#{provider_uid}@placeholder.golive",
      password:     Devise.friendly_token[0, 20],
      provider:     provider,
      provider_uid: provider_uid,
      first_name:   auth.info.first_name || auth.info.name&.split(" ", 2)&.first,
      last_name:    auth.info.last_name  || auth.info.name&.split(" ", 2)&.last
    )
  end

  def self.omniauth_provider_name(strategy)
    case strategy.to_s
    when "google_oauth2" then "google"
    else strategy.to_s
    end
  end

  # ── Display helpers ──────────────────────────────────────────────────
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

  # Shrine profile image URL. Name kept for compatibility with
  # shared/_user_avatar.html.erb partial in the admin layout.
  def avatar_url(size = :thumb)
    user_image.present? ? user_image_url(size) : nil
  end

  def onboarded? = onboarding_completed_at.present?

  private

  def ensure_avatar
    Avatar.create!(user: self) unless avatar
  end
end
