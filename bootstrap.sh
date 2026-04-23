#!/usr/bin/env bash
# Bootstrap the Go Live monorepo.
# Run once after cloning. Installs gems, node modules, Python deps,
# creates both Postgres databases, and applies migrations.
#
# Requires local installs:
#   - PostgreSQL 16 (`brew install postgresql@16 && brew services start postgresql@16`)
#   - Redis         (`brew install redis && brew services start redis`)
#   - pgvector      (`brew install pgvector`)
#   - RVM with Ruby 3.3.4 and a gemset named `go-live`
#   - Node 20       (see .nvmrc)
#   - Python 3.11+  (see apps/ai-agents/.python-version)

set -eo pipefail
cd "$(dirname "$0")"

BACKEND_DB="go_live_backend_development"
AI_DB="go_live_ai_agents_development"

# ── Source RVM so `rvm use` works in this script ────────────────────────
# (RVM internals reference undefined vars; don't set -u around this.)
# shellcheck disable=SC1091
if [[ -s "$HOME/.rvm/scripts/rvm" ]]; then
  source "$HOME/.rvm/scripts/rvm"
else
  echo "    ✗ RVM not found at \$HOME/.rvm/scripts/rvm"
  exit 1
fi

echo "==> 1/7  Copy per-app .env.example → .env (if missing)"
[[ -f apps/backend/.env ]] || cp apps/backend/.env.example apps/backend/.env
[[ -f apps/ai-agents/.env ]] || cp apps/ai-agents/.env.example apps/ai-agents/.env
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

echo "==> 5/7  Rails: bundle install + yarn install + db:prepare (under rvm 3.3.4@go-live)"
rvm use 3.3.4@go-live --create
echo "    ✓ active: $(ruby -v) @ gemset $(rvm gemset name)"
(cd apps/backend && bundle install)
(cd apps/backend && yarn install)
(cd apps/backend && bin/rails db:prepare)

echo "==> 6/7  FastAPI: create venv + install deps + alembic"
# Bypass pyenv shim; require Homebrew Python ≥ 3.11 (ai-agents pyproject).
PYTHON_BIN="$(command -v /opt/homebrew/bin/python3.12 \
            || command -v /opt/homebrew/bin/python3.11 \
            || true)"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "    ✗ No Homebrew Python 3.11/3.12 found. Install with: brew install python@3.12"
  exit 1
fi
echo "    using $PYTHON_BIN ($("$PYTHON_BIN" --version))"
if [[ ! -d apps/ai-agents/.venv ]]; then
  (cd apps/ai-agents && "$PYTHON_BIN" -m venv .venv)
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
      (cd apps/backend   && rvm use 3.3.4@go-live && bin/rails server)
      (cd apps/ai-agents && .venv/bin/uvicorn app.main:app --reload --port 8001)
      (cd apps/frontend  && yarn start)

  Smoke tests:
      curl http://localhost:8001/health                         # public, 200
      curl http://localhost:8001/internal/insights/test_user    # 401 (auth guard)

MSG
