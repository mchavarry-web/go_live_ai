#!/usr/bin/env bash
# Bootstrap the Go Live monorepo.
# Run once after cloning. Installs gems, node modules, Python deps,
# creates both Postgres databases, and applies migrations.
#
# Requires local installs:
#   - PostgreSQL (Homebrew: `brew install postgresql@16 && brew services start postgresql@16`)
#   - Redis      (Homebrew: `brew install redis && brew services start redis`)
#   - pgvector   (Homebrew: `brew install pgvector` — extension shipped with Postgres)
#   - Ruby 3.3.4 (see .ruby-version)
#   - Node 20    (see .nvmrc)
#   - Python 3.11+ (see apps/ai-agents/.python-version)

set -euo pipefail
cd "$(dirname "$0")"

BACKEND_DB="go_live_backend_development"
AI_DB="go_live_ai_agents_development"

echo "==> 1/7  Copy .env.example → .env files (if missing)"
[[ -f .env ]] || cp .env.example .env
[[ -f apps/backend/.env ]] || cp .env.example apps/backend/.env
[[ -f apps/ai-agents/.env ]] || cp .env.example apps/ai-agents/.env
echo "    Remember to fill in API keys in those .env files."

echo "==> 2/7  Check local services"
if ! pg_isready -q; then
  echo "    ✗ Postgres is not accepting connections. Start it with:"
  echo "        brew services start postgresql@16"
  exit 1
fi
echo "    ✓ Postgres: $(psql --version)"
if ! redis-cli ping > /dev/null 2>&1; then
  echo "    ✗ Redis is not responding. Start it with:"
  echo "        brew services start redis"
  exit 1
fi
echo "    ✓ Redis responding"

echo "==> 3/7  Create Postgres databases (idempotent)"
createdb "$BACKEND_DB" 2>/dev/null && echo "    ✓ created $BACKEND_DB" \
  || echo "    ↺ $BACKEND_DB already exists"
createdb "$AI_DB" 2>/dev/null && echo "    ✓ created $AI_DB" \
  || echo "    ↺ $AI_DB already exists"

echo "==> 4/7  Enable pgvector on the ai-agents DB"
psql "$AI_DB" -c "CREATE EXTENSION IF NOT EXISTS vector;" > /dev/null
echo "    ✓ vector extension ready on $AI_DB"

echo "==> 5/7  Rails: bundle install + yarn install + db:prepare"
(cd apps/backend && bundle install)
(cd apps/backend && yarn install)
(cd apps/backend && bin/rails db:prepare)

echo "==> 6/7  FastAPI: create venv + install deps + alembic"
if [[ ! -d apps/ai-agents/.venv ]]; then
  (cd apps/ai-agents && python3 -m venv .venv)
fi
(cd apps/ai-agents && .venv/bin/pip install --upgrade pip setuptools wheel > /dev/null)
(cd apps/ai-agents && .venv/bin/pip install -e ".[dev]")
(cd apps/ai-agents && .venv/bin/alembic upgrade head || echo "    (alembic head failed — likely no migrations yet, ok)")

echo "==> 7/7  Expo + root yarn workspaces"
(cd apps/frontend && yarn install)
yarn install

cat <<'MSG'

  ✔  Bootstrap complete.

  Start all services:
      foreman start -f Procfile.dev

  Or individually:
      cd apps/backend   && bin/rails server
      cd apps/ai-agents && .venv/bin/uvicorn app.main:app --reload --port 8001
      cd apps/frontend  && yarn start

  Smoke tests:
      curl http://localhost:8001/health                         # public, should return 200
      curl http://localhost:8001/internal/insights/test_user    # should return 401 (auth guard)

MSG
