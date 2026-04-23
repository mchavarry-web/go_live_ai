#!/usr/bin/env bash
# Bootstrap the Go Live monorepo.
# Run once after cloning. Slow — installs gems, node modules, Python deps,
# starts Docker services, and creates both databases.

set -euo pipefail
cd "$(dirname "$0")"

echo "==> 1/6  Copy .env.example → .env files (if missing)"
[[ -f .env ]] || cp .env.example .env
[[ -f apps/backend/.env ]] || cp .env.example apps/backend/.env
[[ -f apps/ai-agents/.env ]] || cp .env.example apps/ai-agents/.env
echo "    Remember to fill in API keys in those .env files."

echo "==> 2/6  Start Docker services (Postgres x2 + Redis)"
docker compose up -d

echo "==> 3/6  Rails: bundle install + yarn install + db:prepare"
(cd apps/backend && bundle install)
(cd apps/backend && yarn install)
(cd apps/backend && bin/rails db:prepare)

echo "==> 4/6  FastAPI: create venv + install deps + alembic"
(cd apps/ai-agents && python3 -m venv .venv)
(cd apps/ai-agents && .venv/bin/pip install -e ".[dev]")
(cd apps/ai-agents && .venv/bin/alembic upgrade head || true)  # empty DB is ok

echo "==> 5/6  Expo: yarn install"
(cd apps/frontend && yarn install)

echo "==> 6/6  Root yarn workspaces"
yarn install

cat <<'MSG'

  ✔  Bootstrap complete.

  To start all services:
      foreman start -f Procfile.dev

  Individual services:
      cd apps/backend   && bin/rails server
      cd apps/ai-agents && .venv/bin/uvicorn app.main:app --reload --port 8001
      cd apps/frontend  && yarn start

MSG
