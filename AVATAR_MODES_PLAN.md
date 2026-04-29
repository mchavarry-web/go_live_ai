# AVATAR_MODES_PLAN

User-selectable behavior modes for the avatar. Initial set: **Profesional**, **Amistades**, **Citas**. Each mode constrains tone, register, dialect adoption, and the avatar's relational stance with the user.

The mode is a context the user picks; the avatar reshapes its replies and its persona-evolution behavior accordingly. Switching is one tap from Perfil, just under the avatar header.

> Status: **plan only — no code yet.** Open decisions are flagged below; please answer them before implementation starts.

---

## Why this is non-trivial

The naive read is "just a label and three sets of canned instructions in the prompt." That's most of the work, but two pieces force real architectural thinking:

1. **Persona evolution is mode-specific by nature.** The avatar's voice with you in Profesional is genuinely a different artifact than its voice with you in Citas. If we let `PersonaEvolutionChain` write to one shared bucket, the Profesional avatar will start absorbing the Citas tone and vice versa.
2. **User facts are NOT mode-specific.** Your name, your job, your kid's birthday — those are one truth across all three modes. Splitting them three ways means manually promoting facts between modes, which is bad UX.

So the data model has to draw a line down the middle: **user-fact memory is shared, persona memory is mode-scoped**. This is the central design call this plan rests on.

---

## Open decisions (please answer)

I've put a recommendation on each — feel free to override.

### 1. Memory partition philosophy

- (a) **Shared user facts + mode-scoped persona evolution** — recommended.
- (b) Everything partitioned per mode (three independent avatars sharing a user record).
- (c) Single shared pool, mode acts purely as a prompt-time filter (no data partitioning).

Recommendation: **(a)**. Implementation impact described below assumes this.

### 2. Conversation–mode binding — RESOLVED: seamless

**Decided: switching mode is purely behavioral.** When the user switches mode while a chat is open, the avatar's NEXT reply reflects the new mode tone; nothing else changes. No conversation locking, no fork, no archive. A single thread can contain Profesional-tone and Citas-tone replies side by side after a switch — that's intentional.

Concretely:
- `conversations` table does NOT get a `mode` column.
- `audio_sessions` does NOT get a `mode` column either (same logic: read live).
- Mode lives only on `Avatar.active_mode` (+ `mode_message_counts` for the Citas ramp).
- The chat job reads `current_user.avatar.active_mode` at generation time and ships it to FastAPI in the request payload.
- Persona evolution still mode-scopes via the `source` string on the *insight* row, not via a property of the conversation.

### 3. Citas ramp mechanic

You said "in Citas, not initially but ok as time goes on." How do we measure "as time goes on"?

- (a) **Message-count thresholds** within Citas mode (e.g. <30 msgs = formal, 30–150 = warmer, 150+ = relaxed). Recommended.
- (b) Calendar time since first Citas message (e.g. <7 days, <30 days).
- (c) Sentiment / response-quality driven (avatar reads how the user reacts and ramps when reception is positive).
- (d) Manual: user can tap "loosen up" once they're comfortable.

Recommendation: **(a)** for v1. Simple, deterministic, easy to test. (c) is the right long-term answer but needs more wiring.

Concrete proposal for thresholds: `nascent` (0–30 messages), `warming` (30–150), `established` (150+). Configurable per-user later if needed.

### 4. Naming (Spanish UI labels)

- "Amistades" is grammatically the noun "friendships" — slightly stiff. **"Amigos"** reads more natural.
- "Citas" is fine.
- "Profesional" is fine.

Recommendation: **Profesional / Amigos / Citas**. Confirm.

### 5. Mode visibility

Where do we show the active mode?

- (a) **Profile header (mandatory) + small chip in chat header (recommended)**.
- (b) Profile only.
- (c) Profile + chat + an indicator on each conversation row in the list.

Recommendation: **(a)**. Profile is the switch; chat header is a passive reminder so the user doesn't accidentally send a Citas-tuned message in Profesional mindset.

### 6. Default for existing users on migration

All current avatars have to be assigned a mode at migration time. Options:

- (a) **All existing users default to Amigos** — closest to current behavior. Recommended.
- (b) Force everyone through a one-time mode-picker on next app open.

Recommendation: **(a)** with a non-blocking banner on first open ("Tu avatar ahora tiene modos…") that links to Perfil.

### 7. Avatar appearance per mode

- (a) **Same appearance, behavior changes only**. Recommended for v1.
- (b) Optional appearance overrides per mode (e.g. different color in Citas).

Recommendation: **(a)**. Adds risk; defer to v2 if requested.

### 8. Onboarding flow impact

Existing onboarding sets `formality_level`, `country`, etc. With modes, that single formality_level no longer makes sense (Profesional ≠ Citas formality).

- (a) **Keep onboarding as-is; treat its `formality_level` as the per-mode override for Amigos only.** Profesional and Citas have their own hard-coded baseline. Recommended.
- (b) Re-do onboarding to ask formality per mode (3× the questions).
- (c) Drop `formality_level` entirely; modes encode it.

Recommendation: **(a)**.

### 9. Tone of "Profesional" — how strict?

- (a) **Strict**: no colloquialism, no regional markers, no humor, formal register, "usted" is OK if context calls for it. Like LinkedIn DMs. Recommended.
- (b) Relaxed-formal: tu but tasteful, light humor allowed, no regional slang.
- (c) User-configurable strictness slider per mode.

Recommendation: **(a)**. Easier to soften later than to harden once people are used to it.

### 10. Tone of "Citas" at the `nascent` stage

This one is delicate.

- (a) **Cordial, attentive, light flirtation acceptable, no sexual content, no possessive language, no "babe"-style petnames yet.** Recommended.
- (b) Strictly platonic until escalated.
- (c) Already affectionate from msg 1.

Recommendation: **(a)**. Defer petnames / inside-joke nicknames to the `warming` stage.

### 11. Switching mode wipes / preserves persona memory

When the user switches from Citas → Profesional, what happens to Citas persona notes?

- (a) **Preserved silently**, not used in Profesional. If they switch back, Citas memory resumes. Recommended.
- (b) Visible to the user in Perfil (per-mode persona view).
- (c) Wiped on switch.

Recommendation: **(a)** for v1. (b) is a nice UI for v1.5.

### 12. Phase-2 audio sessions and modes

Audio training sessions (the feature we just shipped) — does each session have a mode?

- (a) **Yes, locked at start.** Audio recorded in Citas tags its insights with mode. Recommended.
- (b) No, audio is mode-agnostic (all sessions feed into the shared user-fact pool only, never persona).

Recommendation: **(a)**. Audio insights for personal_history, preference, etc. → shared. But audio-derived persona patterns → tagged with the session's mode.

---

## Architecture (assuming the recommended answers above)

### Data model changes

#### Rails (`apps/backend`)

Migration `add_mode_to_avatars`:

```ruby
add_column :avatars, :active_mode, :string, null: false, default: "friends"
add_index  :avatars, :active_mode
# Per-mode lifetime user-message counters used by the Citas ramp +
# future analytics. e.g. {"professional"=>4, "friends"=>120, "dating"=>17}
add_column :avatars, :mode_message_counts, :jsonb, null: false, default: {}
```

`Avatar::MODES = %w[professional friends dating].freeze`. Stored as English strings (matches the rest of the codebase's `provider`, `category` enums); the UI translates labels in Spanish.

**No `mode` column on `conversations` or `audio_sessions`** — per decision 2, mode is read live from `avatar.active_mode` at generation/extraction time, never persisted on the artifact.

#### FastAPI (`apps/ai-agents`)

`UserProfile` schema gets:

```python
active_mode: Literal["professional", "friends", "dating"] = "friends"
mode_message_count: int = 0     # in the active mode, used by the Citas ramp
```

`InsightCategory.AVATAR_EVOLUTION` keeps as-is. The mode is encoded in the `source` string the chain writes:

```
source = f"persona_update:{active_mode}"     # was: "persona_update"
```

`_get_persona_insights` filters via `LIKE 'persona_update:<mode>'`. Existing rows with bare `persona_update` get treated as `friends` (back-compat shim, removable after a few weeks).

User-fact insights (personal_history, preference, relationship, goal, emotion, health) **stay with their existing source strings** ("conversation", "manual", "audio:<sid>", etc.). They do not gain a mode tag. They are intentionally shared across modes.

### Prompt changes (`app/prompts/avatar_prompts.py`)

New `_build_mode_section(active_mode, mode_message_count)` block, prepended right after the avatar identity section. This is the *strongest* signal in the prompt — it sits above persona, language style, and user facts.

Sketch:

```
MODO ACTIVO: PROFESIONAL
Tu interaccion con esta persona es estrictamente profesional.
- No uses jerga regional ni particulas dialectales (pe, che, vos, etc.).
- No uses tuteo demasiado casual; usted es aceptable si el contexto lo pide.
- Mantene un registro formal: respuestas estructuradas, sin emojis innecesarios.
- No introduzcas humor sin que el usuario lo invite primero.
- No uses apodos ni terminos de cariño.
[…]
```

Three blocks, one per mode. Citas has internal branching by `mode_message_count`:

- `nascent` (0–29):  cordial, atento, sin apodos, sin coqueteo explicito.
- `warming` (30–149): coqueteo ligero permitido, apodos suaves OK, evita posesividad.
- `established` (150+): puedes adoptar el tono que el usuario marca, jerga regional permitida si ya aparece en `prior_persona` confirmada.

The persona-evolution dialect-marker guardrail we just shipped composes correctly with this — it requires 5+ tentative observations before adopting a marker, AND now in Profesional mode the prompt block forbids the avatar from mirroring even one, so no `[obs:]` tentatives ever get generated.

### PersonaEvolutionChain updates

The chain receives `active_mode` so it:

1. Writes the new source string `persona_update:<mode>`.
2. Adapts the prompt to the active mode — in Profesional, the dialect-marker guardrail tightens further: the chain is instructed not to emit `[obs:]` notes for dialect markers at all, since the avatar shouldn't have mirrored them.
3. Reads only mode-scoped prior persona via `_get_persona_insights(active_mode=…)`.

### Rails endpoints

- `PATCH /api/v1/avatar` already accepts a body — extend to accept `active_mode`. Validate against `Avatar::MODES`.
- `MessagesController#create` increments `avatar.mode_message_counts[active_mode]` on each user message persistence (used by the Citas ramp).
- `ChatGenerationJob` reads `avatar.active_mode` and `avatar.mode_message_counts[active_mode]` at run time and includes them in the FastAPI payload.

`AiAgentsClient` passes `active_mode` and `mode_message_count` in the chat request payload.

### FastAPI endpoints

`/internal/chat/generate` and `/internal/chat/stream` accept `active_mode` and `mode_message_count` in `UserProfile`. Plumbed through `ChatService.generate_reply` to `build_avatar_system_prompt`.

### Mobile (Expo)

- `ProfileScreen.js`: a `ModeSwitcher` component right under `AvatarFace + name` block. Three pill buttons; tapping calls `apiService.updateAvatar({ active_mode: 'professional' | 'friends' | 'dating' })`. Optimistic UI; on failure, revert + toast.
- `ChatScreen` header gains a small mode chip (read-only). Tap → navigates to ProfileScreen anchored to the switcher.
- `AuthContext` exposes `user.avatar.active_mode`; mutations go through `refreshUserData()` after a successful PATCH.
- Optional: a one-time onboarding dialog on first open after the migration ("Tu avatar ahora tiene modos…").

### Telemetry

Log every mode switch in Rails (`AvatarModeChangeJob` or just an inline `Rails.logger.info`). Helps debug "the avatar got weird after I switched".

---

## Migration plan (sequenced PRs)

Single PR per app, in this order:

| # | App | Surface |
|---|---|---|
| 1 | `apps/backend` | Migration + `Avatar.active_mode` + `Avatar.mode_message_counts` + PATCH endpoint + counter increment in `MessagesController#create` + payload to FastAPI |
| 2 | `apps/ai-agents` | `UserProfile.active_mode` + `_build_mode_section` + `PersonaEvolutionChain` mode awareness + scoped `_get_persona_insights` + back-compat shim for legacy `persona_update` rows |
| 3 | `apps/frontend` | `ModeSwitcher` in Perfil + chat header chip + `apiService.updateAvatar({ active_mode })` |

Each PR is independently safe to merge: PR 1 ships the column with default `friends` (no behavior change); PR 2 starts honoring it (still `friends` for everyone); PR 3 lets users switch.

No backfill job needed — the migration's `default: "friends"` covers all existing avatars; conversations and audio_sessions don't carry a mode at all.

---

## Test surface

### ai-agents

- `test_mode_section_professional_no_dialect`: build prompt for `active_mode=professional`, assert the negative constraints are present.
- `test_persona_chain_writes_scoped_source`: the chain writes `persona_update:dating` when run in dating mode.
- `test_get_persona_insights_filters_by_mode`: querying with mode=`professional` only returns notes whose source ends with `:professional`.
- `test_dating_ramp_thresholds`: build prompt with mode_message_count=15 → nascent block; 50 → warming; 200 → established.
- `test_legacy_persona_update_falls_through_to_friends`: a row with bare `persona_update` source surfaces only when `mode=friends`.

### Rails

- `Avatar#active_mode` validates against the enum.
- `Conversation` stamps mode at create from avatar.active_mode.
- `PATCH /avatar` rejects unknown modes with 422.

### Frontend

- ModeSwitcher renders 3 pills; tapping fires `updateAvatar`.
- Optimistic toggle reverts on API failure.

---

## Risks / things I'm watching

1. **Memory leakage between modes via the user-fact pool.** The avatar can technically still "know" you in Profesional that you mentioned an ex on a date — because the relationship insight got stored as `relationship`, not as a persona note. This is the right call (single user truth) but the avatar must be told in Profesional NOT to volunteer this kind of data unprompted. Captured in the Profesional prompt block: "no introduzcas hechos personales sensibles sin que el usuario los pida en este turno."

2. **Mode-switch whiplash.** A user switches Profesional → Amigos mid-day. The avatar abruptly drops the formal register on the next reply. That's correct, but UX-jarring. Worth a brief "Cambiaste a Amigos" system note in the chat? Defer to v1.5 unless feedback says it's needed.

3. **Citas ramp gameability.** A user could rapidly rack up 30 short messages to "unlock" warming. The mode_message_count is per mode, lifetime-only. If we want to be precise we'd track distinct conversation sessions instead. Probably overkill for v1.

4. **Persona graduations interact with modes.** The dialect-marker `[obs:…]` tentative system we just shipped: in Profesional, the chain shouldn't be writing tentative obs at all. Need to assert this in the prompt and in tests.

---

## What this plan deliberately does NOT cover

- Custom user-defined modes ("Trabajo Remoto", "Familia"). That's a v2 if user demand exists.
- Sharing modes across users / templates.
- Per-mode avatar appearance (decision 7 = no).
- Per-mode notification settings.
- Auto-switching mode based on recipient identity or time of day.
