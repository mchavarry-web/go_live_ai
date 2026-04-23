# frozen_string_literal: true

# Sends a push via FCM. Uses the legacy /fcm/send endpoint which still
# accepts the `FCM_SERVER_KEY` (matching the old Django service); migrate
# to FCM v1 + service-account auth when credentials are rotated.
#
# When `FCM_SERVER_KEY` is unset (dev) the job logs + no-ops, so we don't
# need an FCM project just to exercise the pipeline.
#
# On a 404 NotRegistered response the job deactivates the token so we
# don't keep targeting dead installs.
class PushNotificationJob < ApplicationJob
  queue_as :default
  FCM_SEND_URL = "https://fcm.googleapis.com/fcm/send"

  def perform(device_token_id:, title:, body:, data: {})
    dt = DeviceToken.find_by(id: device_token_id)
    return unless dt&.active?

    if ENV["FCM_SERVER_KEY"].blank?
      Rails.logger.info("PushNotificationJob: FCM_SERVER_KEY not set — skipping push to #{dt.platform}/#{dt.token[0,10]}...")
      return
    end

    response = HTTParty.post(
      FCM_SEND_URL,
      headers: {
        "Authorization" => "key=#{ENV.fetch('FCM_SERVER_KEY')}",
        "Content-Type"  => "application/json"
      },
      body: {
        to:           dt.token,
        notification: { title: title, body: body },
        data:         data
      }.to_json,
      timeout: 10
    )

    handle_response(dt, response)
  end

  private

  def handle_response(dt, response)
    body = response.parsed_response
    if response.code == 200
      results = body.is_a?(Hash) ? body["results"] : nil
      err = results&.first&.[]("error")
      dt.deactivate! if %w[NotRegistered InvalidRegistration].include?(err)
      Rails.logger.info("PushNotificationJob: sent (status=#{body.is_a?(Hash) && body['success'] == 1 ? 'ok' : err || 'unknown'})")
    else
      Rails.logger.warn("PushNotificationJob: FCM responded HTTP #{response.code}: #{body.to_s[0, 300]}")
    end
  end
end
