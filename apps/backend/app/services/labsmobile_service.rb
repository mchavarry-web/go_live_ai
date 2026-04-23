class LabsmobileService
  class << self
    API_ENDPOINT = "https://api.labsmobile.com/json/send".freeze

    def send_sms(to_phone, message)
      return log_dev_sms(to_phone, message) unless labsmobile_configured?

      begin
        normalized_phone = normalize_phone_number(to_phone)

        response = make_request(normalized_phone, message)
        result = JSON.parse(response.body)

        if result["code"] == "0"
          Rails.logger.info "[LabsMobile] SMS sent successfully to #{normalized_phone}"
          true
        else
          Rails.logger.error "[LabsMobile] SMS Error: #{result['message']} (code: #{result['code']})"
          false
        end
      rescue JSON::ParserError => e
        Rails.logger.error "[LabsMobile] Response Parse Error: #{e.message}"
        false
      rescue => e
        Rails.logger.error "[LabsMobile] Service Error: #{e.message}"
        false
      end
    end

    def send_otp(phone, otp_code)
      message = "Tu codigo de verificacion es: #{otp_code}. Valido por 10 minutos. No compartas este codigo."
      send_sms(phone, message)
    end

    def send_password_reset(phone, reset_url)
      message = "Para restablecer tu contraseña ingresa a: #{reset_url}"
      send_sms(phone, message)
    end

    def labsmobile_configured?
      username.present? && token_api.present?
    end

    private

    def log_dev_sms(phone, message)
      Rails.logger.warn "[LabsMobile] (dev mode) SMS would be sent:"
      Rails.logger.warn "[LabsMobile] To: #{phone}"
      Rails.logger.warn "[LabsMobile] Message: #{message}"
      true
    end

    def make_request(phone, message)
      uri = URI(API_ENDPOINT)
      https = Net::HTTP.new(uri.host, uri.port)
      https.use_ssl = true

      # Skip SSL verification in development (CRL check fails on some systems)
      if Rails.env.development?
        https.verify_mode = OpenSSL::SSL::VERIFY_NONE
      end

      request = Net::HTTP::Post.new(uri)
      request["Content-Type"] = "application/json"
      request["Authorization"] = "Basic #{auth_credentials}"
      request.body = JSON.dump({
        message: message,
        tpoa: sender_name,
        recipient: [
          { msisdn: phone.delete("+") }
        ]
      })

      https.request(request)
    end

    def auth_credentials
      Base64.strict_encode64("#{username}:#{token_api}")
    end

    def username
      Rails.application.credentials.labsmobile&.dig(:username) || ENV["LABSMOBILE_USERNAME"]
    end

    def token_api
      Rails.application.credentials.labsmobile&.dig(:token_api) || ENV["LABSMOBILE_API_TOKEN"]
    end

    def sender_name
      Rails.application.credentials.labsmobile&.dig(:sender_name) || ENV["LABSMOBILE_SENDER_NAME"] || "MyApp"
    end

    def normalize_phone_number(phone)
      # Remove all non-digit characters except +
      cleaned = phone.gsub(/[^\d+]/, "")

      # If phone doesn't start with +, assume it's a Peruvian number and add +51
      if cleaned.match?(/^\d{9}$/) # 9-digit local number
        "+51#{cleaned}"
      elsif cleaned.start_with?("+")
        cleaned
      elsif cleaned.length == 11 && cleaned.start_with?("51") # 11 digits starting with 51
        "+#{cleaned}"
      else
        cleaned # Return as-is if we can't normalize
      end
    end
  end
end
