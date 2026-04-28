# Deploying the ai-agents FastAPI service

The Capistrano task `ai_agents:deploy` (in `apps/backend/lib/capistrano/tasks/ai_agents.rake`) handles release management automatically. This README covers the **one-time host setup** before the first deploy.

## Prerequisites on the host

- `python3.12` (Homebrew/apt — must be 3.11+ to satisfy `requires-python>=3.11`).
- `git` reachable from the deploy user (re-uses the same SSH agent forwarding the Rails deploy uses).
- PostgreSQL with the `vector` extension on the AI agents database.
- Redis (DB 5 by default; matches dev config).
- The deploy user (`deploy`) must be allowed to restart the service without a password — see "sudoers" below.

## One-time setup

```bash
# As root or via sudo on the production host.

# 1. Create the AI agents database and enable pgvector.
sudo -u postgres createdb go_live_ai_agents_production
sudo -u postgres psql go_live_ai_agents_production -c 'CREATE EXTENSION IF NOT EXISTS vector;'

# 2. Create the deploy directory tree (Capistrano will own everything inside).
mkdir -p /home/deploy/ai_agents/{releases,shared}
chown -R deploy:deploy /home/deploy/ai_agents

# 3. Drop the production .env in shared/ — it gets symlinked into every release.
#    See apps/ai-agents/.env in the repo for the full list of keys.
sudo -u deploy nano /home/deploy/ai_agents/shared/.env
sudo chmod 600 /home/deploy/ai_agents/shared/.env

# 4. Install the systemd unit.
sudo cp apps/ai-agents/deploy/ai-agents.service /etc/systemd/system/ai-agents.service
sudo systemctl daemon-reload
sudo systemctl enable ai-agents.service

# 5. Allow the deploy user to restart the service without a password prompt.
#    (Capistrano's `sudo systemctl restart ai-agents.service` would otherwise hang.)
echo 'deploy ALL=NOPASSWD: /bin/systemctl restart ai-agents.service' | \
  sudo tee /etc/sudoers.d/ai-agents
sudo chmod 440 /etc/sudoers.d/ai-agents
```

## First deploy

```bash
# From your dev machine, in apps/backend/
cap production deploy        # ← deploys Rails AND ai-agents (the rake task hooks
                             #   into 'deploy:published' so they ship together)

# To deploy ai-agents alone (e.g. after editing only Python code):
cap production ai_agents:deploy
```

Each `ai_agents:deploy` will:

1. `git clone --depth 1` the monorepo into a temp dir, move `apps/ai-agents/` to a fresh release dir, delete the rest.
2. Install / upgrade dependencies into `shared/.venv` (cached across releases — only re-runs `pip install` for what changed).
3. Symlink `shared/.env` into the release.
4. Run `alembic upgrade head` against the production DB.
5. Flip the `current` symlink.
6. `sudo systemctl restart ai-agents.service`.
7. Prune all but the most recent 3 releases.

If any step fails the Rails deploy is **not** rolled back — they are independent services. Re-run `cap production ai_agents:deploy` after fixing whatever broke.

## Health check

```bash
# On the host:
curl http://localhost:8001/health
# → {"status":"healthy",...} if FastAPI is up + DB is reachable.

# /internal/* endpoints reject without the shared token:
curl http://localhost:8001/internal/memory/00000000-0000-0000-0000-000000000000
# → 401

# With the token (must match AI_AGENTS_INTERNAL_TOKEN in the Rails .env):
curl -H "X-Internal-Token: $(grep ^INTERNAL_TOKEN /home/deploy/ai_agents/shared/.env | cut -d= -f2)" \
  http://localhost:8001/internal/memory/<some_uuid>
# → 200
```

## Why uvicorn is bound to 127.0.0.1, not 0.0.0.0

FastAPI is **never** exposed publicly. The only client is Rails, running on the same host. `X-Internal-Token` is a backstop, not the security boundary — the firewall is. If you ever split FastAPI to a different box, change `--host` and put it behind your VPN / Cloudflare Tunnel; do not open `:8001` to the internet.
