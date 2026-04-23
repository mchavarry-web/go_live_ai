# LabsMobile Configuration
# This initializer ensures LabsMobile credentials are properly loaded at startup
# and provides helpful error messages if they're missing

if Rails.application.credentials.labsmobile&.dig(:username).present? ||
   ENV["LABSMOBILE_USERNAME"].present?

  Rails.logger.debug "LabsMobile SMS service configured and ready"

else
  Rails.logger.debug "LabsMobile SMS service not configured. SMS will be logged to console in development."
  Rails.logger.debug "Add LABSMOBILE_USERNAME, LABSMOBILE_API_TOKEN, and optionally LABSMOBILE_SENDER_NAME to your environment variables."
end
