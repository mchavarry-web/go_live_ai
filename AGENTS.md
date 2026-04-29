# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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
- `../AGENTS.md` — the old 5-repo workspace guide.

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
- **Queue/Cable/Cache:** Sidekiq + Redis. ActionCable adapter is **`redis` in every environment** (was `async` in dev — that broke Sidekiq → frontend chat broadcasts because `async` is per-process). **No Solid Queue / Solid Cable / Solid Cache.**
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
- **Redis DB index is `5`** (`REDIS_URL=redis://localhost:6379/5`). Other local projects occupy DB 0; keep go-live on 5 in every `.env`, `cable.yml`, and Python `settings.py` default.
- **Shrine falls back to local FileSystem** in dev when `S3_AWS_STORAGE_BUCKET_NAME` is unset (see `config/initializers/shrine.rb`). Production sets the S3 env vars; nothing else changes.
- **FastAPI hatch build** needs `[tool.hatch.build.targets.wheel] packages = ["app"]` in `pyproject.toml` — the package name (`golive-ai-agents`) doesn't match the source dir (`app/`), so hatchling can't auto-detect.
- **RVM + `set -u`** don't mix. Shell scripts that source RVM must use `set -eo pipefail`, not `set -euo`.

## Common commands

### Bootstrap (first run only)
```bash
./bootstrap.sh          # assumes local Postgres + Redis; creates DBs, installs deps
```
Requires: Homebrew Postgres running (the running server can be 14+; pgvector available), Redis running, RVM with Ruby 3.3.4 and the `go-live` gemset, Homebrew Python 3.11+, Node 20. No Docker in dev or prod.

### Daily dev (two terminals)
```bash
# Terminal 1 — backend stack
bin/dev
# ↳ frees orphan ports (3000/8001/8081), removes stale Puma pid, then runs
#   foreman start -f Procfile.dev
#   processes: rails :3000, jsbundle, cssbundle, sidekiq, ai-agents :8001

# Terminal 2 — Expo (run manually so the keyboard menu works)
cd apps/frontend
yarn start
# ↳ Metro on :8081, then press i / a / w for iOS / Android / web,
#   r to reload, q to quit
```

Why two terminals: foreman captures stdin, which kills Expo's interactive
keyboard menu (`q`/`r`/`i`/`a`/`w`). Running Expo in its own terminal
keeps the menu functional.

Why `bin/dev` exists: foreman's SIGTERM is sometimes ignored by uvicorn's
reloader children and Puma, leaving them squatting on `:3000` / `:8001`
so the next foreman cycle fails to bind. Rails also leaves
`tmp/pids/server.pid` behind on hard exits. `bin/dev` cleans those up
surgically (kills only processes bound to our exact ports) before
booting. Note that `--reload` was dropped from the ai-agents Procfile
line — restart foreman manually after Python changes.

There are **two Procfile.dev** files. Both include Sidekiq:
- `/Procfile.dev` (monorepo root) — full stack (6 processes). Use `foreman start -f Procfile.dev` here.
- `/apps/backend/Procfile.dev` (Rails-only) — web + js + css + worker (sidekiq). Used by `bin/dev` when you `cd apps/backend`.

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
- Phase 1 (auth + data model) — **✔ complete**. User schema extended with country/timezone/lat/lng/last_proactive_skill/last_proactive_at/formality_level/onboarding_completed_at/provider/provider_uid; `Avatar` model (1:1 with User, knowledge_level 1-10 + appearance/behavior jsonb); `Api::V1::AuthController` covers email sign_in/sign_up, Google/Apple/Facebook (server-side provider-token verification — Google/Apple via JWKS, Facebook via Graph API), refresh, me, sign_out; `Api::V1::OnboardingController` (status/complete/reset); CanCanCan `Ability` updated for Avatar; `user` role added to seeds.
- Phase 2 (chat + AI integration) — **✔ complete**. `Conversation` (UUID, `belongs_to :user`, `last_active_at` touched by each new message) + `Message` (UUID, role enum user|assistant|system, content, jsonb metadata, proactive_skill nullable); `Api::V1::ConversationsController` (index/show/create/destroy) and `MessagesController` (index/create) under `/api/v1/chat/conversations`; `ChatChannel` (`stream_from "chat:<conv_id>"`, auth via `current_user.conversations.find_by`); `ChatGenerationJob` (Sidekiq) calls `AiAgentsClient#stream_chat` and broadcasts deltas/message/done/error on the channel; ActionCable mounted at `/cable` with JWT-in-query-param auth; ActiveJob adapter set to `:sidekiq` globally.
- Phase 3 (social + ingestion) — **✔ complete**. `SocialConnection` (UUID, unique per user+provider) with Rails-8 ActiveRecord encryption on `access_token` + `refresh_token`; per-platform flat controllers (`InstagramController`, `FacebookController`, `TwitterController`, `SpotifyController`) sharing an `Api::V1::SocialBaseController` that provides `status`/`disconnect`/`extract_insights`; Spotify full server-side OAuth flow (`auth_url` w/ signed state, `callback` exchanges code); Instagram upload-based ingestion; Sidekiq jobs `InstagramIngestJob`, `FetchSocialDataJob` (per-provider Graph/Web-API pulls), and `ExtractInsightsJob` chained via `AiAgentsClient#extract_insights` which routes to `/internal/insights/extract-instagram` or `/extract-social` per platform.
- Phase 4 (proactive + notifications) — **✔ complete**. `Proactive::SkillRegistry` Ruby port (`app/services/proactive/skill_registry.rb`) with the four default skills (`generic_greeting`, `fun_fact`, `motivation`, `news`), identical time-of-day weights and anti-repetition penalty as the Django original; `Api::V1::ProactiveGreetingsController#create` at `POST /api/v1/chat/proactive-greeting` selects a skill, calls FastAPI `/internal/chat/proactive-generate`, persists the reply as a proactive `Message` (role=assistant, `proactive_skill` stamped), updates `User.last_proactive_skill/at` + optional GPS; `DeviceToken` model (UUID, one active per token, platform enum ios|android|web); `Api::V1::DeviceTokensController` for register/unregister/test-push; `PushNotificationJob` (Sidekiq) hits FCM legacy `/fcm/send` or no-ops when `FCM_SERVER_KEY` is unset (dev-safe).
- Phase 5 (web admin) — **✔ complete**. `/admin` Hotwire pages under `Admin::AdminController` (Devise cookie session + `ensure_admin!` on `current_user.admin?`); rewritten `Admin::DashboardController#index` with go-live metrics (users/onboarded/admin count, conversations + messages + proactive count, per-provider social-connection totals, active device-token count, recent users, recent messages); `Admin::InstagramController#index` + `#extract` lists `SocialConnection.for("instagram")` with item counts + last-ingested timestamp, and a "Re-extraer" button that fires `ExtractInsightsJob` via `button_to`; admin nav updated to expose the Instagram panel; admin layout rebranded Go Live.
- **Decisions applied** (post-Phase 5): single-role on `User` (migration `20260423000007` drops `roles`/`user_roles` tables and adds `users.role` string with default `user`); `omniauth` restored for **web flows** only (`omniauth-google-oauth2`/`-apple`/`-facebook`, all registered unconditionally in `devise.rb` so shared-link helpers stay defined even when env creds are blank); `Users::OmniauthCallbacksController` handles the redirect back via `User.from_omniauth`. Mobile API keeps its hand-rolled JWKS verifiers from Phase 1.
- Phase 6 (Expo polish + web) — **✔ complete**. `app.config.js` gains `platforms: ['ios','android','web']`, `web: { bundler: 'metro', output: 'static' }`; env keys renamed `BASE_URL`→`API_URL` and `WS_URL`→`CABLE_URL`; `utils/platformConfig.js` exposes `getApiUrl/getCableUrl` (Android emulator auto-rewrites localhost → 10.0.2.2); `services/apiService.js` rewritten to match Rails' JWT token shape and endpoint paths (`/auth/sign_in`, `/auth/google|apple|facebook`, `/auth/refresh`, `/auth/me`, `/auth/sign_out`, `/onboarding/*`, `/chat/conversations`, `/chat/proactive-greeting`, per-platform `/{instagram,facebook,twitter,spotify}/{status,ingest,extract}`, `/notifications/device_tokens`); `AuthContext` persists `access_token` + `refresh_token` + `user` and exposes `login`/`register`/`loginWithProvider(provider, token)`/`logout`/`refreshUserData`; `services/chatChannel.js` — hand-rolled WebSocket subscriber that speaks the ActionCable protocol (subscribe → {delta|message|done|error} → disconnect), no dependency on `@rails/actioncable` so it works identically on ios/android/web.
- Phase 7 (archive + cutover) — **✔ complete**. Workspace-level `MIGRATION_COMPLETE.md` records the 5-repo → monorepo mapping, per-phase commit ledger, and first-run checklist. Workspace `AGENTS.md` carries a banner pointing operators here; the old `gln-*` repos are **preserved in place** for reference (not deleted; archival is an explicit operator action). Final cross-phase smoke test (all green): rails `/up`, fastapi `/health`, JWT login w/ `role: administrator`, chat/proactive/social-status/device-tokens endpoints, web login + `/admin` + `/admin/users` + `/admin/instagram`, FastAPI guard (401 without token / 200 with).

See `../PORT_PLAN.md` §10 for the full phase roadmap.

## Auth quick reference

Mobile JWT flow, all under `/api/v1/auth/`:

| Route | Payload | Response |
|---|---|---|
| `POST /auth/sign_up` | `{email, password, first_name?, last_name?}` | `{access_token, refresh_token, expires_at, user}` |
| `POST /auth/sign_in` | `{email, password}` | same |
| `POST /auth/google` | `{id_token}` (ID token from `@react-native-google-signin`) | same |
| `POST /auth/apple` | `{id_token}` (from `expo-apple-authentication`) | same |
| `POST /auth/facebook` | `{access_token}` (from `react-native-fbsdk-next`) | same |
| `POST /auth/refresh` | `{refresh_token}` | `{access_token, expires_at}` |
| `GET  /auth/me` | — (header: `Authorization: Bearer <access_token>`) | `{user}` |
| `DELETE /auth/sign_out` | — | `{message}` |

Provider verification is in `app/services/auth/`: `google_verifier.rb` + `apple_verifier.rb` share `jwks_verifier.rb` (JWKS fetch + RS256 decode + 1-retry on key rotation), `facebook_verifier.rb` hits `graph.facebook.com/me`. All three return a normalised claim hash to `Auth::SocialSignIn` which upserts the `User` by `(provider, provider_uid)` with an email fallback.

JWT issuance is centralised in `Auth::JwtIssuer` (HS256 + `Rails.application.secret_key_base`; access 7d, refresh 30d). Every `User.create!` triggers `ensure_default_role_and_avatar` which adds the `:user` role and creates the matching `Avatar` — no empty users.

**Seed credentials** (from `db/seeds.rb`):
- Admin: `admin@golive.local` / `password123` — use for the `/admin` panel.

**Knowledge-level scale mismatch.** `Avatar.knowledge_level` is 1–10 in Rails; FastAPI's `UserProfile.knowledge_level` is 1–5. Convert with `((rails_level + 1) / 2).clamp(1, 5)` when sending to FastAPI; the reverse (FastAPI → Rails) is `(ai_level * 2).clamp(1, 10)`.

## Chat quick reference

REST under `/api/v1/chat/`:

| Route | Purpose |
|---|---|
| `GET    /chat/conversations`                              | list (100 most recent, by `last_active_at`) |
| `POST   /chat/conversations`                              | create (optional `title`) |
| `GET    /chat/conversations/:id`                          | show + full `messages[]` |
| `DELETE /chat/conversations/:id`                          | delete |
| `GET    /chat/conversations/:id/messages`                 | list messages |
| `POST   /chat/conversations/:id/messages`                 | send `{content}` — returns 202 + user message; enqueues `ChatGenerationJob` |

Real-time over ActionCable at `/cable?token=<jwt>`:
```
subscribe  { channel: "ChatChannel", conversation_id: "<uuid>" }
recv       { type: "delta",   content: "text chunk" }          // repeated
recv       { type: "message", message: { id, role, content, created_at } }
recv       { type: "done",    assistant_message_id: "<uuid>" }
recv       { type: "error",   message: "..." }                  // on failure
```

Flow: Expo `POST` → `MessagesController#create` persists user message + enqueues `ChatGenerationJob` → job calls `AiAgentsClient#stream_chat` (parses FastAPI SSE frames `data: ...\n\n`) → each chunk is broadcast as `{type: "delta"}` → accumulated content is persisted as an assistant `Message` → final `{type: "message"}` + `{type: "done"}`. If the stream is empty (e.g. missing `OPENAI_API_KEY`), the job persists a placeholder assistant message and broadcasts `{type: "error"}` — no exception leaks.

**ActiveJob adapter is Sidekiq in every environment** (`config/application.rb`). Don't set it per-env.

## Social connections quick reference

Flat per-platform routes under `/api/v1/`:

| Route | Instagram | Facebook | Twitter | Spotify |
|---|:---:|:---:|:---:|:---:|
| `GET  <p>/status`           | ✓ | ✓ | ✓ | ✓ |
| `POST <p>/ingest`           | upload payload | paste access_token | paste access_token | enqueue `FetchSocialDataJob` |
| `POST <p>/extract`          | ✓ | ✓ | ✓ | ✓ |
| `DELETE <p>`                | ✓ | ✓ | ✓ | ✓ |
| `GET  spotify/auth_url`     | — | — | — | ✓ (full OAuth) |
| `GET  spotify/callback`     | — | — | — | ✓ |

`SocialConnection` stores the OAuth state: `provider`, `external_user_id`, `access_token` (**encrypted**), `refresh_token` (**encrypted**), `scopes`, `expires_at`, `metadata` jsonb. `User` has `has_many :social_connections`.

Spotify OAuth lives in `app/services/social/spotify_oauth.rb`: `authorize_url(state:)` + `exchange_code!(code)` which persists the connection and its Spotify-provided profile (display_name, country, email) into `metadata`. State is a Redis-cached nonce (10-min TTL) tied to `current_user.id` so the callback can re-identify the user without a JWT. On successful callback we auto-enqueue `ExtractInsightsJob` so insights populate immediately.

Job chain:
- `InstagramIngestJob(user_id:, payload:)` → `ExtractInsightsJob`
- `FetchSocialDataJob(user_id:, provider:)` → persists raw payload on `SocialConnection.metadata.raw_data` → `ExtractInsightsJob`
- `ExtractInsightsJob(user_id:, provider:, payload: nil)` → `AiAgentsClient#extract_insights` → FastAPI `/internal/insights/extract-instagram` (IG) or `/extract-social` (others)

`AiAgentsClient#extract_insights` mirrors the FastAPI split: Instagram has its own triple-chain (`extract-instagram`), every other platform goes through the shared `extract-social`.

**ActiveRecord encryption keys** are env-driven in dev via `ACTIVE_RECORD_ENCRYPTION_{PRIMARY_KEY,DETERMINISTIC_KEY,KEY_DERIVATION_SALT}` (see `config/initializers/active_record_encryption.rb`). They are **stable** — rotating any of them invalidates every existing `social_connections.access_token`/`refresh_token` row.

## Proactive + notifications quick reference

Proactive greeting (avatar speaks first when user returns to the app):

```
POST /api/v1/chat/proactive-greeting
    { local_time: "08:15", local_date: "2026-04-23",
      absence_minutes: 45, latitude?, longitude?, timezone? }

→  { conversation_id, skill: { id, name }, message: {...} }
```

Flow: `Proactive::SkillRegistry.default.select(context)` picks a skill using time-of-day weights (morning/afternoon/evening/night) + anti-repetition penalty on `user.last_proactive_skill` → Rails calls FastAPI `/internal/chat/proactive-generate` → persists reply as `Message(role: "assistant", proactive_skill: skill.id)` → updates `user.last_proactive_skill / last_proactive_at` (+ `last_latitude/longitude` if GPS was provided).

**Adding a new skill:** register on `Proactive::SkillRegistry.default` with id/name/time_weights/requires_location/requires_web_search/min_absence_minutes. The matching prompt section must also be added under `apps/ai-agents/app/prompts/proactive_greeting.py` for FastAPI to know how to render it.

Device tokens & push:

| Route | Body | Purpose |
|---|---|---|
| `POST   /api/v1/notifications/device_tokens` | `{ token, platform, metadata? }` | register (find-or-create by token; reassigns user on reinstall) |
| `DELETE /api/v1/notifications/device_tokens/:token` | — | deactivate |
| `POST   /api/v1/notifications/test` | — | dev-only; enqueues a test push to every active token |

`PushNotificationJob(device_token_id:, title:, body:, data:)` posts to FCM legacy `/fcm/send` with `FCM_SERVER_KEY` bearer. When the key is unset the job **logs and returns** — pipeline stays exerciseable without a real FCM project. On FCM `NotRegistered`/`InvalidRegistration` responses the token is auto-deactivated.

## Admin panel quick reference

Cookie-session + Devise. Entry point: `/users/sign_in`. Admin gate: `Admin::AdminController#ensure_admin!` checks `current_user.admin?` (role = `administrator`). Layout: `layouts/admin.html.erb` (Hotwire + Turbo + Stimulus + Tailwind).

| Route | Purpose |
|---|---|
| `GET  /admin`                             | dashboard (stat cards + recent users + recent messages) |
| `GET  /admin/users`                       | template users index + role management |
| `GET  /admin/users/:id`                   | per-user view |
| `GET  /admin/instagram`                   | list `SocialConnection.for("instagram")` — item counts, last upload |
| `POST /admin/instagram/:id/extract`       | enqueue `ExtractInsightsJob` for that IG connection |

Dashboard query shape (keep `DashboardController#index` cheap — all counts, no joins heavier than `joins(:roles)`):
`@users_count`, `@admins_count`, `@onboarded_count`, `@conversations_count`, `@messages_count`, `@proactive_count`, `@social_totals` (per-provider), `@device_tokens_count`, `@recent_users`, `@recent_messages`.

Panel stat cards render through the `admin/dashboard/_stat_card.html.erb` partial — pass `title:`, `value:`, optional `hint:` + `href:` for the "Ver más" link.

## Expo client quick reference

Config (`apps/frontend/app.config.js`):
- `platforms: ['ios','android','web']` — web target is first-class.
- `extra.API_URL` (default `http://localhost:3000/api/v1`) + `extra.CABLE_URL` (`ws://localhost:3000/cable`) are the only transport URLs — nothing else is hardcoded.

Service layer:
- `services/apiService.js` — one class with methods per Rails endpoint; returns `{ success, data, error }` uniformly. Reads access_token from `AsyncStorage['access_token']` and `Authorization: Bearer …` on every call. 401 → `logoutCallback()` is invoked so the AuthContext can clear state.
- `services/chatChannel.js` — hand-rolled ActionCable-over-WebSocket client. Instantiate with the `conversation_id`, `.on('delta' | 'message' | 'done' | 'error', fn).connect()` then `.disconnect()` on unmount. Token passed as `?token=<jwt>` query param (Rails decodes it in `ApplicationCable::Connection`).
- `contexts/AuthContext.js` — persists `{access_token, refresh_token, user}` triplet. `loginWithProvider('google'|'apple'|'facebook', providerToken)` mirrors the `/auth/google|apple|facebook` Rails endpoints; the Expo caller obtains the provider token via the native SDK (`@react-native-google-signin`, `expo-apple-authentication`, `react-native-fbsdk-next`).

Web vs native gotchas:
- `expo-location` on web uses the browser Geolocation API — works but prompts per origin.
- `expo-web-browser` + in-app redirects → on web, use `window.open` / same-origin redirect when appropriate.
- No `MMKV` on web; AsyncStorage falls back to `localStorage` via `@react-native-async-storage/async-storage` — already in the deps.
