# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this monorepo is

Single-repo consolidation of the Go Live platform (an AI avatar that mirrors its owner and acts on their behalf). Replaces the 5 previous repos — `gln-mobile-app`, `gln-web-front`, `gln-api-back`, `gln-ai-agents`, `gln-ingestion-back` — with three apps under `apps/`:

| Path | Stack | Role |
|---|---|---|
| `apps/backend/` | Rails 8.1 + Devise + Sidekiq + ActionCable + HTTParty + Hotwire + Tailwind | Web (public + admin) + JSON API + real-time chat. Owns users, auth, chat persistence, social connections, ingestion, notifications. |
| `apps/ai-agents/` | FastAPI + LangChain 1.2 + LangGraph + LangSmith + SQLAlchemy async + pgvector | Internal AI sidecar. Only Rails calls it. Never exposed publicly. |
| `apps/frontend/` | Expo SDK 54 (iOS + Android + web) + React Navigation + Zustand + TanStack Query | Single client codebase. Talks to Rails only. |

Authoritative context docs live at the parent workspace `../`:
- `../PLATFORM_ANALYSIS.md` — what each repo did, feature history, training pipelines.
- `../PORT_PLAN.md` — the full port plan (source of truth for architecture decisions).
- `../CLAUDE.md` — the old 5-repo workspace guide.

## Architecture (locked)

```
Expo (ios/android/web) ──HTTPS + ActionCable──► Rails ──HTTP──► FastAPI
                                                  │              │
                                                  │              └── pgvector (insights, embeddings)
                                                  │                  LangSmith traces
                                                  │                  OpenAI / Anthropic / Tavily
                                                  └── PostgreSQL (users, auth, chat, social, ingestion, notifications)
                                                      Redis (Sidekiq, ActionCable prod)
```

- **Only Rails is publicly exposed.** FastAPI guards `/internal/*` with `X-Internal-Token`.
- **Real-time chat uses ActionCable only.** No SSE, no `ActionController::Live`. Expo POSTs via REST, receives streaming chunks via Cable.
- **Auth:** Devise (cookie web) + hand-rolled JWT (API) — see `apps/backend/app/controllers/api/v1/base_controller.rb`. **No devise-jwt, no omniauth.** Social login (Google/Apple/Facebook) done via client-side provider SDK + server-side token verification.
- **Queue/Cable/Cache:** Sidekiq + Redis. ActionCable adapter is `async` in dev, `redis` in prod. **No Solid Queue / Solid Cable / Solid Cache.**
- **Ingestion:** flat per-platform controllers (`InstagramController`, `SpotifyController`, etc.) — no `Ingestion::` namespace.
- **Two PostgreSQL DBs on the same local server** (different DB names): `go_live_backend_development` for Rails, `go_live_ai_agents_development` for FastAPI. Rails never uses pgvector; the AI DB has the `vector` extension enabled. Production follows the same shape; Postgres runs locally on the box, not containerized.

## Running locally — verified state

Bootstrap passes end-to-end; all three services boot cleanly on this machine.

| Service       | Port | Start command                       | Smoke check                                              |
|---------------|-----:|-------------------------------------|----------------------------------------------------------|
| Rails 8.1.3   | 3000 | `bin/rails server`                  | `GET /up` → **200**                                      |
| FastAPI       | 8001 | `.venv/bin/uvicorn app.main:app`    | `GET /health` → **200** (DB connected, pgvector ready)   |
| FastAPI guard | 8001 | `GET /internal/memory/<user_id>`    | no header → **401**; wrong token → **401**; correct → **200** |
| Postgres 14+  | 5432 | `pg_isready`                        | `accepting connections`; 2 DBs, `vector` ext on AI DB    |
| Redis         | 6379 | `redis-cli ping`                    | `PONG`                                                   |

Copy-paste smoke tests:
```bash
curl http://localhost:3000/up                                                       # Rails
curl http://localhost:8001/health                                                    # FastAPI public
curl http://localhost:8001/internal/memory/00000000-0000-0000-0000-000000000000     # 401
TOKEN=$(grep ^INTERNAL_TOKEN apps/ai-agents/.env | cut -d= -f2)
curl -H "X-Internal-Token: $TOKEN" \
     http://localhost:8001/internal/memory/00000000-0000-0000-0000-000000000000     # 200
```

## Environment pins (non-obvious, learned the hard way)

- **Ruby 3.3.4 @ RVM gemset `go-live`** (dash, not underscore). `.ruby-gemset` at the monorepo root and at `apps/backend/` both contain `go-live`. Every Rails command must run under this gemset — `Procfile.dev` wraps each Ruby process in `bash -lc 'rvm use 3.3.4@go-live --create …'`.
- **Python 3.11+ via Homebrew**, **not pyenv**. `bootstrap.sh` explicitly uses `/opt/homebrew/bin/python3.12` to create `apps/ai-agents/.venv` because the user's pyenv is pinned to 3.9.4. **Don't reintroduce `apps/ai-agents/.python-version`** — it forces pyenv back into the picture.
- **Two `.env` files, never a root one.** `DATABASE_URL` has different values in each service, so the env split is by app: `apps/backend/.env` and `apps/ai-agents/.env`. Don't create a root `.env` — nothing reads it.
- **Shared secret is one value, two names.** `AI_AGENTS_INTERNAL_TOKEN` (Rails) == `INTERNAL_TOKEN` (FastAPI). Must match; FastAPI fails closed with 500 if unset.
- **Shrine falls back to local FileSystem** in dev when `S3_AWS_STORAGE_BUCKET_NAME` is unset (see `config/initializers/shrine.rb`). Production sets the S3 env vars; nothing else changes.
- **FastAPI hatch build** needs `[tool.hatch.build.targets.wheel] packages = ["app"]` in `pyproject.toml` — the package name (`golive-ai-agents`) doesn't match the source dir (`app/`), so hatchling can't auto-detect.
- **RVM + `set -u`** don't mix. Shell scripts that source RVM must use `set -eo pipefail`, not `set -euo`.

## Common commands

### Bootstrap (first run only)
```bash
./bootstrap.sh          # assumes local Postgres + Redis; creates DBs, installs deps
```
Requires: Homebrew Postgres running (the running server can be 14+; pgvector available), Redis running, RVM with Ruby 3.3.4 and the `go-live` gemset, Homebrew Python 3.11+, Node 20. No Docker in dev or prod.

### Daily dev (one command starts the stack)
```bash
foreman start -f Procfile.dev
# ↳ Rails :3000, jsbundle watch, cssbundle watch, Sidekiq, FastAPI :8001, Expo :8081
```

### Rails (apps/backend)
```bash
cd apps/backend
bin/rails server                 # :3000
bin/rails console
bin/rails db:migrate
bin/rails db:reset
bundle exec sidekiq              # background jobs
bundle exec rspec                # (or bin/rails test)
bundle exec rubocop
bundle exec brakeman             # security scan
```

### FastAPI (apps/ai-agents)
```bash
cd apps/ai-agents
.venv/bin/uvicorn app.main:app --reload --port 8001
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate -m "msg"
.venv/bin/pytest
.venv/bin/pytest tests/integration/test_chat.py::test_name
.venv/bin/ruff check app/ && .venv/bin/black app/ && .venv/bin/pyright app/
```
API docs at `/docs`. `/internal/*` requires the `X-Internal-Token` header.

### Expo (apps/frontend)
```bash
cd apps/frontend
yarn start                       # Metro + QR code
yarn ios | yarn android | yarn web
yarn lint && yarn test
```

## Per-service conventions

- `apps/backend/` follows Rails conventions with the template's Services/Selectors split — business logic in `app/services/*.rb`, read-only queries in `app/selectors/*.rb`. Controllers (inc. `Api::V1::*`) only handle HTTP. Views/serializers only shape output.
- `apps/ai-agents/` — LCEL only (never raw prompt strings), `ChatPromptTemplate` + `PydanticOutputParser`, `@traceable` on every chain method, `SecretStr` for API keys, repository pattern in `app/repositories/`, pgvector via IVFFlat cosine. **Carried over unchanged from the old `gln-ai-agents`.** Only addition: `X-Internal-Token` middleware.
- `apps/frontend/` — dark theme only (`#0A0A0F`); tokens from `src/theme/` — never hardcode colors. Backend responses snake_case → map to camelCase in the API service layer. Server state in TanStack Query, client state in Zustand (never mix). All API calls via one configured Axios instance.

## Cross-service gotchas

- **Auth token format:** `{ access_token, refresh_token, user }` from `Api::V1::Mobile::SessionsController`. Mirror it in Expo's auth store.
- **ActionCable JWT:** passed as `?token=<jwt>` query param; `ApplicationCable::Connection#connect` decodes with `Rails.application.secret_key_base` + HS256.
- **Chat streaming:** Expo's message POST triggers `ChatGenerationJob` (Sidekiq) → calls FastAPI `/internal/chat/stream` → each chunk `ActionCable.server.broadcast("chat:<conv_id>", …)`. Expo reads chunks over its `ChatChannel` subscription.
- **Ingestion jobs are asynchronous.** Spotify/IG/FB/Twitter raw fetches run as Sidekiq jobs that call `AiAgentsClient#extract_insights` on completion. The mobile client polls status or subscribes to a progress channel.
- **Two databases.** When running migrations, `bin/rails db:migrate` only touches the backend DB. FastAPI schema is managed by Alembic in `apps/ai-agents/alembic/`.

## Phase status

- Phase 0 (scaffold) — **✔ complete**. Monorepo boots; FastAPI guard verified; Rails + pgvector DB wired.
- Phase 1 (auth + data model) — **next**. Add go-live-specific `User` columns (country, timezone, proactive tracking, formality_level), `Avatar` model, onboarding endpoints, and server-side social-login verification for Google/Apple/Facebook.

See `../PORT_PLAN.md` §10 for the full phase roadmap.
