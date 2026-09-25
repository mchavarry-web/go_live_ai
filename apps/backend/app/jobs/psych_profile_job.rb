# frozen_string_literal: true

# DEV-98 — psychological profiling via external providers (Humantic AI /
# Sentino), proxied through FastAPI /internal/profile/psych.
#
# Strictly opt-in: runs ONLY when the user's avatar carries
# behavior["psych_profiling_opt_in"] == true (absent = no profiling).
# Env-gated end-to-end: with no provider API keys configured on the
# FastAPI side, the call is a clean no-op (providers report
# "api_key_not_configured" in the errors hash).
#
# The text corpus is built server-side from what the user actually wrote
# or said: the last ~200 user-authored chat messages plus recent finished
# audio-chunk transcripts (the user's own voice journal).
class PsychProfileJob < ApplicationJob
  queue_as :low

  MESSAGE_LIMIT    = 200
  TRANSCRIPT_LIMIT = 50
  MAX_CORPUS_CHARS = 20_000

  def perform(user_id:, linkedin_url: nil, providers: nil)
    user = User.find(user_id)

    unless user.avatar&.behavior&.dig("psych_profiling_opt_in") == true
      Rails.logger.info("[psych-profile] user=#{user_id} has not opted in — skipping")
      return
    end

    corpus = build_corpus(user)
    if corpus.blank? && linkedin_url.blank?
      Rails.logger.info("[psych-profile] user=#{user_id} has no corpus and no linkedin_url — skipping")
      return
    end

    response = AiAgentsClient.new.run_psych_profiling(
      user_id:      user.id.to_s,
      text_corpus:  corpus.presence,
      linkedin_url: linkedin_url,
      providers:    providers
    )

    unless response.is_a?(Hash)
      Rails.logger.warn("[psych-profile] user=#{user_id} non-hash response=#{response.inspect.to_s.first(200)}")
      return
    end

    profiles = response["profiles"] || {}
    errors   = response["errors"]   || {}
    Rails.logger.info(
      "[psych-profile] user=#{user_id} corpus_chars=#{corpus.to_s.length} " \
      "stored=#{profiles.count { |_, v| v.present? }} " \
      "providers=#{profiles.keys.inspect} errors=#{errors.inspect}"
    )
  end

  private

  # Last ~200 user-authored chat messages + recent finished audio
  # transcripts, oldest-first so the corpus reads chronologically.
  def build_corpus(user)
    message_texts = user.messages.user_msgs
                        .order(created_at: :desc)
                        .limit(MESSAGE_LIMIT)
                        .pluck(:content)
                        .reverse

    transcript_texts = AudioChunk
                       .joins(:audio_session)
                       .where(audio_sessions: { user_id: user.id })
                       .where.not(transcript: [nil, ""])
                       .order(created_at: :desc)
                       .limit(TRANSCRIPT_LIMIT)
                       .pluck(:transcript)
                       .reverse

    (message_texts + transcript_texts).join("\n").first(MAX_CORPUS_CHARS)
  end
end