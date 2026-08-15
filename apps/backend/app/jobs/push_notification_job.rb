# frozen_string_literal: true

# Sends a push via FCM HTTP v1
# (POST https://fcm.googleapis.com/v1/projects/<project-id>/messages:send),
# authenticating with an OAuth2 service-account Bearer token (googleauth gem,
# scope firebase.messaging). The legacy /fcm/send + FCM_SERVER_KEY endpoint
# was shut down by Google and is gone from this job.
#
# Credentials (checked lazily, authorizer memoized per process):
#   - GOOGLE_APPLICATION_CREDENTIALS — path to a service-account JSON file, or
#   - FCM_SERVICE_ACCOUNT_JSON       — the service-account JSON inline.
# Project id comes from the JSON's `project_id`, overridable via FCM_PROJECT_ID.
#
# When neither credential env var is set (dev) the job logs + no-ops, so we
# don't need an FCM project just to exercise the pipeline.
#
# Dead tokens: v1 signals them as 404 UNREGISTERED (or 400 INVALID_ARGUMENT
# with an FcmError detail) — the job deactivates the DeviceToken so we don't
# keep targeting dead installs.
class PushNotificationJob < ApplicationJob
  queue_as :default

  FCM_SCOPE    = "https://www.googleapis.com/auth/firebase.messaging"
  FCM_V1_HOST  = "https://fcm.googleapis.com"
  DEAD_TOKEN_ERROR_CODES = %w[UNREGISTERED INVALID_ARGUMENT].freeze

  AUTHORIZER_MUTEX = Mutex.new

  class << self
    # Memoized per process; googleauth caches the access token internally and
    # we refresh it via fetch_access_token! only when missing/near expiry.
    def authorizer
      AUTHORIZER_MUTEX.synchronize { @authorizer ||= build_authorizer }
    end

    def credentials_configured?
      ENV["FCM_SERVICE_ACCOUNT_JSON"].present? || ENV["GOOGLE_APPLICATION_CREDENTIALS"].present?
    end

    private

    def build_authorizer
      require "googleauth"

      json_io =
        if ENV["FCM_SERVICE_ACCOUNT_JSON"].present?
          StringIO.new(ENV.fetch("FCM_SERVICE_ACCOUNT_JSON"))
        else
          File.open(ENV.fetch("GOOGLE_APPLICATION_CREDENTIALS"))
        end

      Google::Auth::ServiceAccountCredentials.make_creds(
        json_key_io: json_io,
        scope:       FCM_SCOPE
      )
    ensure
      json_io.close if json_io.is_a?(File)
    end
  end

  def perform(device_token_id:, title:, body:, data: {})
    dt = DeviceToken.find_by(id: device_token_id)
    return unless dt&.active?

    unless self.class.credentials_configured?
      Rails.logger.info("PushNotificationJob: FCM service-account credentials not set — skipping push to #{dt.platform}/#{dt.token[0, 10]}...")
      return
    end

    message = {
      token:        dt.token,
      notification: { title: title, body: body }
    }
    # v1 requires every data value to be a string.
    stringified_data = (data || {}).to_h.map { |k, v| [ k.to_s, v.to_s ] }.to_h
    message[:data] = stringified_data if stringified_data.any?

    response = HTTParty.post(
      "#{FCM_V1_HOST}/v1/projects/#{project_id}/messages:send",
      headers: {
        "Authorization" => "Bearer #{access_token}",
        "Content-Type"  => "application/json"
      },
      body:    { message: message }.to_json,
      timeout: 10
    )

    handle_response(dt, response)
  end

  private

  def project_id
    ENV["FCM_PROJECT_ID"].presence || self.class.authorizer.project_id ||
      raise(KeyError, "FCM project id missing: set FCM_PROJECT_ID or use a service-account JSON with project_id")
  end

  def access_token
    auth = self.class.authorizer
    auth.fetch_access_token! if auth.access_token.nil? || auth.expires_within?(60)
    auth.access_token
  end

  def handle_response(dt, response)
    body = response.parsed_response

    if response.code == 200
      Rails.logger.info("PushNotificationJob: sent (name=#{body.is_a?(Hash) ? body['name'] : body.to_s[0, 120]})")
      return
    end

    error_code = fcm_error_code(body)
    if (response.code == 404 && (error_code == "UNREGISTERED" || error_status(body) == "NOT_FOUND")) ||
       (response.code == 400 && DEAD_TOKEN_ERROR_CODES.include?(error_code))
      dt.deactivate!
      Rails.logger.info("PushNotificationJob: token unregistered — deactivated #{dt.platform}/#{dt.token[0, 10]}...")
    else
      Rails.logger.warn("PushNotificationJob: FCM v1 responded HTTP #{response.code}: #{body.to_s[0, 300]}")
    end
  end

  def error_status(body)
    body.is_a?(Hash) ? body.dig("error", "status") : nil
  end

  # v1 error payloads carry the FCM-specific code in
  # error.details[] entries of @type ...google.firebase.fcm.v1.FcmError.
  def fcm_error_code(body)
    details = body.is_a?(Hash) ? body.dig("error", "details") : nil
    return nil unless details.is_a?(Array)

    fcm_detail = details.find { |d| d.is_a?(Hash) && d["@type"].to_s.end_with?("FcmError") }
    fcm_detail&.[]("errorCode")
  end
end
