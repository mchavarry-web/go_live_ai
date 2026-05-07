# Memory & Training Strategy

How the Go Live avatar accumulates knowledge about its user, what it stores, how it stores it, how it retrieves it back at chat time, and how it generates a response that feels like the user is talking — not an assistant *about* the user.

> **The job**: the avatar interacts as if it *were* the user. To do that it learns from every channel the user touches — chat, voice journal, social platforms, onboarding, location, web search — distills that into structured memory across four substrates with three retrieval mechanisms, then composes a layered system prompt that the LLM uses to speak in the user's voice with the user's facts.

This document is the comprehensive picture: training philosophy, per-source pipelines, mode system, retrieval, generation, proactive surface, lifecycle, and admin tooling. The phase log (§14) is the per-phase build record; the changelog (§17) is the dated summary of improvement waves.

---

## 1. Strategy at a glance

There are three problems the avatar has to solve, and each one has its own strategy:

| Problem | Strategy |
|---|---|
| **Know the user** — learn personal facts, preferences, relationships, plans, and emotional patterns. | Multi-channel extraction. Every input (chat, audio, social, onboarding) feeds purpose-built LCEL chains that produce categorized insights. Stored in `insights` table (pgvector). Retrieved by semantic similarity to whatever the user is currently saying. |
| **Sound like the user** — match their register, regional dialect, slang, formality, and the avatar's own developing voice with this person. | Style adaptation: dialect catalog (per ISO country), slang calibrator (every 5 turns), persona-evolution chain (mode-scoped), formality directive section. Layered top-down in the system prompt so register can never accidentally override mode constraints. |
| **Stay grounded in time and context** — remember dated commitments, pick up the thread of a long conversation, recall what the user actually said in their voice journal, and know where they are. | Three temporal/contextual substrates (events, summaries, transcript chunks) with non-RAG retrieval where appropriate. Filter-by-time for events, latest-non-superseded for summaries, strict-cosine for verbatim quotes. |

All three layer into the same generation prompt; none of them block the chat response. Extraction happens in non-blocking post-turn tasks; retrieval runs as 6 concurrent fetches before generation.

---

## 2. The four memory substrates

| Substrate | Table (FastAPI DB) | What it holds | Retrieval | Prompt section |
|---|---|---|---|---|
| **Insights** | `insights` (1536-d pgvector) | Categorized facts, preferences, persona notes, language style. | Semantic RAG (cosine) | "COSAS QUE SABES…" + "TU VOZ Y EVOLUCIÓN…" + (formality directive) |
| **User events** | `user_events` (no embedding, indexed `(user_id, occurs_at)`) | Time-bound commitments. | Filter-by-time | "PRÓXIMOS COMPROMISOS…" |
| **Conversation summaries** | `conversation_summaries` (rolling, supersedable) | Medium-term thread compression. | Latest-non-superseded | "RESUMEN DE LA CONVERSACIÓN…" |
| **Audio transcript chunks** | `audio_transcript_chunks` (1536-d pgvector, sentence-windowed) | Verbatim quotes from voice journal. | Semantic RAG over verbatim text | "FRAGMENTOS RELEVANTES DE LO QUE HA DICHO…" |

All four wipe together via `MemoryService.delete_user_memory(user_id)` for GDPR symmetry.

### 2.1 `insights` (semantic RAG pool)

`InsightCategory` enum (`app/models/enums.py`) defines eight categories:

| Category | Pool | Purpose |
|---|---|---|
| `personal_history` | User-fact | Past events, life experiences. |
| `preference` | User-fact | Likes, favorites, tastes. |
| `relationship` | User-fact | Family, friends, partners. |
| `goal` | User-fact | Forward-looking objectives. |
| `emotion` | User-fact | Recurring emotional states. |
| `health` | User-fact | Body, exercise, diet. |
| `avatar_evolution` | Avatar self-model | Notes about how the avatar's *own voice* is developing with this user. Mode-scoped via `source = "persona_update:<mode>"`. |
| `language_style` | Style | One-row-per-user formality + custom expressions. |

Each row carries a `source` tag that downstream code uses to filter:

| `source` | Origin |
|---|---|
| `"conversation"` | Chat insight chain |
| `"audio:<session_id>"` | Audio insight chain |
| `"facebook"` / `"twitter"` / `"spotify"` / `"instagram"` | Social ingest |
| `"persona_update:<mode>"` | `PersonaEvolutionChain` |
| `"persona_update"` | Legacy persona rows (pre-mode support) |
| `"slang_calibration"` | `SlangCalibratorChain` |
| `"web_search:<md5(query)[:12]>"` | Phase-15 search-engagement capture |
| `"manual"` | Admin teach endpoint |

### 2.2 `user_events` (temporal pool)

Phase 1–6.

- Schema: `id, user_id, title, occurs_at TIMESTAMPTZ, occurs_at_has_time, raw_text, source, source_message_id, confidence, status (active|cancelled|archived), timezone, created_at, updated_at`.
- Composite indexes on `(user_id, occurs_at)` (hot path for `list_upcoming`) and `(user_id, status)` (cleanup sweeps).
- Lifecycle: opportunistic archive on read — `ChatService._get_upcoming_events` calls `EventRepository.archive_past(user_id, before=now)` for the same user every chat turn. No cron sweep.
- No embedding column by design: retrieval is `WHERE status='active' AND occurs_at BETWEEN now AND now+horizon` — semantic similarity is the wrong tool for "what's on my calendar today?".

### 2.3 `conversation_summaries` (medium-term memory)

Phase 12–13.

- Schema: `id, user_id, conversation_id, summary, message_count, summary_token_count, range_start_message_id, range_end_message_id, superseded_at, created_at`.
- Trigger: `ConversationSummaryService.should_summarize(turn_count) == (turn_count >= 20 and turn_count % 20 == 0)` — every 20 user turns.
- Atomic write via `supersede_then_create`: marks the prior latest row `superseded_at = now()` and inserts the new one in a single transaction. Race-tolerant under double-firing.
- Idempotency: when the latest non-superseded row already covers the same `range_end_message_id`, the service skips. Cheap protection against duplicate writes.

### 2.4 `audio_transcript_chunks` (verbatim retrievable pool)

Phase 14.

- Schema: `id, user_id, audio_chunk_id, audio_session_id, sequence_in_chunk, text, embedding(1536), recorded_at, created_at`.
- IVFFlat cosine index on `embedding` + composite `(user_id, recorded_at)` for the rare time-window query.
- Chunker (`transcript_chunker.chunk_transcript`): sentence-aware, ~256-word windows with ~32-word overlap, with a fallback word-window split for punctuation-free transcripts.
- Retrieval: `AudioTranscriptRepository.search_similar(user_id, q_embedding, top_k=3, max_distance=0.25)` — strict cosine ceiling so tangential matches don't surface.
- Distinct from insights — insights are *derived facts*, transcript chunks are *source-of-truth quotes*. The avatar can quote the user's words back rather than rephrasing them when relevant.

---

## 3. Per-source training strategy

Eight input channels feed the substrates above. The strategies differ because the inputs differ.

### 3.1 Chat messages (per-turn)

The richest signal — the user is talking *to* the avatar in real time. Every turn produces multiple parallel signals:

| Chain | When | Output | Source tag | Code |
|---|---|---|---|---|
| `InsightExtractionChain` | Every turn | 0–N insights across 6 user-fact categories | `"conversation"` | `app/chains/insight_chain.py` |
| `PersonaEvolutionChain` | Every turn | `avatar_evolution` notes (mode-scoped) | `"persona_update:<mode>"` | `app/chains/persona_evolution_chain.py` |
| `SlangCalibratorChain` | Every 5th user turn | `language_style` row (formality + custom expressions) | `"slang_calibration"` | `app/chains/slang_calibrator_chain.py` |
| `EventExtractionChain` | Every turn (Phase 7+) | 0–N dated events | `"conversation"` | `app/chains/event_extraction_chain.py` |
| `ConversationSummaryChain` | Every 20th turn | One supersedable summary | n/a (own table) | `app/chains/conversation_summary_chain.py` |

**All five run as non-blocking post-turn tasks** (`ChatService._run_post_turn_tasks` for streaming, `ChatService.generate_response` post-turn block for non-streaming). The chat response is delivered first; extraction happens in the background with its own DB session.

#### 3.1.1 `InsightExtractionChain` — design rationale

- Six rigid categories, no `event` slot — that's why events live in their own substrate.
- Spanish-first prompt with explicit anti-patterns ("ignore greetings", "ignore trivial messages without personal content").
- Confidence floor `0.4` — insights below this get dropped post-extraction. Low floor because false positives in personal_history/preference are cheap.
- The chain receives optional `assistant_response` so it can pick up implicit confirmations ("yeah, exactly").
- `avatar_evolution` is filtered out at the chain level so the persona chain has exclusive ownership of that category.
- **Pre-insert dedupe (Wave A.3)**: before storing, candidates are batch-embedded and looked up against same-user/same-category insights at `cosine_distance ≤ 0.15`. On hit, we either reuse the existing row (lower confidence) or update it in place (new confidence ≥ existing + 0.10). Slang calibration calls `dedupe=False` because its content is a JSON blob whose distance is dominated by structure, not value.

#### 3.1.2 `PersonaEvolutionChain` — the avatar's own model of itself

- Reads the user's message + the assistant's reply + a window of prior persona notes.
- Output is **about the avatar's voice**, not facts about the user (e.g. "ya conoce su humor seco", "está cómodo usando voseo con esta persona").
- Mode-scoped: notes from `professional` mode never leak into `dating` mode, and vice versa. Source format: `persona_update:<mode>`.
- Tentative dialect-marker observations are stored with an `[obs:<marker>]` prefix at 0.45–0.55 confidence and **only promoted to a confirmed adoption note after ≥5 prior observations with the same prefix**. This prevents the avatar from imitating a regional particle from a single mention.
- **Anti-self-reinforcement guardrail (Wave A.4)**: the prompt now explicitly tells the chain that words/jerga appearing only in the avatar's own response are *not* evidence of the user's style. Adoption only counts when the user repeats, confirms, or contradicts. This stops the avatar's own quirks from feeding back into its self-model as if the user had taught it.

#### 3.1.3 `SlangCalibratorChain` — register sensing

- Reads the user's last 5 turns and infers `(formality_level: 0.0-1.0, custom_expressions: list[str])`.
- Single-row-per-user latest-only retrieval — overwrites are fine because we want the freshest signal.
- Output drives two prompt sections: `_build_language_style_section` (slang intensity bucketing) and `_build_formality_directive_section` (Phase 8 — explicit register guidance).

#### 3.1.4 `EventExtractionChain` — temporal grounding

- Hybrid resolver: LLM produces ISO 8601 in the user's local tz; `dateparser` independently parses the raw fragment. Disagreement window: 2 days.
- Behavior matrix:

| LLM | dateparser | Outcome |
|---|---|---|
| ✓ | ✓ (within 2d) | Use LLM's value (richer phrasing). |
| ✓ | ✗ | Use LLM. |
| ✗ | ✓ | Use dateparser. |
| ✓ | ✓ (>2d apart) | **Drop** — neither source trusted. |
| ✗ | ✗ | Drop. |

- Confidence floor 0.6 (chat/audio); 0.7 for social (noisier text).
- Window guard: `now_utc - 1h <= occurs_at <= now_utc + 365d`.
- Dedupe via `EventRepository.find_duplicate(user_id, title, occurs_at, window_minutes=60)` — case-insensitive title prefix in a ±60-minute window. Prevents double-inserts when the user mentions the same event in two consecutive turns.

#### 3.1.5 `ConversationSummaryChain` — medium-term memory

- Output: third-person Spanish summary (≤800 chars), 3–5 key topics, token-count estimate.
- Reads the prior summary as context if one exists — new summaries integrate older ones rather than re-summarizing from zero.
- Read-side: `_gather_memory` fetches the latest summary; when present and history > 20 entries, history is truncated to the last 10 by `_maybe_truncate_history`.

### 3.2 Audio chunks (per-recording, ~5 minutes)

User dictates into the app. Rails captures, transcribes, and ships the transcript to FastAPI for full processing.

**Pipeline**:

```
Mobile app → Rails AudioChunk row → AudioChunkProcessJob
                                          │
                                          ▼
   POST /internal/audio/transcribe ── transcript text returned
                                          │
                                          ▼
   POST /internal/audio/extract_insights ── three concurrent operations:
                                          ├─ InsightExtractionChain over transcript
                                          ├─ EventService.extract_and_store_from_text
                                          │   (Phase 7 — events from voice journal)
                                          └─ chunk + embed + persist transcript
                                              chunks (Phase 14)
```

- Transcripts are stored on Rails (`AudioChunk.transcript`) for UI display.
- Insights tagged `source="audio:<session_id>"` so `delete_insights_by_source` can wipe per-session.
- Events anchor on `chunk.created_at` (not Sidekiq pickup time) so "mañana" resolves to the day the user actually spoke.
- Transcript chunks tagged with `audio_session_id` and `audio_chunk_id` for traceability and per-session wipes.

### 3.3 Social platforms

Each platform has its own extraction strategy because the data shapes differ. All routed through `POST /internal/insights/extract-social` (or `/extract-instagram` for IG which is upload-based).

| Platform | Insight chains | Event extraction (Phase 11) | Notes |
|---|---|---|---|
| **Instagram** | `InstagramInterestChain` + `InstagramContentChain` + `InstagramSocialGraphChain` (3-way parallel) | Skipped — comments lack reliable post-date | Upload-based (user uploads their IG export). |
| **Facebook** | `FacebookContentChain` + `FacebookSocialChain` | `posts[].message` / `story` anchored on `created_time` | Token-based fetch via `FetchSocialDataJob`. |
| **Twitter/X** | `TwitterContentChain` + `TwitterInterestChain` | `tweets[].text` anchored on `created_at` | Same fetch job. |
| **Spotify** | `SpotifyTasteChain` | No posts → no events | OAuth flow with token refresh. |

Phase 11 social-event extraction is gated by:
- `_SOCIAL_POST_AGE_LIMIT_DAYS = 180` — older posts skipped silently (their relative phrases would resolve to the past anyway).
- A regex pre-filter (`_TEMPORAL_PATTERNS`) — only posts that mention a temporal marker pay for an LLM call. Cuts ~80% of cost.
- `Semaphore(5)` concurrency cap — bounds peak parallelism for users with hundreds of posts.
- Confidence floor `0.7` — higher than chat because posts are noisier.

Phase 16 archival: every social fetch persists a `social_data_snapshots` row in Rails *before* `SocialConnection.metadata.raw_data` is overwritten. `extraction_version` on the snapshot lets a future redrive skip already-processed payloads. Retention: latest 12 per `(user, platform)`, pruned in the same transaction as the new write.

### 3.4 Onboarding form

One-shot capture, stored as direct columns on Rails `User`:

| Field | Used for |
|---|---|
| `country` | Dialect-catalog lookup at chat time. |
| `timezone` | Event-extraction `RELATIVE_BASE` + proactive-greeting time-of-day binning. |
| `formality_level` (initial) | Seeds the slang calibrator before observed signal is available. |
| `last_latitude` / `last_longitude` | Phase 10 reactive location section (privacy-gated). |
| `share_location_with_avatar` | Phase 10 toggle (default `false`). |
| `last_proactive_skill` / `last_proactive_at` | Anti-repetition penalty in proactive registry. |
| `onboarding_completed_at` | Gates whether the avatar treats the user as "new" or "established". |

### 3.5 Location

`User.last_latitude` / `last_longitude` are populated by background client updates. Two consumers:

1. **Proactive greetings** — gate location-requiring skills (`weather`, `commute`, `morning_briefing` flag-via-skill).
2. **Reactive chat** (Phase 10) — when `share_location_with_avatar = true`, the user's `current_location_payload` is included in the prompt as a "UBICACIÓN ACTUAL" line. Coords-only (no reverse geocode) — the LLM infers city from `(lat, lng) + country`.

### 3.6 Web search results

Phase 15. Web search is a tool, not a content source — but engagement with what comes back IS a signal.

- The `web_search` Tavily/DuckDuckGo tool, after a successful call, stashes `(query, summary[:1000])` into a 5-minute TTL in-process LRU keyed by `(user_id, conversation_id)`. Identity reads from contextvars (`bind_chat_request`) so the tool doesn't need user/conv args plumbed through the agent.
- On the **next** turn, `take_prior_search_for(user_id, conversation_id)` is called BEFORE the agent runs — capturing the prior turn's stash before this turn's potentially-different search overwrites it.
- The captured context + the user's new message feed `SearchEngagementChain`, which decides whether the user actually engaged (vs. polite acknowledgement).
- On engaged + confidence ≥ 0.7: a `preference` insight is persisted with `source="web_search:<md5(query)[:12]>"`.

Note: search results themselves are not embedded; only the engagement-derived insight is captured.

### 3.7 Sentiment (orthogonal signal)

`SentimentChain` (`app/chains/sentiment_chain.py`) classifies a single message into `{positivo, negativo, neutro}` plus a primary emotion and intensity. Surfaced via `/internal/insights/sentiment-analyze` for ad-hoc use. Not currently wired into the chat post-turn tasks — the persona/insight chains already capture emotional state through the `emotion` insight category.

### 3.8 Avatar agent + tool use

`AvatarChain._build_agent` instantiates `AvatarAgent` (a LangGraph `create_react_agent`) when `settings.web_search_enabled = true`. The agent has access to:

- `web_search` (Tavily preferred, DuckDuckGo fallback when no key)
- `fetch_urls` (when Tavily key is present)

Tool-use policy lives in the system prompt itself (`templates/avatar_system.txt`):
- **REGLA 0** — proactive verification before any external fact assertion.
- **REGLA 1** — mandatory search for sports results, news, prices, weather, releases, recent changes, explicit requests.
- **REGLA 2** — never simulate the search ("voy a buscarlo" is forbidden — first action is the tool call).
- **REGLA 3** — max 3 calls per turn.
- **REGLA 4** — integrate results naturally, brief citation only when very specific.

When `web_search_enabled = false`, `AvatarChain` falls back to the bare `prompt | llm` chain.

---

## 4. Mode system — the strongest constraint on style

The user picks one of three modes from the Perfil screen. The mode is **the single most influential prompt section** because it overrides everything else (slang intensity, formality, tone, dialect mirroring).

| Mode | Stage trigger | Posture |
|---|---|---|
| `professional` | always neutral register | Formal, no jerga, no voseo, no apodos, no humor, no personal vulnerability. |
| `friends` | default | Casual permitted. Humor, dialect mirroring, register matches user. |
| `dating` (nascent) | `mode_message_count < 30` | Cautious. No nicknames. No early intimacy. Polite curiosity. |
| `dating` (warming) | `30 <= mode_message_count < 150` | Warmer. Light flirtation if user initiates. Some inside-jokes accepted. |
| `dating` (established) | `mode_message_count >= 150` | Established familiarity. Avatar can volunteer affection if previously reciprocated. |

Implementation:

- `_build_mode_section(active_mode, mode_message_count)` returns the mode block — top of prompt, after datetime + location, before everything else.
- `_mode_demands_neutral_register(active_mode, mode_message_count)` is True for `professional` and dating-nascent. Used to suppress dialect / formality directive / behavior-section tone lines that could contradict the mode.
- Mode is also a **filter on persona retrieval**: `_get_persona_insights` only returns rows whose `source` matches `persona_update:<active_mode>` (or legacy `persona_update` when active_mode is `friends`). A persona note written during dating mode will not surface during professional mode.

`Avatar.message_count_in_active_mode` is incremented by `Avatar.increment_mode_message_count!` on every user-message persistence. JSONB `mode_message_counts` keeps separate counts per mode so switching modes doesn't reset the stage.

---

## 5. Dialect catalog — language-style adaptation

`apps/ai-agents/app/prompts/dialect_catalog.py` maps ISO 3166-1 alpha-2 country codes to a `DialectProfile`:

```python
{
    "name": "rioplatense",                 # human-readable label
    "pronoun": "vos",                      # Tú / usted / vos
    "conjugation_hint": "voseo (tenés, sos, querés, dale)",
    "slang_casual": [...],                 # full informal palette
    "slang_moderate": [...],               # softer, mixed-register palette
    "fillers": [...],                      # natural muletillas
    "avoid": [...],                        # other-dialect expressions to NOT use
}
```

Currently catalogued: `ar, mx, pe, co, cl, es, uy, ec, ve, us, gb` (11 profiles).

`_build_language_style_section` selects which slang palette to inject based on `formality_level`:
- `< 0.4` → `slang_casual` palette + "usa jerga libremente".
- `0.4–0.7` → `slang_moderate` palette + "usa jerga moderada".
- `≥ 0.7` → no slang list + "evita jerga pesada".

`avoid` is always emitted — explicitly tells the avatar which other-dialect expressions NOT to use even if it has seen them.

The whole section is suppressed when `_mode_demands_neutral_register` is True (professional / dating-nascent).

---

## 6. Behavior settings — explicit user policy

In addition to the *observed* signal (slang calibrator), the user can express explicit policy through `behavior_settings` (JSON dict on the Rails Avatar). `_build_behavior_section` reads:

| Key | Range | Effect |
|---|---|---|
| `tone_formality` | 0.0–1.0 | Explicit formality policy. When set, **suppresses** the calibrator-derived formality directive (Phase 8) — explicit user policy wins over observed signal. |
| `tone_humor` | 0.0–1.0 | Humor sensitivity. |
| `tone_verbosity` | 0.0–1.0 | Reply length preference. |
| `language` | ISO code | Forces a target language. Always pass-through (safety/policy). |
| `preferred_topics` | list | Topics to lean into. |
| `restricted_topics` | list | Topics to avoid. Always pass-through (safety/policy). |

`_build_behavior_section` is appended at the **tail** of the system prompt — most-recent-instruction priority. Tone-shaping lines (formality / humor / verbosity / preferred_topics) are stripped when `_mode_demands_neutral_register` is True; `language` and `restricted_topics` always pass through.

---

## 7. Knowledge_level — the avatar's overall grasp

Phase 9 unified what used to be two divergent formulas.

**Rails is canonical** (`Avatar#knowledge_level`):

```
log10(insights*3 + messages + conversations*2 + connections*5 + days_active + 1) * 2.5
```

Clamped to 1–10. Multi-signal, log-scaled — a brand-new user starts at 1, a long-active user with social connections approaches 10.

**FastAPI accepts as-is** — no recomputation. `MemoryService.calculate_knowledge_level` was deleted. `UserProfile.knowledge_level` Pydantic range is 1–10.

**Prompt rendering** — for stylistic stability the prompt still says "X/5":

```python
knowledge_level_display = max(1, min(5, (int(knowledge_level) + 1) // 2))
```

Maps 1–2 → 1, 3–4 → 2, 5–6 → 3, 7–8 → 4, 9–10 → 5.

Counter sync: `SyncAvatarCountersJob` runs nightly at 04:00 local and pulls `insights_count` from FastAPI's `count_by_user_id` so `Avatar.insights_count` stays current. Other counters (`messages_count`, `conversations_count`, `social_connections_count`, `days_active`, `mode_message_counts`) update inline via `after_create_commit` callbacks on Rails.

---

## 8. Retrieval pipeline (chat-time)

`ChatService._gather_memory` runs **six concurrent fetches** before each chat turn:

| # | Fetch | Source | Output | Notes |
|---|---|---|---|---|
| 1 | `_get_memory_insights` | `insights` table | top-10 cosine, `max_distance ≤ 0.40` | Excludes `avatar_evolution` and `language_style`. Wave A.2 distance ceiling stops weakly-related insights from polluting the prompt. |
| 2 | `_get_persona_insights` | `insights` (avatar_evolution) | top-5 cosine, `max_distance ≤ 0.45` | Mode-scoped via source filter. Drops `[obs:...]` rows. Looser ceiling than facts because persona notes are paraphrased. |
| 3 | `_get_language_style` | `insights` (language_style) | latest single row | Parsed by `SlangCalibratorChain.parse_insight_content` into `(formality_level, custom_expressions)`. |
| 4 | `_get_upcoming_events` | `user_events` | upcoming 14d, limit 10 | Opportunistic `archive_past` on the same call. |
| 5 | `_get_prior_summary` | `conversation_summaries` | latest non-superseded | Phase 13. |
| 6 | `_get_relevant_transcript_quotes` | `audio_transcript_chunks` | top-3 cosine, dist ≤ 0.25 | Phase 14. Verbatim quotes. |

All six degrade to a None/empty default on failure (`return_exceptions=True`), so a single subsystem outage cannot break chat. Results land on `_MemoryContext` (slots: `memory_insights, persona_insights, formality_level, custom_expressions, upcoming_events, prior_summary, transcript_quotes`).

`_extract_user_profile` then assembles a single dict that flows into `AvatarChain._build_system_prompt` → `build_avatar_system_prompt(...)` in `app/prompts/avatar_prompts.py`.

### 8.1 History truncation

When `prior_summary` is non-empty AND `len(conversation_history) > 20`, the chain only sees the last 10 entries. The summary covers the older context. Implemented by `_maybe_truncate_history` and applied identically in `generate_response` (non-streaming) and `generate_stream` (SSE).

---

## 9. Generation prompt structure

`build_avatar_system_prompt(...)` assembles the system prompt from these sections, in this exact order:

1. Header (`Eres {avatar_name}, el avatar digital de {display_name}.`)
2. **`current_datetime`** — anchor for relative-date inference at runtime.
3. **`location_section`** (Phase 10) — privacy-gated coords + country.
4. **`mode_section`** — strongest constraint. Mode block + dating-stage stanza.
5. Profile basics (`age_range, interests, personality_section, social_section, health_section`).
6. **`insights_section`** — derived facts.
7. **`persona_section`** — avatar's own evolving voice notes (filtered to confirmed only).
8. **`summary_section`** (Phase 13) — medium-term conversation summary.
9. **`transcript_quotes_section`** (Phase 14) — verbatim quotes from voice journal.
10. **`events_section`** — upcoming dated commitments, humanized in Spanish ("hoy a las 18:00", "mañana", "el martes a las 09:00", "el próximo martes a las 15:00", "el 10/07").
11. **`language_style_section`** — dialect catalog selection.
12. **`formality_directive_section`** (Phase 8) — register guidance from `formality_level`.
13. Static behavior rules ("CÓMO HABLAS", anti-patterns, web-search policy).
14. **`behavior_section`** (appended at tail) — explicit `behavior_settings` policy.

The builder has a defensive fallback path: when any optional placeholder is missing from `avatar_system.txt` (older deployment), the section is appended at the tail and a warning logs.

---

## 10. The end-to-end generation loop

What happens from a user's POST to the streamed assistant reply:

```
POST /api/v1/chat/conversations/<id>/messages   { content: "..." }
   │
   ▼ (Rails)
   Api::V1::Chat::MessagesController#create
     ├─ Persists user Message
     ├─ Increments avatar counters (messages_count, mode_message_counts, last_interaction_at)
     ├─ Bumps conversation.last_active_at
     └─ Enqueues ChatGenerationJob via Sidekiq
   │
   ▼ (Sidekiq)
   ChatGenerationJob#perform
     ├─ Builds payload: user_id, message, conversation_id,
     │   user_profile (display_name, avatar_name, age_range, country,
     │     timezone, last_location, interests, values, introvert_extrovert,
     │     rational_emotional, behavior_settings, knowledge_level (1-10),
     │     active_mode, mode_message_count),
     │   conversation_history, message_created_at
     │   (Wave A.1 — interests/values/personality/behavior_settings now
     │    populated from Avatar.appearance + Avatar.behavior jsonb)
     └─ Streams POST /internal/chat/stream to FastAPI (HTTPS, X-Internal-Token)
   │
   ▼ (FastAPI)
   ChatService.generate_stream
     ├─ bind_chat_request(user_id, conversation_id)        # contextvar for tools
     ├─ prior_search = take_prior_search_for(...)          # Phase 15 read-side
     ├─ mem = await _gather_memory(...)                    # 6 concurrent fetches
     ├─ user_profile = _extract_user_profile(...)
     ├─ history_for_stream = _maybe_truncate_history(...)  # Phase 13 truncation
     │
     ├─ async for token in avatar_chain.generate_stream(...):
     │     yield SSE frame                                 # delta tokens to Rails
     │
     ├─ yield telemetry SSE frame (hop-by-hop timestamps)
     ├─ asyncio.create_task(_run_post_turn_tasks(...))     # non-blocking
     └─ yield "data: [DONE]"
   │
   ▼ (back in Rails)
   ChatGenerationJob streams chunks to ActionCable as
   { type: "delta", content: "..." }, accumulates the full text,
   persists assistant Message with telemetry metadata, then broadcasts
   { type: "message", message: {...} } and { type: "done", ... }.
   │
   ▼ (in parallel — FastAPI background)
   _run_post_turn_tasks (own DB session):
     ├─ _extract_and_store_insights              # 6 fact-categories
     ├─ _evolve_and_store_persona                # mode-scoped avatar_evolution
     ├─ _extract_and_store_events                # delegates to EventService
     ├─ (every 5th turn) _calibrate_and_store_slang
     ├─ (every 20th turn) ConversationSummaryService.summarize_if_due
     └─ (when prior_search) SearchEngagementService.maybe_capture
```

Key invariants:
- The streamed reply does **not** wait for any post-turn task. The user sees tokens immediately.
- Post-turn tasks run with their own `AsyncSession` (via `_get_async_session_maker`) so they survive request-scope teardown.
- All post-turn tasks use `asyncio.gather(..., return_exceptions=True)` — one failure cannot break the others.
- Telemetry is preserved across success / empty / error paths. Rails persists whatever timestamps it has so testers can spot which leg of the trip stalled.

---

## 11. Proactive greetings

A separate generation path: the avatar speaks first when the user returns to the app.

### 11.1 Skill registry

Rails `Proactive::SkillRegistry` (`apps/backend/app/services/proactive/skill_registry.rb`). Eight default skills:

| Skill | `requires_location` | `requires_web_search` | `min_absence_minutes` | Time-of-day weights (M/A/E/N) |
|---|---|---|---|---|
| `generic_greeting` | – | – | 0 | 0.8 / 0.8 / 0.8 / 0.8 |
| `fun_fact` | – | – | 0 | 2.0 / 1.5 / 0.8 / 0.5 |
| `motivation` | – | – | 0 | 2.5 / 0.6 / 1.5 / 2.0 |
| `news` | – | ✓ | 0 | 2.0 / 2.5 / 1.0 / 0.3 |
| `weather` | ✓ | ✓ | 0 | 2.5 / 1.2 / 0.8 / 0.2 |
| `commute` | ✓ | ✓ | 0 | 2.0 / 0.3 / 1.8 / 0.0 |
| `morning_briefing` | – | ✓ | 360 (~6h overnight) | 3.0 / 0.0 / 0.0 / 0.0 |
| `workout_reminder` | – | – | 0 | 2.0 / 0.6 / 1.5 / 0.3 |

Selection algorithm:
1. Filter by gates: `enabled_skill_ids` (admin × user opt-in), `requires_location`, `min_absence_minutes`.
2. Compute time-of-day from `local_time` (morning / afternoon / evening / night).
3. Weight each eligible skill by its franja weight; multiply by `REPETITION_PENALTY = 0.1` if `skill.id == user.last_proactive_skill`.
4. Weighted random sample.

### 11.2 Generation

`POST /api/v1/chat/proactive-greeting` →

```
Proactive::SkillRegistry.default.select(context)
  → Rails calls FastAPI /internal/chat/proactive-generate
    payload: user_id, conversation_id, user_profile, skill_id, skill_context,
             local_time, local_date, absence_minutes
  → ChatService.generate_proactive_greeting
    ├─ if skill_id == "news": _fetch_news_context (Tavily, rotated interests)
    ├─ build_proactive_system_prompt(skill_id, skill_context, ...)
    └─ LLM invoke (no streaming, no chain — direct call)
  → Rails persists reply as Message(role: "assistant", proactive_skill: skill_id)
  → Updates user.last_proactive_skill / last_proactive_at (+ optional GPS)
```

Key differences from reactive chat:
- No RAG. Only skill context is injected. Insight retrieval is too noisy for an opener.
- `knowledge_level` is scaled DOWN for proactive (`((rails + 1) // 2)` clamped to 5) so the avatar doesn't overclaim familiarity at the start of a session.
- Empty `conversation_history` — proactive is the first message, not a continuation.

---

## 12. Lifecycle, GDPR, admin

### 12.1 GDPR memory wipe

`DELETE /internal/memory/{user_id}` → `MemoryService.delete_user_memory` cascades across all four substrates:

- `InsightRepository.delete_by_user_id`
- `EventRepository.delete_by_user_id`
- `ConversationSummaryRepository.delete_by_user_id`
- `AudioTranscriptRepository.delete_by_user_id`

Each is wrapped in its own `try/except` so partial failure logs and continues — better to delete what we can than abort midway.

Source-tagged wipes (`/internal/memory/{user_id}/by-source`) handle audio-session deletes (e.g. `source="audio"` with `prefix=true` matches `audio:<any>`) and per-platform unbinding.

### 12.2 Admin surface

| Endpoint | Purpose |
|---|---|
| `/internal/memory/{user_id}` | Full insight pool (`MemoryResponse`). |
| `/internal/memory/{user_id}/snapshot` | Cross-substrate counts + last-write timestamps (Phase 18). |
| `/internal/memory/{user_id}/categories` | Per-category insight counts. |
| `/internal/memory/{user_id}/sources` | Per-source insight counts. |
| `/internal/memory/{user_id}/insights/{insight_id}` (PATCH) | Update single insight content + regenerate embedding. |
| `/internal/memory/{user_id}/insights/{insight_id}` (DELETE) | Single-insight delete. |
| `/internal/memory/{user_id}/teach` | Manual insight injection (`source="manual"`). |
| `/internal/events/{user_id}` | Active upcoming events. |
| `/internal/events/{user_id}/all` | Every status (debug). |
| `/internal/events/{user_id}/{event_id}` (PATCH) | Change status (cancel / archive). |

All `/internal/*` routes are guarded by the shared `X-Internal-Token` header (`require_internal_token` dependency in `app/main.py`).

### 12.3 CLI

`apps/ai-agents/scripts/dump_user_memory.py <user_id> [--output report.md]` produces a markdown snapshot of the user's complete memory state — counts, per-category, per-source, recent insights, upcoming events, summaries, transcript chunks. Read-only, dev convenience. Pulls everything via the same repositories the production code uses.

### 12.4 Rails admin views

`/admin/instagram` (Hotwire) lists `SocialConnection.for("instagram")` with item counts and last-upload timestamps; "Re-extraer" buttons fire `ExtractInsightsJob`. Useful for re-running extraction after a chain prompt evolves.

---

## 13. Internal API surface

```
GET    /internal/memory/{user_id}                           — full insight pool
GET    /internal/memory/{user_id}/snapshot                  — Phase 18 cross-substrate counts
GET    /internal/memory/{user_id}/categories                — per-category counts
GET    /internal/memory/{user_id}/sources                   — per-source counts
DELETE /internal/memory/{user_id}                           — GDPR wipe (4 substrates)
DELETE /internal/memory/{user_id}/by-source                 — selective wipe (audio session, etc.)
DELETE /internal/memory/{user_id}/insights/{insight_id}     — single-insight delete
PATCH  /internal/memory/{user_id}/insights/{insight_id}     — single-insight update
POST   /internal/memory/{user_id}/teach                     — manual insight injection

GET    /internal/events/{user_id}                           — active upcoming
GET    /internal/events/{user_id}/all                       — debug, every status
PATCH  /internal/events/{user_id}/{event_id}                — change status
DELETE /internal/events/{user_id}                           — events GDPR wipe

POST   /internal/insights/extract                           — chat insight extraction
POST   /internal/insights/extract-social                    — Facebook/Twitter/Spotify + events (Phase 11)
POST   /internal/insights/extract-instagram                 — Instagram (3-chain parallel)
POST   /internal/insights/search                            — semantic search

POST   /internal/audio/transcribe                           — multipart audio → transcript
POST   /internal/audio/extract_insights                     — transcript → insights + events + chunks (Phase 7 + 14)

POST   /internal/chat/generate                              — non-streaming
POST   /internal/chat/stream                                — SSE streaming
POST   /internal/chat/proactive-generate                    — proactive greetings
```

All routes guarded by `X-Internal-Token` header.

---

## 14. Phase log (chronological)

What follows is the development history. The strategy described above (§§1–13) is the *current* state; this section explains how that state was built up over time.

### Phase 0 — pre-existing baseline (carried over from `gln-ai-agents`)

Before any of the numbered phases, the system already had:

- `insights` table + `InsightRepository` + pgvector IVFFlat cosine index.
- `InsightExtractionChain` (6 categories) and per-platform social chains (Facebook, Twitter, Spotify, Instagram triple).
- `PersonaEvolutionChain` + `SlangCalibratorChain`.
- `AvatarChain` + `AvatarAgent` + Tavily/DuckDuckGo `web_search` tool.
- `MemoryService` orchestrating storage + retrieval.
- `_gather_memory` with 3 concurrent retrievals (memory insights, persona, language style).
- Mode system (Profesional / Amigos / Citas) with the dating ramp.
- Dialect catalog (11 countries).
- Behavior settings policy block.
- Proactive skill registry (4 default skills, time-of-day weights, anti-repetition penalty).
- Sentiment chain.
- Conversation history passed full each turn (no summarization).

Gaps closed by Phases 1–18 below.

### Phases 1–6 — events feature ✓

| # | Title | Key deliverable |
|---|---|---|
| 1 | Data model | `user_events` table, `EventRepository`, Pydantic `UserEvent`/`UserEventCreate`, alembic `a1b2c3d4e5f6`. |
| 2 | Extraction chain | `EventExtractionChain` with hybrid LLM + dateparser. Drop-on-disagreement (deviated from initial plan after smoke-test showed dateparser unreliable for Spanish weekday phrases). |
| 3 | Wire into chat | Rails `chat_generation_job.rb` sends `timezone` + `message_created_at`. `ChatService._extract_and_store_events` runs in `_run_post_turn_tasks` (non-blocking). |
| 4 | Retrieval into prompt | `_gather_memory` adds 4th concurrent fetch. `event_humanizer.py` renders Spanish phrases. New "PRÓXIMOS COMPROMISOS" section. |
| 5 | Admin + GDPR | `/internal/events/{user_id}` route. GDPR wipe extended to events. |
| 6 | Tests | 22 unit tests for humanizer + chain. |

### Phase 7 — Audio transcripts → events ✓

`EventService.extract_and_store_from_text` introduced as the shared entrypoint. Audio route runs event extraction concurrently with insight extraction. Rails `AudioChunkProcessJob` passes `timezone`, `recorded_at` (chunk's `created_at`, not Sidekiq pickup time), `audio_chunk_id`.

### Phase 8 — Formality directive prompt section ✓

`_build_formality_directive_section` translates `formality_level` into one of three Spanish directives. Suppressed in Profesional / dating-nascent and when `behavior_settings.tone_formality` is explicitly set.

### Phase 9 — Knowledge_level unification ✓

Rails canonical 1–10. FastAPI accepts as-is, no recomputation. `MemoryService.calculate_knowledge_level` removed. `UserProfile.knowledge_level` widened to 1–10. `chat_generation_job.rb` stops halving. Prompt renders 1–5 by halving for stylistic stability.

### Phase 10 — Reactive location context ✓

Rails migration `share_location_with_avatar` (default false). `User#current_location_payload` returns coords + country only when toggle on. `_build_location_section` renders coords-only — no reverse-geocode dependency.

### Phase 11 — Social posts → events ✓

`_extract_events_from_social_posts` helper iterates Facebook/Twitter posts (Spotify and Instagram skipped). 6-month age cutoff, regex pre-filter for temporal markers, `Semaphore(5)` concurrency cap, confidence floor 0.7.

### Phase 12 — Conversation summary WRITE ✓

`ConversationSummaryChain` + `ConversationSummaryRepository` (atomic supersede-then-create) + `ConversationSummaryService` (idempotent by `range_end_message_id`). Migration `c2d3e4f5a6b7` adds 4 columns + 2 indexes. Trigger every 20 user turns. GDPR symmetry.

### Phase 13 — Conversation summary READ ✓

`_get_prior_summary` added to `_gather_memory` (5th concurrent fetch). `_build_summary_section` placed between insights and events. `_maybe_truncate_history` slices to last 10 when summary present and history > 20.

### Phase 14 — Audio transcript chunks ✓

New `AudioTranscriptChunkModel` + IVFFlat + composite `(user_id, recorded_at)` index. Migration `d3e4f5a6b7c8` includes raw `ALTER TABLE … ADD COLUMN embedding vector(1536)`. `transcript_chunker.chunk_transcript` is sentence-aware with word-window fallback. `AudioTranscriptRepository.search_similar(top_k=3, max_distance=0.25)`. Audio route runs chunk + embed alongside insight + event extraction (3 concurrent awaits). 6th memory retrieval added. GDPR symmetry.

### Phase 15 — Web search engagement → preference insight ✓

`SearchEngagementChain` (LCEL, conservative; floor 0.7). `SearchEngagementService` with two-turn correlation. `web_search` tool stashes via contextvars + in-process LRU (5-min TTL). `take_prior_search_for` is invoked at request entry BEFORE the agent runs to avoid TOCTOU. Persistence: `preference` insight with `source="web_search:<md5(query)[:12]>"`.

### Phase 16 — Social raw data archival ✓

Rails migration `social_data_snapshots` with FK CASCADE + composite index. `SocialDataSnapshot.archive!` persists + prunes (latest 12 per user/platform) in one transaction. `FetchSocialDataJob` archives BEFORE overwriting `metadata.raw_data`.

### Phase 17 — EventService consolidation ✓

`ChatService._extract_and_store_events` now delegates to `EventService.extract_and_store_from_text`. Audio (Phase 7) and social (Phase 11) already used `EventService` from the start, so chat was the only refactor target.

### Phase 18 — Admin observability ✓

`GET /internal/memory/{user_id}/snapshot` returns per-substrate counts + last-write timestamps. `apps/ai-agents/scripts/dump_user_memory.py` produces a full markdown report.

---

## 15. Migrations summary

| Service | Migration | Phase | What |
|---|---|---|---|
| FastAPI | `a1b2c3d4e5f6_add_user_events.py` | 1 | Create `user_events` table. |
| FastAPI | `c2d3e4f5a6b7_extend_conversation_summaries.py` | 12 | 4 cols + 2 indexes on `conversation_summaries`. |
| FastAPI | `d3e4f5a6b7c8_create_audio_transcript_chunks.py` | 14 | Create `audio_transcript_chunks` + IVFFlat. |
| Rails | `20260506000001_add_share_location_with_avatar_to_users.rb` | 10 | Privacy toggle on `users`. |
| Rails | `20260506000002_create_social_data_snapshots.rb` | 16 | Immutable archive table. |

In dev, `Base.metadata.create_all` in `apps/ai-agents/app/main.py` materialises new FastAPI tables on restart so alembic only matters for production parity. Rails migrations need `bin/rails db:migrate`.

---

## 16. Testing

`apps/ai-agents/tests/unit/`:

| File | Coverage |
|---|---|
| `test_event_extraction_chain.py` | ISO/dateparser parsers, window/confidence filters, end-to-end with mocked LLM, hallucination rejection, chain failure → empty list. |
| `test_event_humanizer.py` | Relative buckets, weekday rendering, tz fallback, sort order. |
| `test_transcript_chunker.py` | Sentence boundaries, oversize-sentence fallback, overlap. |
| `test_schemas.py` | UserProfile bounds widened to 1–10 (Phase 9). |
| `test_avatar_modes.py` | Mode block selection, dating ramp boundaries, prompt placement. |
| `test_audio_transcription.py` | Audio pipeline. |
| `test_autonomous_agent.py` | Tool-using agent path, profile injection. |
| `test_web_tools.py` | URL normalization, fetch-result formatting. |
| `test_insight_repository_threshold.py` | Wave A.2 — `max_distance` SQL predicate, optionality, filter composition. |
| `test_memory_service_dedupe.py` | Wave A.3 — no-match insert, lower-conf reuse, higher-conf update, `dedupe=False` bypass, batch embedding. |
| `test_persona_chain_prompt.py` | Wave A.4 — anti-self-reinforcement rule presence, dialect guardrail intact. |

Suite total at the close of Wave A: **115 tests passing** (104 prior + 11 new).

---

## 17. Changelog

Reverse-chronological summary of dated improvement waves. The full per-phase
detail lives in §14 above; this section is the at-a-glance "what shipped
when" view.

### 2026-05-06 — Wave C: autonomy design + draft-mode scaffolding (no execution)

Lays the groundwork for "acts as the user" without any real-world side
effects yet. Schema + endpoints + identity policy ship; tool execution is
explicitly out of scope.

| Item | What | Files |
|---|---|---|
| **C.1** Identity / representation policy | New `_build_agent_identity_section` + `{agent_identity_section}` placeholder. Avatar prompts now declare which mode they operate in: `companion` (default, omitted), `representative`, `draft`, `autopilot`. The full doc (`docs/autonomous_agent_design.md`) defines when each mode is allowed and what tools each can call. | `apps/ai-agents/app/prompts/avatar_prompts.py`, `apps/ai-agents/app/prompts/templates/avatar_system.txt`, `docs/autonomous_agent_design.md` |
| **C.2** `agent_permissions` Rails model | Per-`(user, capability)` row with `enabled / approval_required / max_risk_level / spend_limit_cents / allowed_recipients / allowed_domains / quiet_hours`. Default-deny — rows ship `enabled: false`. | `db/migrate/20260506000003_create_agent_permissions.rb`, `app/models/agent_permission.rb` |
| **C.3** `agent_action_logs` Rails model | Append-only audit row for every proposed/approved/rejected/executed/failed/rolled_back action. Carries `tool_input`, `tool_output`, `rollback_payload`. Indexed by `(user_id, executed_at desc)` and `(user_id, approval_status)`. | `db/migrate/20260506000004_create_agent_action_logs.rb`, `app/models/agent_action_log.rb` |
| **C.4** Draft-mode proposal endpoints | `POST/GET /api/v1/agent/proposals`, `PATCH /api/v1/agent/proposals/:id/approve\|reject\|edit`. **No tool executor wired.** Approving a proposal flips `approval_status` to `approved`; nothing runs against external services. The next phase will hand off `approved` rows to per-capability adapters. | `app/controllers/api/v1/agent_proposals_controller.rb`, `config/routes.rb`, `app/models/user.rb` |
| **C.5** User has-many wiring | `User has_many :agent_permissions, :agent_action_logs` (dependent: :destroy). | `app/models/user.rb` |

**Decisions baked in**:

- **Default-deny** at the schema layer. New users have zero capabilities granted.
- **Mode is set per-request, never inferred.** Reactive chat defaults to `companion` and stays there until a controller action explicitly enters `representative` / `draft` / `autopilot`.
- **No autopilot in v1.** The mode exists in the prompt-section enum so the schema is forward-compatible, but there is no path to grant pre-approved capabilities via the current admin/user UIs.
- **Rollback fields are present but unused** — capabilities that are inherently irreversible (sent email, paid purchase) should set `rollback_available: false` and stay in draft mode forever, per the doc.

**Rollout gates** (from §6 of the design doc, in order; only items 1–3 ship today):

1. ✅ Identity policy section in prompts.
2. ✅ `agent_permissions` and `agent_action_logs` migrations + models.
3. ✅ Draft-mode endpoints — proposals only, no execution.
4. ⛔ User-facing settings UI to manage permissions.
5. ⛔ First read-only capability adapter.
6. ⛔ Per-capability executor — only after ≥2 weeks of draft-mode telemetry.
7. ⛔ Autopilot for narrowly-scoped capabilities.

---

### 2026-05-06 — Wave B: memory quality hardening + durable learning + eval harness

Five items extending the chat-quality work from Wave A into measurable,
durable, and observable territory.

| Item | What | Files | Tests |
|---|---|---|---|
| **B.1** Insight `status` + correction detection | New `status` column on `insights` (`active` / `superseded` / `corrected`) + alembic `e4f5a6b7c8d9`. `InsightRepository.search_similar` defaults to `status='active'`; admin can pass `include_superseded=True`. New `CorrectionDetectorChain` (LCEL, confidence floor 0.7) reads each user message; `MemoryService.apply_corrections` looks up matching same-category insights at `cosine_distance ≤ 0.40` and bulk-flips them to `status='superseded'`. Wired FIRST in post-turn so insight extraction can't re-add facts the user just retracted. | `app/models/database.py`, `alembic/versions/e4f5a6b7c8d9_add_insight_status.py`, `app/repositories/insight_repository.py`, `app/services/memory_service.py`, `app/chains/correction_detector_chain.py`, `app/services/chat_service.py` | `test_correction_detector.py` (8 cases) |
| **B.2** Per-category confidence floors | `InsightExtractionChain` accepts a `category_min_confidence` map. Defaults: base 0.55, sensitive (`health` / `relationship` / `emotion`) 0.65. Action-usable bucket reserved (≥ 0.80) but inactive until autonomy capabilities ship. | `app/chains/insight_chain.py` | `test_insight_chain_floors.py` (5 cases) |
| **B.3** `user_style_profiles` typed table | New table with structured columns (formality, dialect, custom_expressions, emoji_frequency, plus reserved fields for richer style modelling). Migration `f5a6b7c8d9e0`. SlangCalibratorChain now writes to the new table; `_get_language_style` reads from it first and falls back to the legacy JSON-blob `language_style` insight when missing. GDPR symmetry. | `app/models/database.py`, `alembic/versions/f5a6b7c8d9e0_create_user_style_profiles.py`, `app/repositories/user_style_profile_repository.py`, `app/services/chat_service.py`, `app/services/memory_service.py` | covered by integration smoke (no DB tests yet) |
| **B.4** Durable post-turn learning | New `POST /internal/chat/learn` endpoint that runs the full post-turn batch synchronously. New `LearnRequest`/`LearnResponse` schemas. New `Settings.post_turn_inline` flag (default `True` for safety) — when `False`, FastAPI's streaming path skips its in-process `create_task` kick. Rails: new `PostTurnLearningJob` enqueued by `ChatGenerationJob` after the assistant Message persists; calls FastAPI and stamps counts onto the assistant Message metadata for observability. Sidekiq retries handle transient failures. | `app/api/routes/chat.py`, `app/services/chat_service.py`, `app/models/schemas.py`, `app/config/settings.py`, `apps/backend/app/jobs/post_turn_learning_job.rb`, `apps/backend/app/jobs/chat_generation_job.rb`, `apps/backend/app/clients/ai_agents_client.rb` | `test_chat_service_learn.py` (3 cases) |
| **B.5** Voice + memory eval harness | `apps/ai-agents/scripts/evaluate_avatar_voice.py` ships 6 deterministic scenarios (professional-strict, friends-voseo, dating-nascent, location-gated-off, summary+quotes, behavior-policy-overrides-calibrator). Runs in <1s, no LLM. Wrapped as a pytest so CI catches structural regressions. LLM-judge mode reserved for pre-release validation. | `scripts/evaluate_avatar_voice.py`, `tests/unit/test_evaluate_avatar_voice.py` | (the harness IS the test) |

**Test suite at the close of Wave B + C**: 131 tests passing.

---

### 2026-05-06 — Wave A: chat-quality hardening

Closed five gaps surfaced by an external audit (OpenAI Codex). All
incremental, all behind existing flags or default-on with a fallback path.

| Item | What changed | Files | Tests |
|---|---|---|---|
| **A.1 Rails payload completeness** | `chat_generation_job.rb#user_profile` now reads `interests` / `values` / `introvert_extrovert` / `rational_emotional` from `Avatar.appearance` jsonb and `behavior_settings` from `Avatar.behavior` jsonb. New helpers `interests_list`, `values_list`, `introvert_extrovert_score`, `rational_emotional_score`, `behavior_settings_payload` on the Avatar model. FastAPI `UserProfile` schema gains a typed `behavior_settings` field; `ChatService._extract_user_profile` plumbs it into the prompt dict (the prompt builder already consumed it via `_build_behavior_section`). | `apps/backend/app/models/avatar.rb`, `apps/backend/app/jobs/chat_generation_job.rb`, `apps/ai-agents/app/models/schemas.py`, `apps/ai-agents/app/services/chat_service.py` | covered by existing schema tests |
| **A.2 Retrieval distance thresholds** | `InsightRepository.search_similar` gained an optional `max_distance` parameter (SQL-side `WHERE cosine_distance(embedding, q) <= max_distance`). Plumbed through `MemoryService.get_relevant_insights`. Chat-time defaults: `_USER_INSIGHT_MAX_DISTANCE = 0.40` for facts, `_PERSONA_INSIGHT_MAX_DISTANCE = 0.45` for persona notes. Admin/debug callers get the original behaviour by leaving `max_distance=None`. | `apps/ai-agents/app/repositories/insight_repository.py`, `apps/ai-agents/app/services/memory_service.py`, `apps/ai-agents/app/services/chat_service.py` | `tests/unit/test_insight_repository_threshold.py` (3 cases) |
| **A.3 Pre-insert insight dedupe** | `MemoryService.store_insights` now batch-embeds candidates first (one round-trip) and runs a strict `cosine_distance ≤ 0.15` lookup against same-user/same-category insights before each insert. On hit: reuse the existing row, or update it in place when the new confidence is ≥ existing + 0.10. New `dedupe=False` flag for callers that should bypass (e.g. slang calibrator's JSON-blob content). | `apps/ai-agents/app/services/memory_service.py`, `apps/ai-agents/app/services/chat_service.py` | `tests/unit/test_memory_service_dedupe.py` (5 cases) |
| **A.4 Persona chain anti-self-reinforcement** | `_PERSONA_EVOLUTION_TEMPLATE` gained an explicit ANTI-AUTORREFUERZO rule: words appearing only in the avatar's response are not evidence of the user's style. Adoption only counts when the user repeats, confirms, or contradicts. Verified the slang calibrator already only sees user-authored messages (no fix needed there). | `apps/ai-agents/app/chains/persona_evolution_chain.py` | `tests/unit/test_persona_chain_prompt.py` (3 cases) |
| **A.5 Doc updates** | This file: §3.1.1 records the dedupe path; §3.1.2 records the anti-self-reinforcement guardrail; §8 retrieval table records the new distance ceilings; §10 end-to-end loop reflects the richer Rails payload. | `MEMORY_AND_TRAINING.md` | n/a |

**Decisions baked in**:

- **Cosine ceilings**: 0.40 for user facts, 0.45 for persona, 0.15 for dedupe. These are starting points — re-tune after a week of trace data shows what real distance distributions look like.
- **Confidence uplift for dedupe replacement**: 0.10. Below this, the new row is treated as "same fact, no new evidence" and reuses the existing row.
- **Slang calibrator opts out of dedupe**: its JSON-blob content embedding is dominated by JSON structure, not values, so two calibrations with different formality readings would falsely register as near-dupes. Slang is overwrite-style memory anyway.
- **Persona reads both turns, but treats them asymmetrically**: the chain still reads `assistant_response` because relationship-building patterns *do* live in the avatar's choices — but the prompt now tells the LLM that the assistant's own phrases are evidence of the avatar, not the user.

**Test suite**: 115 tests passing (104 prior + 11 new across A.2 / A.3 / A.4).

**Deferred to Wave B (next session)**: insight `status` column for contradiction/correction handling (A2.3), per-category confidence floors (A2.4), `user_style_profiles` table (A3.1), durable Sidekiq-driven post-turn learning (A5), eval harness (A7).

---

### 2026-05-04 — Phases 1–18: events, summaries, transcript-chunks, and observability

The first comprehensive build of the memory + training stack on top of the
Phase-0 baseline. Eighteen phases shipped in one focused session, all
described in detail in §14 above. At-a-glance summary:

| Group | Phases | What shipped |
|---|---|---|
| **Events as a first-class substrate** | 1–6 | `user_events` table, `EventExtractionChain` (hybrid LLM + dateparser), `EventRepository`, `EventService`, `_get_upcoming_events` retrieval, "PRÓXIMOS COMPROMISOS" prompt section, admin endpoints, GDPR symmetry, 22 unit tests. |
| **Events from non-chat sources** | 7, 11 | Audio transcripts → events (Phase 7); Facebook/Twitter posts → events with regex pre-filter, 6-month cutoff, `Semaphore(5)` concurrency, confidence floor 0.7 (Phase 11). |
| **Style + register fidelity** | 8, 9, 10 | Formality directive prompt section (Phase 8); knowledge_level unified — Rails canonical 1–10, FastAPI accepts as-is (Phase 9); reactive location context — privacy-gated, coords-only (Phase 10). |
| **Conversation summarization** | 12, 13 | `ConversationSummaryChain` + `ConversationSummaryRepository` + `ConversationSummaryService` (atomic supersede-then-create, idempotent by `range_end_message_id`, every-20-turns trigger) on the write side (Phase 12); read side adds `_get_prior_summary` to `_gather_memory`, new "RESUMEN DE LA CONVERSACIÓN" prompt section, history-tail truncation to last 10 entries when summary present (Phase 13). |
| **Verbatim transcript memory** | 14 | `audio_transcript_chunks` table + IVFFlat cosine index + sentence-aware `transcript_chunker.chunk_transcript`. Audio route runs chunk + embed alongside insight + event extraction (3 concurrent awaits). New `_get_relevant_transcript_quotes` retrieval pool (top-3 cosine, distance ≤ 0.25). "FRAGMENTOS RELEVANTES" prompt section. GDPR symmetry. |
| **Web-search engagement capture** | 15 | `SearchEngagementChain` (LCEL, conservative; floor 0.7) + `SearchEngagementService` with two-turn correlation. `web_search` tool stashes via contextvars + in-process LRU (5-min TTL). `take_prior_search_for` invoked at request entry BEFORE the agent runs to avoid TOCTOU. Persists `preference` insight with `source="web_search:<md5(query)[:12]>"`. |
| **Operational durability** | 16, 17, 18 | Rails `social_data_snapshots` archive table (FK CASCADE + composite index, retention=12 per user/platform) so future redrives can replay against the original payload (Phase 16); `EventService` consolidation — chat / audio / social all delegate through the same `extract_and_store_from_text` entrypoint (Phase 17); `/internal/memory/{user_id}/snapshot` admin endpoint + `apps/ai-agents/scripts/dump_user_memory.py` CLI for cross-substrate observability (Phase 18). |

**Migrations shipped** (5 total):
- FastAPI: `a1b2c3d4e5f6_add_user_events.py`, `c2d3e4f5a6b7_extend_conversation_summaries.py`, `d3e4f5a6b7c8_create_audio_transcript_chunks.py`.
- Rails: `20260506000001_add_share_location_with_avatar_to_users.rb`, `20260506000002_create_social_data_snapshots.rb`.

**Notable decisions made during the build**:

- Events store has no embedding column — retrieval is filter-by-time (`occurs_at BETWEEN now AND now+horizon`), not cosine.
- `EventExtractionChain` uses **drop-on-disagreement** when LLM and dateparser disagree by >2 days, *not* prefer-dateparser as the original plan suggested. Smoke testing showed dateparser unreliable for Spanish weekday phrases, so deferring to it on disagreement would silently corrupt good LLM output.
- Knowledge_level: Rails canonical (1–10), FastAPI passes through. Prompt renders 1–5 by halving for stylistic stability — the displayed scale doesn't need to change when the underlying formula evolves.
- Search-engagement uses contextvars + in-process LRU rather than threading user/conv args through the agent + tool builders — the tool surface stayed untouched.

**Test suite at the close**: 104 tests passing.

---

## 18. What's intentionally not included

Some gaps were considered and consciously deferred:

- **Recurring events** ("every Tuesday") — single-occurrence-only in v1.
- **`EventUpdateChain`** for natural-language cancel/move — needs entity resolution against existing rows; v2.
- **Reverse-geocode service** — the LLM infers city from `(lat, lng) + country` cheaply; revisit if signal quality drops.
- **Multi-language prompts** — extraction prompts are Spanish-first; multi-lang is its own phase.
- **Transcript-chunk eviction job** — storage growth is bounded; revisit in 6–12 months if hit-rate is low.
- **Sentiment chain in post-turn tasks** — emotional state is already captured by the `emotion` insight category; sentiment is available as an ad-hoc endpoint but doesn't need to fire every turn.
- **Web-search content embedding** — only engagement-derived insights are persisted; raw search results stay ephemeral.
- **Hierarchical summary tree** — single-level rolling summary is enough for the conversation lengths we see today.
