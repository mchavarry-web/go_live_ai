# AVATAR_MODES_IMPLEMENTATION

Progress log for the avatar-modes feature. Source plan: [`AVATAR_MODES_PLAN.md`](./AVATAR_MODES_PLAN.md).

**PR order (each independently mergeable):**
1. `apps/backend` (Rails) — data + endpoint + payload to FastAPI
2. `apps/ai-agents` (FastAPI) — mode-aware prompt + scoped persona retrieval
3. `apps/frontend` (Expo) — ModeSwitcher + chat-header chip

PR 1 + 2 ship together. PR 3 depends on both being deployed.

---

## PR 1 — `apps/backend` (Rails)

Status: **code complete + smoke-tested live**

- [x] Migration `20260429000001_add_active_mode_to_avatars`: adds `active_mode` (default `friends`, indexed) and `mode_message_counts` (jsonb, default `{}`)
- [x] `Avatar::MODES = %w[professional friends dating]`; `Avatar::DATING_NASCENT_LIMIT = 30`, `DATING_WARMING_LIMIT = 150`
- [x] `Avatar` validates `active_mode` inclusion with friendly message
- [x] `Avatar#message_count_in(mode)`, `#message_count_in_active_mode`, `#increment_mode_message_count!` (atomic via `jsonb_set` SQL)
- [x] `Api::V1::AvatarsController#update` accepts optional `active_mode` param; serializer surfaces `active_mode` + `mode_message_counts`
- [x] `Api::V1::AuthController#avatar_json` mirrors the new fields so `/auth/me` and login return them
- [x] `Api::V1::MessagesController#create` calls `current_user.avatar.increment_mode_message_count!` on each user message
- [x] `ChatGenerationJob#user_profile` includes `active_mode` + `mode_message_count` in the FastAPI payload
- [x] Live smoke (admin user): GET avatar shows fields, PATCH switches mode, invalid mode → 422 with friendly Spanish error, sending two messages in dating mode bumps `{"dating": 2}`

### Live smoke output

```
=== invalid mode — friendly error now ===
{"error":"Active mode must be one of: professional, friends, dating"}  HTTP 422

=== set mode=dating, send 2 messages ===
  PATCH HTTP 200
  current counts after 2 msgs in dating: {'dating': 2}
```

---

## PR 2 — `apps/ai-agents` (FastAPI)

Status: **code + tests + live smoke complete**

### Schema
- [x] `UserProfile` gains `active_mode: Literal["professional","friends","dating"] = "friends"` and `mode_message_count: int = Field(default=0, ge=0)`
- [x] `ChatService._extract_user_profile` reads + plumbs both fields
- [x] `AvatarChain._build_system_prompt` passes both into `build_avatar_system_prompt`

### Prompt
- [x] `app/prompts/avatar_prompts.py`: `_build_mode_section(active_mode, mode_message_count)` returns one of 5 blocks (Profesional / Amigos / Citas-nascent / Citas-warming / Citas-established)
- [x] `templates/avatar_system.txt` gains a `{mode_section}` placeholder right after `FECHA Y HORA ACTUAL`, anchoring the mode constraints near the top of the prompt
- [x] Citas thresholds: `< 30` → nascent; `< 150` → warming; `>= 150` → established
- [x] Profesional block forbids dialect particles, voseo, casual tuteo, humor without invitation, petnames, and unprompted disclosure of sensitive personal facts

### Persona evolution
- [x] `_evolve_and_store_persona` takes `active_mode` and writes `source = f"persona_update:{active_mode}"`
- [x] `_get_persona_insights` filters retrieved notes by `source == "persona_update:<mode>"` (oversamples top_k=15, trims to 5)
- [x] Back-compat: legacy rows with bare `persona_update` source surface only when active_mode == "friends"
- [x] Both `_gather_memory` and `_run_post_turn_tasks` pass `active_mode` through

### Tests (13 new, 79 total passing)
- [x] `test_avatar_modes.py::TestModeSection` (6) — block selection per mode + Citas count thresholds + unknown-mode fallback
- [x] `test_avatar_modes.py::TestBuildAvatarSystemPromptWithMode` (3) — block lands in full prompt; warming picked at count=50; default = friends
- [x] `test_avatar_modes.py::TestUserProfileMode` (4) — schema validation: defaults, accepted values, rejected values, count must be non-negative

### Live smoke (fresh uvicorn on :8002, real LLM)
Same input message ("Cuéntame de ti") in three modes:
- **Profesional**: "Soy Lumi… Mi **función** es ofrecerte una visión cercana, opinar con honestidad y **ayudarte a organizar** tus ideas." — formal register, structured.
- **Amigos**: "Mira, soy Lumi… La idea es charlar con vos como si fuera él." — casual opener, relaxed.
- **Citas (nascent, count=0)**: "Uh, bueno… soy Lumi, un avatar digital inspirado en Augusto. Pensé que me describiría como alguien curioso, amante de las charlas profundas…" — hesitant, more personal, no flirtation, no petnames.

---

## PR 3 — `apps/frontend` (Expo)

Status: **code complete; iOS production bundle succeeds**

- [x] `components/avatar/ModeSwitcher.js` — three-pill segmented control with optimistic toggle + revert on PATCH failure; mounted in `ProfileScreen` directly under `KnowledgeBar`
- [x] `apiService.updateAvatar` extended to accept `active_mode`; PATCH body includes it when present
- [x] `ProfileScreen` calls `refreshUserData()` after a mode change so the `AuthContext`-backed `user.avatar.active_mode` stays fresh
- [x] `AvatarHeader` gains a small read-only mode chip ("Profesional" / "Amigos" / "Citas") that taps to ProfileTab → ProfileHome via `onModeChipPress`
- [x] `ChatScreen` wires `onModeChipPress` to navigate cross-tab so the user can switch from chat
- [x] `npx expo export --platform ios` bundles all 1700+ modules cleanly

---

## Notes
- Decision 2 was overridden post-plan: switching mode is **seamless**. No `mode` column on conversations or audio sessions; mode is read live from `avatar.active_mode` at every chat generation.
- This means a single conversation thread can contain Profesional-tone and Citas-tone replies side by side after a switch — intentional.
