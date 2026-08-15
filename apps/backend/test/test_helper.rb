ENV["RAILS_ENV"] ||= "test"

# CRITICAL: dotenv-rails (require: "dotenv/load") loads apps/backend/.env in
# EVERY Rails env, and its DATABASE_URL points at the DEVELOPMENT database.
# DATABASE_URL overrides config/database.yml, so without this preset the test
# suite (fixture loading included — it DELETEs from fixture tables!) would run
# against go_live_backend_development. Dotenv never overwrites an already-set
# variable, so pinning it here wins.
ENV["DATABASE_URL"] = "postgres:///go_live_backend_test"

require_relative "../config/environment"
require "rails/test_help"

# config/application.rb pins ActiveJob to :sidekiq in every environment.
# Swap in the inline test adapter so jobs are captured (assert_enqueued_with
# et al) instead of being pushed to Redis during tests.
ActiveJob::Base.queue_adapter = :test

module ActiveSupport
  class TestCase
    # Forked parallel workers hang in this app once the suite crosses the
    # parallelization threshold (observed 2026-08-15: workers fork, create
    # their per-worker DBs, then never run a test — likely Redis-backed
    # Sidekiq/ActionCable connections not surviving the fork). The whole
    # suite runs in <1s single-process, so default to 1 worker; opt back in
    # with PARALLEL_WORKERS=N.
    parallelize(workers: ENV.fetch("PARALLEL_WORKERS", 1).to_i)

    # NOTE: was `fixtures :all`, but test/fixtures/roles.yml and
    # user_roles.yml target tables dropped by migration 20260423000007
    # (single-role model) — loading them raises PG::UndefinedTable even when
    # the files are empty (fixture loading DELETEs from every fixture table).
    # Load only fixture sets whose tables still exist.
    fixtures :users

    # Add more helper methods to be used by all tests here...
  end
end
