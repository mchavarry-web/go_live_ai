# frozen_string_literal: true

# DEV-98 — psychological profiling (Humantic AI + Sentino via FastAPI).
#
# Profiling is sensitive, so it is strictly opt-in: both endpoints refuse
# with 403 unless the user's avatar carries
# behavior["psych_profiling_opt_in"] == true (set via the existing
# PATCH /api/v1/avatar, which deep-merges arbitrary behavior keys).
# Absent key = NOT opted in.
#
#   POST /api/v1/profile/psych  → 202, enqueues PsychProfileJob
#   GET  /api/v1/profile/psych  → stored per-provider profiles (proxied)
class Api::V1::PsychProfilesController < Api::V1::BaseController
  OPT_IN_ERROR = "No has activado el perfil psicológico. " \
                 "Actívalo primero desde la configuración de tu avatar."

  before_action :ensure_opted_in!

  # POST /api/v1/profile/psych
  # Optional param: linkedin_url (Humantic can analyze a public profile).
  # The text corpus is built server-side by the job from the user's own
  # messages and audio transcripts — never accepted from the client.
  def create
    PsychProfileJob.perform_later(
      user_id:      current_user.id.to_s,
      linkedin_url: params[:linkedin_url].presence
    )
    render_success(
      { message: "Perfil psicológico en proceso. Estará disponible en unos minutos." },
      :accepted
    )
  end

  # GET /api/v1/profile/psych
  def show
    response = AiAgentsClient.new.psych_profiles(current_user.id.to_s)
    profiles = response.is_a?(Hash) ? (response["profiles"] || {}) : {}
    render_success(profiles: profiles)
  rescue StandardError => e
    Rails.logger.warn("[psych-profile] show failed user=#{current_user.id}: #{e.class}: #{e.message}")
    render_error("No se pudo obtener el perfil psicológico. Intenta de nuevo.", :bad_gateway)
  end

  private

  def ensure_opted_in!
    opted_in = current_user.avatar&.behavior&.dig("psych_profiling_opt_in") == true
    render_error(OPT_IN_ERROR, :forbidden) unless opted_in
  end
end
