# frozen_string_literal: true

# Onboarding captures the minimum facts the avatar needs before it can talk
# in the user's voice: country (→ dialect catalog), timezone (→ proactive
# skill franja), optional formality_level. The actual questionnaire content
# lives on the mobile side; this endpoint just persists the answers.
#
#   GET    /api/v1/onboarding/status   → { completed, country, timezone, formality_level }
#   POST   /api/v1/onboarding/complete → persists + marks complete
#   POST   /api/v1/onboarding/reset    → clears onboarding_completed_at (for dev)
class Api::V1::OnboardingController < Api::V1::BaseController
  def status
    render_success(
      completed:       current_user.onboarded?,
      country:         current_user.country,
      timezone:        current_user.timezone,
      formality_level: current_user.formality_level
    )
  end

  def complete
    current_user.assign_attributes(onboarding_params)
    current_user.onboarding_completed_at = Time.current
    if current_user.save
      render_success(
        completed:       true,
        country:         current_user.country,
        timezone:        current_user.timezone,
        formality_level: current_user.formality_level
      )
    else
      render_error(current_user.errors.full_messages.join(", "), :unprocessable_entity)
    end
  end

  def reset
    current_user.update!(onboarding_completed_at: nil)
    render_success(completed: false)
  end

  private

  def onboarding_params
    params.permit(:country, :timezone, :formality_level)
  end
end
