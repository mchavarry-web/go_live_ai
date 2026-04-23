# Go Live

AI avatar platform — a personalized digital avatar that mirrors its owner closely enough to act on their behalf: chat with friends and family, read and reply on social media, attend meetings, take actions via independent AI agents as if it were the user.

## Structure

```
apps/
├── backend/     Rails 8.1 monolith — web + web-admin + JSON API + ActionCable
├── ai-agents/   FastAPI + LangChain + pgvector — internal AI sidecar
└── frontend/    Expo SDK 54 — one codebase for iOS + Android + web
```

## Quick start

```bash
./bootstrap.sh              # first time only (installs everything, starts Docker, creates DBs)
foreman start -f Procfile.dev
```

Services:
- Rails      → http://localhost:3000
- FastAPI    → http://localhost:8001  (docs at /docs)
- Expo       → http://localhost:8081
- Sidekiq UI → http://localhost:3000/sidekiq (admin only)

## Docs

- [CLAUDE.md](./CLAUDE.md) — architecture + conventions for this repo.
- [../PORT_PLAN.md](../PORT_PLAN.md) — full port plan from the previous 5-repo setup.
- [../PLATFORM_ANALYSIS.md](../PLATFORM_ANALYSIS.md) — historical platform analysis.
