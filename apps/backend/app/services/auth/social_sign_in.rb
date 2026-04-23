# frozen_string_literal: true

# Takes a normalised claim hash from a provider verifier and finds-or-creates
# the corresponding User. Uses `provider + provider_uid` as the strong key;
# email is a fallback for linking.
module Auth
  class SocialSignIn
    class Error < StandardError; end

    def self.call(claims)
      new(claims).call
    end

    def initialize(claims)
      @claims = claims
    end

    def call
      user = User.find_by(provider: provider, provider_uid: provider_uid)
      return user if user

      # Fall back to email match so a user who signed up with email can link a provider later.
      user = User.find_by(email: email) if email.present?
      if user
        user.update!(provider: provider, provider_uid: provider_uid)
        return user
      end

      raise Error, "provider did not return an email" if email.blank?

      User.create!(
        email:    email,
        password: SecureRandom.base58(24), # random; social users never log in with password
        provider: provider,
        provider_uid: provider_uid,
        first_name: first_name,
        last_name:  last_name
      )
    end

    private

    def provider      = @claims.fetch(:provider)
    def provider_uid  = @claims.fetch(:provider_uid).to_s
    def email         = @claims[:email]

    def first_name
      @claims[:name]&.split(" ", 2)&.first
    end

    def last_name
      @claims[:name]&.split(" ", 2)&.last
    end
  end
end
