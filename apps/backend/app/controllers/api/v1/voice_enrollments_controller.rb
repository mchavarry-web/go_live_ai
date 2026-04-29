# frozen_string_literal: true

# Trigger-phrase enrollment. Phase 1 stores the audio + transcribed text;
# Phase 2 will compute and persist a voice embedding into FastAPI pgvector.
#
# Both phrase clips are required to mark the enrollment ready, since the
# Phase 1 plan is "no skip". The Voice Enrollment Screen on the client
# uploads each phrase's audio + its transcribed text in a single PATCH/PUT
# of this controller.
class Api::V1::VoiceEnrollmentsController < Api::V1::BaseController
  def show
    enrollment = current_user.voice_enrollment
    if enrollment.nil?
      render_success(enrollment: { status: "pending" })
      return
    end
    render_success(enrollment: payload(enrollment))
  end

  def create
    enrollment = current_user.voice_enrollment || current_user.build_voice_enrollment
    enrollment.start_phrase_audio = params[:start_phrase] if params[:start_phrase].present?
    enrollment.stop_phrase_audio  = params[:stop_phrase]  if params[:stop_phrase].present?
    enrollment.start_phrase_text  = params[:start_phrase_text] if params.key?(:start_phrase_text)
    enrollment.stop_phrase_text   = params[:stop_phrase_text]  if params.key?(:stop_phrase_text)

    both_clips_present = enrollment.start_phrase_audio_data.present? && enrollment.stop_phrase_audio_data.present?
    enrollment.status = both_clips_present ? "ready" : "pending"

    enrollment.save!
    render_success({ enrollment: payload(enrollment) }, :created)
  rescue ActiveRecord::RecordInvalid => e
    render_error(e.record.errors.full_messages.join(", "), :unprocessable_entity)
  end

  def destroy
    current_user.voice_enrollment&.destroy
    render_success(deleted: true)
  end

  private

  def payload(enrollment)
    {
      status:             enrollment.status,
      start_phrase_text:  enrollment.start_phrase_text,
      stop_phrase_text:   enrollment.stop_phrase_text,
      has_start_audio:    enrollment.start_phrase_audio_data.present?,
      has_stop_audio:     enrollment.stop_phrase_audio_data.present?
    }
  end
end
