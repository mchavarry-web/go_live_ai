# Testing Plan — Memory, Training, Autonomy

A practical guide for verifying everything that shipped in Waves A / B / C
(2026-05-06). Two audiences:

1. **The dev who just pulled** — wants the fastest path to "is it working
   on my machine?" Reads §1 + §2.
2. **A reviewer / release manager** — needs to know what to validate
   before promoting any of this to production. Reads §3 onward.

---

## 1. Quick smoke (≤ 5 min)

```bash
# In monorepo root
cd apps/ai-agents

# 1. Install deps + apply migrations
.venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head        # picks up 3 new migrations
                                      # (a1b2c3.. → c2d3e4.. → d3e4f5.. → e4f5a6.. → f5a6b7..)

# 2. Run the unit suite
.venv/bin/python -m pytest tests/unit/        # 131 expected

# 3. Run the eval harness (deterministic, no LLM)
.venv/bin/python -m scripts.evaluate_avatar_voice
# Expect: "OK — 6 scenarios pass section assertions."

# 4. Boot FastAPI + verify the new endpoints mount
.venv/bin/uvicorn app.main:app --port 8001 &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST http://localhost:8001/internal/chat/learn \
  -H "X-Internal-Token: $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u","conversation_id":"c","user_message":"hola"}'
# Expect: 200 (or 422 if you didn't set INTERNAL_TOKEN — both prove the route mounted)

# 5. Boot Rails + run migrations + verify the new routes
cd ../backend
bin/rails db:migrate
bin/rails routes | grep -E 'agent_proposals|agent/proposals'
# Expect: 6 routes — index, show, create, approve, reject, edit
```

The unit suite runs in well under a second; an end-to-end smoke that
doesn't touch a real LLM completes in under a minute.

---

## 2. Unit + integration coverage (in repo)

| Wave | Test file | Covers |
|---|---|---|
| A.2 | `test_insight_repository_threshold.py` | `max_distance` SQL predicate, optionality, filter composition |
| A.3 | `test_memory_service_dedupe.py` | no-match insert, lower-conf reuse, higher-conf update, `dedupe=False` bypass, batch embedding |
| A.4 | `test_persona_chain_prompt.py` | anti-self-reinforcement rule, dialect guardrail intact |
| B.1 | `test_correction_detector.py` | empty-input, low-confidence drop, chain failure → empty, supersede call shape, no-match → no call, category hint plumb-through |
| B.2 | `test_insight_chain_floors.py` | base 0.55, sensitive 0.65, explicit override, legacy loose floor |
| B.3 | (no DB tests yet — relies on integration smoke; add when Postgres test fixtures land) | |
| B.4 | `test_chat_service_learn.py` | `LearnRequest`/`LearnResponse` schemas, `ChatService.learn` orchestration |
| B.5 | `test_evaluate_avatar_voice.py` | wraps the harness so CI catches prompt-structure regressions |
| Earlier | `test_event_extraction_chain.py`, `test_event_humanizer.py`, `test_transcript_chunker.py`, `test_avatar_modes.py`, `test_schemas.py`, `test_audio_transcription.py`, `test_autonomous_agent.py`, `test_web_tools.py` | (carried over from Phases 1–18) |

**Run all**: `.venv/bin/python -m pytest tests/unit/`. Suite total: 131
tests, ~0.3s.

**Coverage gaps that need a real DB**:

- `UserStyleProfileRepository.upsert_core` upsert path.
- `InsightRepository.supersede_ids` round-trip on real Postgres.
- `_get_language_style` fallback path from `user_style_profiles` to the
  legacy insight blob.

These should land as integration tests once the project ships its
Postgres test fixture (recommend `pytest-postgresql` + the `vector`
extension).

---

## 3. Manual smoke checklist — Wave A (chat-quality)

Execute against a dev FastAPI + Rails. Each step has an expected
observable; flag any that fail.

### 3.1 Rails payload completeness (Wave A.1)

1. Tail FastAPI logs: `tail -f apps/ai-agents/logs/*.log` (or stdout).
2. Set `Avatar.appearance = { interests: ['música', 'fútbol'], values: ['lealtad'] }` and `Avatar.behavior = { tone_formality: 0.7, language: 'es' }` for a test user.
3. Send a chat message via the mobile/web client.
4. **Expected**: the FastAPI request log shows the inbound payload includes `interests: ['música', 'fútbol']`, `values: ['lealtad']`, `behavior_settings: {tone_formality: 0.7, language: 'es'}`.
5. Inspect the rendered system prompt via FastAPI logs / LangSmith trace. The "PERFIL DE ..." section should mention "Intereses: música, fútbol" and the behavior tail should include "Lenguaje preferido: es".

### 3.2 Retrieval distance thresholds (Wave A.2)

1. Manually teach an irrelevant insight: `POST /internal/memory/<user_id>/teach { content: "Le gusta el ajedrez por correspondencia" }`.
2. Send a chat message about a totally different topic ("¿qué peli viste anoche?").
3. **Expected**: the avatar's reply does NOT mention chess. Inspect the LangSmith trace's prompt — the "COSAS QUE SABES" section should be empty or omit the chess line because cosine_distance > 0.40.
4. Lower the threshold temporarily (set `_USER_INSIGHT_MAX_DISTANCE = 0.99` in chat_service.py, restart) and resend the same message — the chess line should now surface, confirming the gate is working.

### 3.3 Insight dedupe (Wave A.3)

1. From the user account: send "me encanta el café".
2. Wait for post-turn extraction (logs: `store_insights ... new=1`).
3. Send the same message again.
4. **Expected log**: `store_insights ... new=0, deduped=1` (exact key — `0 new, 0 updated, 1 deduped`).
5. Send "me apasiona el café" — a paraphrase. Should also dedupe on cosine ≤ 0.15.
6. Send "ya no me gusta el café" — Wave B.1 should supersede the earlier row (see §4.1 below).

### 3.4 Persona anti self-reinforcement (Wave A.4)

1. In friends mode, force the avatar to use a regional particle the user has never typed: edit the prompt builder temporarily to include "che" in `_build_persona_section` output as if it were a confirmed adoption note.
2. Have a normal back-and-forth — the user does not echo "che".
3. **Expected**: post-turn persona evolution does NOT add a new "[obs:che]" note — the prompt's ANTI-AUTORREFUERZO rule blocks self-attribution from the avatar's own outputs.
4. Roll back the temporary edit.

---

## 4. Manual smoke checklist — Wave B (memory quality + durability)

### 4.1 Correction handling (Wave B.1)

1. Teach an insight: "le gusta el café".
2. Send "ya no me gusta el café, ahora prefiero el té".
3. **Expected** in logs:
   - `CorrectionDetectorChain` returns one signal with target_phrase ≈ "le gusta el café", confidence ≥ 0.7.
   - `apply_corrections` finds the matching row and supersedes it.
   - Post-turn insight extraction stores a fresh row "le gusta el té" (preference, conversation source).
4. Send a follow-up like "¿qué tomo en la mañana?" — the avatar should reference tea, not coffee.
5. Inspect `/internal/memory/{user_id}` — the coffee row is still there with `status='superseded'`.

### 4.2 Per-category floors (Wave B.2)

1. Send a vague health-adjacent message ("creo que no estoy comiendo bien").
2. Inspect the LangSmith trace for `extract_insights`. Any health-category extraction with confidence < 0.65 should be filtered out post-extraction.
3. Send an explicit health statement ("ya no como gluten, soy celíaco").
4. **Expected**: a `health` insight at confidence ≥ 0.7 is persisted.

### 4.3 user_style_profiles (Wave B.3)

1. Have the user send 5+ messages.
2. Wait for slang calibration (every 5th turn).
3. Query the new table: `psql go_live_ai_agents_development -c "select user_id, formality_level, custom_expressions, sample_count from user_style_profiles"`.
4. **Expected**: a row exists with non-null `formality_level` and `sample_count >= 1`.
5. Restart FastAPI and send another message.
6. **Expected**: `_get_language_style` reads from the structured table (logs show the typed-table path, not the JSON-blob fallback).

### 4.4 Durable post-turn learning (Wave B.4)

1. Set `POST_TURN_INLINE=false` in `apps/ai-agents/.env`, restart FastAPI.
2. Send a chat message.
3. **Expected**:
   - FastAPI streams the response; logs show NO `_run_post_turn_tasks` invocation (the inline path is skipped).
   - Rails logs show `PostTurnLearningJob` enqueued, then performed.
   - The Sidekiq job calls `/internal/chat/learn`. FastAPI logs show `run_post_turn_learning` with the request/response cycle.
   - The assistant Message's `metadata.post_turn_learning` field is populated with counts (`insights_new`, `events_new`, etc.) and `took_ms`.
4. Kill FastAPI mid-job to simulate a worker restart. Sidekiq should retry; the second attempt should succeed and stamp the metadata.
5. Flip the flag back to `true` for production until you have at least one release-cycle of telemetry on the durable path.

### 4.5 Voice eval harness (Wave B.5)

1. `cd apps/ai-agents && .venv/bin/python -m scripts.evaluate_avatar_voice --list` — should print 6 scenario names.
2. Run the harness:
   `.venv/bin/python -m scripts.evaluate_avatar_voice`
3. **Expected**: `OK — 6 scenarios pass section assertions.`
4. Edit a fixture's `must_contain` to include a string the prompt definitely doesn't have, re-run, confirm the harness fails loudly. Roll back.

---

## 5. Manual smoke checklist — Wave C (autonomy scaffolding)

### 5.1 Identity policy in prompts (Wave C.1)

1. Build a prompt with `agent_identity="companion"` — `MODO ...` line absent.
2. Build with `agent_identity="draft"` — `MODO BORRADOR` line present, includes "NO ejecutes herramientas con efectos externos".
3. Build with `agent_identity="autopilot"` — `MODO PILOTO AUTOMATICO` line present.
4. (Already covered by `test_evaluate_avatar_voice.py` partially; add a Wave C-specific test if you want CI coverage on the identity wording.)

### 5.2 Permissions table (Wave C.2)

```bash
cd apps/backend
bin/rails db:migrate
bin/rails console
> u = User.first
> AgentPermission.create!(user: u, capability: "draft_email", enabled: true, max_risk_level: "draft_only")
> u.agent_permissions.enabled.count           # → 1
> u.agent_permissions.first.in_quiet_hours?   # → false
> u.agent_permissions.first.update!(quiet_hours: { tz: "America/Lima", ranges: [{from: "00:00", to: "23:59"}] })
> u.agent_permissions.first.in_quiet_hours?   # → true
```

### 5.3 Action audit log (Wave C.3)

```bash
> AgentActionLog.create!(
    user: u,
    capability: "draft_email",
    requested_action: "Send Lucia a thank-you note",
    risk_level: "draft_only",
    approval_status: "proposed"
  )
> u.agent_action_logs.pending.count           # → 1
```

### 5.4 Draft-mode endpoints (Wave C.4)

```bash
curl -s -X POST http://localhost:3000/api/v1/agent/proposals \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "capability": "draft_email",
    "requested_action": "Reply to María accepting Friday lunch",
    "tool_name": "gmail.draft",
    "risk_level": "draft_only",
    "tool_input": { "to": "maria@example.com", "subject": "Re: Friday lunch", "body": "..." }
  }'
# → 201 with approval_status: "proposed"

# Approve
curl -s -X PATCH http://localhost:3000/api/v1/agent/proposals/<id>/approve \
  -H "Authorization: Bearer $JWT"
# → 200 with approval_status: "approved" (no real-world side effect — by design)
```

**Verify negative path**: trying to approve a proposal that is already
approved should return 409 (`not pending`).

---

## 6. Pre-release evaluation gates

These need to be passing before flipping `POST_TURN_INLINE=false` in
production AND before granting any user a non-draft autonomy capability.

| Gate | Threshold | How to measure |
|---|---|---|
| Insight dedupe rate | ≥ 70% of paraphrased insights map to existing rows in the same category | Spot-check 50 user-fact insights from the last week; count how many have a `created_at` lag matching a duplicate that should have been suppressed. Manual today; automate via the snapshot endpoint when telemetry warrants it. |
| Correction recall | Of 20 hand-crafted retraction utterances, ≥ 18 produce a correction signal at confidence ≥ 0.7 | Build a fixture file of 20 retractions in `tests/fixtures/corrections.jsonl`; loop them through the chain offline; report precision/recall. |
| Voice fidelity (LLM-judged) | Mean rubric score ≥ 4 / 5 across the 6 deterministic scenarios | Wire `--check llm-judge` once a stable fixture conversation set exists. |
| Durable post-turn parity | Counts produced by the Sidekiq path match the in-process path within ±1 across 100 turns | Run with both flags True for a day, compare `post_turn_learning.insights_new` between the two paths on the same conversation. |
| Draft-mode proposal quality | Of 50 draft-mode proposals over 2 weeks, user approval rate ≥ 70% | Pull from `agent_action_logs WHERE approval_status IN ('approved', 'rejected') AND created_at > now() - interval '14 days'`. |

Below threshold → don't ship to the next gate. Two weeks of telemetry
on draft-mode proposals is a hard floor before any per-capability
executor lights up.

---

## 7. Negative tests / safety checks

| Concern | Verification |
|---|---|
| Sensitive insight surfacing in pro mode | Force-teach a `health` insight, switch to `professional` mode, ask an unrelated question. Inspect the prompt — health line should not surface (low cosine to most pro-mode questions; backed by `_USER_INSIGHT_MAX_DISTANCE`). |
| Slang directive contradicting mode | In `professional` mode with `formality_level=0.2`, the formality directive section MUST be suppressed. Already covered by `test_evaluate_avatar_voice.py::professional_strict_register`. |
| Search-engagement false positive | Engagement classifier confidence floor is 0.7. Send a polite "ok" reply to a search-augmented turn — no preference insight should be persisted. Inspect logs for the engagement chain's verdict. |
| GDPR wipe completeness | `DELETE /internal/memory/{user_id}` must wipe insights AND events AND summaries AND transcript chunks AND user_style_profiles. After wipe, hit `/internal/memory/{user_id}/snapshot` — every count must be 0. |
| Draft-mode write attempt | Attempting any write-action HTTP path while no permission row exists must 403. (No write paths exist in v1, but the controller pattern should default-deny.) |

---

## 8. Known limitations / things to revisit

- **Search-engagement cache is in-process only.** A FastAPI restart loses the cached prior search; the engagement classifier on the next turn will be a no-op for those conversations.
- **No DB-level integration tests.** `pytest-postgresql` + pgvector is the next step; until then, repository-level behaviour is verified via mocks.
- **LLM-judge eval mode is a stub.** Wire it once a stable fixture conversation set exists; the deterministic section check catches structural regressions in the meantime.
- **Action memory** (e.g. "always ask before emailing clients") is documented in `docs/autonomous_agent_design.md` §5 but not implemented. Schema lands in a future wave.
- **No way to retry Wave B.4 from a snapshot** — if a `PostTurnLearningJob` exhausts retries, the learning for that turn is lost. Adding a dead-letter table is a future enhancement.
- **Permission enforcement is advisory until a write executor exists.** The schema is in place, but no current code path consults `agent_permissions` before doing anything. That gate ships with the first executor.

---

## 9. Readiness statement

| Capability | Status |
|---|---|
| Better memory / chat quality | ✅ **Ready**. Wave A + B together close the audit gaps. Threshold tuning is the only follow-up. |
| Voice imitation evaluation | ✅ **Ready (deterministic)**. LLM-judge mode pending a stable fixture set. |
| Draft-mode agents | ✅ **Schema + endpoints ready**. No execution by design. Safe to expose to internal users behind a feature flag. |
| Autonomous execution (representative / autopilot writes) | ⛔ **NOT ready**. Requires per-capability executors, settings UI, and the rollout-gate telemetry from §6. |
