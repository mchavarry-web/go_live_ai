# frozen_string_literal: true

# Scheduled proactive-greeting dispatcher.
#
# For every User whose timezone places them in the argued `time_window`
# (morning | afternoon | evening | night), enqueues a
# PushNotificationJob per active DeviceToken with a generated proactive
# greeting that's already run through the skill registry (both gates).
#
# Called from config/schedule.rb every 30min; small work batches keep
# Sidekiq responsive. Actual LLM generation is deferred to
# ProactiveGreetingForUserJob (one per user) so a slow user doesn't
# block others.
class ProactivePushJob < ApplicationJob
  queue_as :default

  WINDOWS = {
    "morning"   => (6..11),
    "afternoon" => (12..17),
    "evening"   => (18..21),
    "night"     => (22..5) # wraps
  }.freeze

  def perform(time_window: nil)
    target_users(time_window).find_each do |user|
      next if user.device_tokens.active.empty?
      next if throttled?(user)
      ProactiveGreetingForUserJob.perform_later(user_id: user.id, time_window: time_window)
    end
  end

  private

  # Active users in the requested time-of-day window based on their own
  # timezone. Users without a timezone fall through to America/Lima (the
  # current default locale).
  def target_users(window)
    User.where.not(timezone: nil).where.not(timezone: "").select do |u|
      hour = Time.current.in_time_zone(u.timezone || "America/Lima").hour
      in_window?(hour, window)
    end
  end

  def in_window?(hour, window)
    return true if window.blank?
    range = WINDOWS.fetch(window)
    range.include?(hour) || (window == "night" && (hour >= 22 || hour <= 5))
  end

  # Skip users who got a proactive ping in the last 4h — the registry's
  # repetition penalty is for intra-session selection; this is global rate.
  def throttled?(user)
    user.last_proactive_at.present? && user.last_proactive_at > 4.hours.ago
  end
end
