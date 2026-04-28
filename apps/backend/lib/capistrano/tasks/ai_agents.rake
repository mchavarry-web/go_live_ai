# Deploys the FastAPI ai-agents service alongside Rails.
#
# Why this is custom rather than another Capistrano stage: the existing
# `set :repo_tree, "apps/backend"` is what makes the Rails deploy clone only
# the backend subtree. Running a second Capistrano app would mean a parallel
# release manager + duplicate config. Cheaper to just clone the same repo
# into a sibling deploy_to and manage its release lifecycle here.
#
# Layout on the server (mirrors the Rails one exactly):
#
#   /home/deploy/ai_agents/
#     current  → releases/<ts>
#     releases/
#       2026-04-27-072000/
#       2026-04-27-074500/
#     shared/
#       .env                # the only required shared file
#       .venv/              # cached venv — rebuilt only when pyproject changes
#
# Variables (override in config/deploy/<stage>.rb if needed):
#   :ai_agents_deploy_to     "/home/deploy/ai_agents"
#   :ai_agents_python        "python3.12"
#   :ai_agents_service       "ai-agents.service"
#   :ai_agents_keep_releases  3

namespace :load do
  task :defaults do
    set :ai_agents_deploy_to,    "/home/deploy/ai_agents"
    set :ai_agents_python,       "python3.12"
    set :ai_agents_service,      "ai-agents.service"
    set :ai_agents_keep_releases, 3
  end
end

namespace :ai_agents do
  desc "Deploy the FastAPI ai-agents service"
  task :deploy do
    invoke "ai_agents:setup"
    invoke "ai_agents:fetch"
    invoke "ai_agents:venv"
    invoke "ai_agents:link_env"
    invoke "ai_agents:migrate"
    invoke "ai_agents:publish"
    invoke "ai_agents:restart"
    invoke "ai_agents:cleanup"
  end

  desc "Ensure ai-agents directory layout exists on the server"
  task :setup do
    on roles(:ai_agents) do
      base = fetch(:ai_agents_deploy_to)
      execute :mkdir, "-p", "#{base}/releases", "#{base}/shared"
    end
  end

  desc "Clone the apps/ai-agents subtree of the monorepo into a fresh release dir"
  task :fetch do
    on roles(:ai_agents) do
      base    = fetch(:ai_agents_deploy_to)
      release = Time.now.utc.strftime("%Y%m%d%H%M%S")
      release_path = "#{base}/releases/#{release}"
      tmp_path     = "#{base}/releases/.tmp-#{release}"

      execute :git, "clone --quiet --depth 1 --branch #{fetch(:branch)} #{fetch(:repo_url)} #{tmp_path}"
      execute :mv, "#{tmp_path}/apps/ai-agents", release_path
      execute :rm, "-rf", tmp_path

      set :ai_agents_release_path, release_path
    end
  end

  desc "Build (or reuse) a Python venv with current dependencies"
  task :venv do
    on roles(:ai_agents) do
      release_path = fetch(:ai_agents_release_path)
      base         = fetch(:ai_agents_deploy_to)
      shared_venv  = "#{base}/shared/.venv"
      python       = fetch(:ai_agents_python)

      # Build the venv into `shared/.venv` once, then symlink it from each
      # release. That way `pip install` only re-runs when pyproject.toml
      # changes — fast deploys when only Python source changes.
      unless test "[ -d #{shared_venv} ]"
        execute python, "-m", "venv", shared_venv
      end

      # Always upgrade pip + reinstall the package (idempotent; pip skips
      # unchanged deps). `-e .` makes `app` importable as the source layout
      # uses `[tool.hatch.build.targets.wheel] packages = ["app"]`.
      execute "#{shared_venv}/bin/pip install --quiet --upgrade pip"
      execute "#{shared_venv}/bin/pip install --quiet -e #{release_path}"

      execute :ln, "-sfn", shared_venv, "#{release_path}/.venv"
    end
  end

  desc "Symlink the shared .env into the new release"
  task :link_env do
    on roles(:ai_agents) do
      release_path = fetch(:ai_agents_release_path)
      shared_env   = "#{fetch(:ai_agents_deploy_to)}/shared/.env"

      unless test "[ -f #{shared_env} ]"
        error "Missing #{shared_env} — create it on the server before deploying."
        exit 1
      end

      execute :ln, "-sfn", shared_env, "#{release_path}/.env"
    end
  end

  desc "Run Alembic migrations against the production AI agents DB"
  task :migrate do
    on roles(:ai_agents) do
      release_path = fetch(:ai_agents_release_path)
      within release_path do
        # `.env` is symlinked, so DATABASE_URL resolves correctly when alembic
        # boots through env.py (which loads dotenv). No need to re-export here.
        execute "#{release_path}/.venv/bin/alembic upgrade head"
      end
    end
  end

  desc "Flip the 'current' symlink to the new release"
  task :publish do
    on roles(:ai_agents) do
      base         = fetch(:ai_agents_deploy_to)
      release_path = fetch(:ai_agents_release_path)
      execute :ln, "-sfn", release_path, "#{base}/current"
    end
  end

  desc "Restart the systemd unit running uvicorn"
  task :restart do
    on roles(:ai_agents) do
      service = fetch(:ai_agents_service)
      # Allow non-sudo restart by adding the deploy user to a sudoers entry
      # that whitelists exactly this systemctl call (recommended).
      execute :sudo, "/bin/systemctl", "restart", service
    end
  end

  desc "Drop releases older than :ai_agents_keep_releases"
  task :cleanup do
    on roles(:ai_agents) do
      base   = fetch(:ai_agents_deploy_to)
      keep   = fetch(:ai_agents_keep_releases)
      # Sort newest-first, skip the most recent N, delete the rest.
      execute "ls -1t #{base}/releases | tail -n +#{keep + 1} | xargs -I{} rm -rf #{base}/releases/{}"
    end
  end
end

# Wire ai-agents into the standard deploy flow. Runs after Rails finishes so
# a failure here doesn't roll back the Rails deploy — they are independent
# services. Comment out to deploy ai-agents only via `cap production ai_agents:deploy`.
after "deploy:published", "ai_agents:deploy"
