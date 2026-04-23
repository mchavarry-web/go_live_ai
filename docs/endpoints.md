# Rails ↔ FastAPI contract

Living reference. When you add a new endpoint on either side of the boundary,
update this table and the Rails client class (`app/clients/ai_agents_client.rb`)
+ the Expo API service (`apps/frontend/services/api/*`) in the same PR.

## FastAPI endpoints called by Rails

All require `X-Internal-Token: <shared>` header.

| Method | Path | Rails caller | Purpose |
|---|---|---|---|
| POST | `/internal/chat/generate` | `AiAgentsClient#generate_chat` | Single-turn avatar response |
| POST | `/internal/chat/stream` | `AiAgentsClient#stream_chat` | SSE stream of tokens, consumed by `ChatGenerationJob` |
| POST | `/internal/chat/proactive-generate` | `AiAgentsClient#generate_proactive` | Proactive greeting per selected skill |
| POST | `/internal/insights/extract` | `AiAgentsClient#extract_insights` | Run insight extraction over a platform payload |
| GET  | `/internal/insights/{user_id}` | `AiAgentsClient#list_insights` | List persisted insights for a user |
| POST | `/internal/memory/search` | `AiAgentsClient#search_memory` | pgvector similarity search |
| GET  | `/health` | `AiAgentsClient#health_ok?` | Liveness probe (public) |

## Rails endpoints called by Expo

Base URL: `/api/v1/` (mobile JWT auth unless noted).

See `apps/backend/config/routes.rb` for the canonical list. Keep the snake_case
JSON ↔ camelCase JS mapping in the Expo API service layer; never change Rails
casing.
