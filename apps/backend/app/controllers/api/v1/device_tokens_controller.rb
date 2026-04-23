# frozen_string_literal: true

# Device-token management for FCM push notifications.
#
#   POST   /api/v1/notifications/device_tokens
#          { token, platform: "ios"|"android"|"web", metadata: {...} }
#   DELETE /api/v1/notifications/device_tokens/:token
#   POST   /api/v1/notifications/test   (dev-only: fires a test push)
class Api::V1::DeviceTokensController < Api::V1::BaseController
  def create
    token    = params.require(:token)
    platform = params.require(:platform)

    record = DeviceToken.find_or_initialize_by(token: token)
    # If the token moved to a different user (reinstall, handoff), reassign.
    record.user     = current_user
    record.platform = platform
    record.metadata = (record.metadata || {}).merge(metadata_params)
    record.active   = true
    record.save!

    render json: { device_token: serialize(record) }, status: :created
  rescue ActiveRecord::RecordInvalid, ActionController::ParameterMissing => e
    render_error(e.message, :unprocessable_entity)
  end

  def destroy
    record = current_user.device_tokens.find_by(token: params[:token])
    return render_error("token not found", :not_found) unless record
    record.deactivate!
    head :no_content
  end

  # Dev-only smoke test: enqueues a push to all active tokens for current_user.
  def test
    return render_error("not allowed in production", :forbidden) if Rails.env.production?

    current_user.device_tokens.active.each do |dt|
      PushNotificationJob.perform_later(
        device_token_id: dt.id,
        title: "Prueba",
        body:  "Test push from /notifications/test",
        data:  { kind: "test" }
      )
    end
    render json: { enqueued: current_user.device_tokens.active.count }, status: :accepted
  end

  private

  # Allow any free-form metadata hash from the client — device-specific
  # diagnostics (model, os_version, app_version, locale) aren't known in
  # advance so we opt into permitting whatever arrives.
  def metadata_params
    raw = params[:metadata]
    return {} if raw.blank?
    (raw.respond_to?(:to_unsafe_h) ? raw.to_unsafe_h : raw.to_h).transform_keys(&:to_s)
  end

  def serialize(t)
    { id: t.id, token: t.token, platform: t.platform, active: t.active, metadata: t.metadata,
      created_at: t.created_at.iso8601 }
  end
end
