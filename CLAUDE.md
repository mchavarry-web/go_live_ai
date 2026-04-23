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

## Common commands

### Bootstrap (first run only)
```bash
./bootstrap.sh          # assumes local Postgres + Redis; creates DBs, installs deps
```
Requires: Homebrew Postgres 16 running, pgvector available, Redis running. No Docker in dev or prod.

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

Phase 0 (scaffold) — `IN PROGRESS`. Directory structure in place; awaiting `./bootstrap.sh` to install deps and boot the stack end-to-end.

See `../PORT_PLAN.md` §10 for the full phase roadmap.
