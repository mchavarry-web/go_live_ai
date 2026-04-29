# Whenever DSL → crontab.
# Generate with `bundle exec whenever --update-crontab` on the target host,
# or preview with `bundle exec whenever`.

set :output, "log/cron.log"
env :PATH, ENV["PATH"]

# Proactive pings — fan out every 30 minutes across each time-of-day window.
# Each job self-filters users by their configured timezone + last_proactive_at
# rate limit, so it's safe to schedule at UTC-ish cadence.
every 30.minutes do
  runner "ProactivePushJob.perform_later(time_window: 'morning')"
  runner "ProactivePushJob.perform_later(time_window: 'afternoon')"
  runner "ProactivePushJob.perform_later(time_window: 'evening')"
  runner "ProactivePushJob.perform_later(time_window: 'night')"
end

# Nightly avatar-counter sync (insights_count) from FastAPI.
every 1.day, at: "4:00 am" do
  runner "SyncAvatarCountersJob.perform_later"
end

# Audio training cleanup — abandons stale `recording` sessions older than
# 24h and re-tries chunks stuck in processing for >6h.
every 1.hour do
  runner "AudioSessionCleanupJob.perform_later"
end
