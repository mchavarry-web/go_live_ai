# AUDIO_TRAINING_PLAN_IMPLEMENTATION

Progress log for the Audio Training feature. Source plan: [`AUDIO_TRAINING_PLAN.md`](./AUDIO_TRAINING_PLAN.md).

**Strategy:** one PR per app, each shipping the full Phase 1 surface for that app.
**PR order (each independently mergeable, frontend gates on backend):**
1. `backend` (Rails)
2. `ai-agents` (FastAPI)
3. `frontend` (Expo)

Backend and ai-agents PRs can ship together; frontend depends on both being deployed.

---

## PR 1 — `apps/backend` (Rails)

Status: **code complete; ready for tests + PR**

### Migrations
- [x] `audio_sessions` (UUID, FK user (bigint), status state-machine, transcribed_seconds rollup)
- [x] `audio_chunks` (UUID, FK session (uuid), sequence_number unique within session, Shrine `audio_data`)
- [x] `voice_enrollments` (UUID, FK user unique, two Shrine attachments)
- [x] `audio_usages` (daily rollup per user for quota)

### Models
- [x] `AudioSession` — STATUSES + `cancel!` + `finalize_outcome!`
- [x] `AudioChunk` — `AudioChunkUploader::Attachment(:audio)`, `transcript_preview`
- [x] `VoiceEnrollment` — two Shrine attachments + `ready?`
- [x] `AudioUsage` — `upsert_seconds!` with row lock
- [x] `User#audio_sessions`, `User#voice_enrollment`, `User#audio_usages`

### Uploader
- [x] `AudioChunkUploader < Shrine` — `:store_private`, 25MB cap, AAC/m4a/mp3/wav mime allow-list

### Controllers
- [x] `Api::V1::AudioSessionsController` — index/show/create/destroy + finish/cancel/wipe_all
- [x] `Api::V1::AudioChunksController` — idempotent create with `Idempotency-Key` header
- [x] `Api::V1::VoiceEnrollmentsController` — show/create/destroy

### Jobs
- [x] `AudioChunkProcessJob` — quota check → multipart transcribe via FastAPI → persist → extract insights → roll usage
- [x] `AudioSessionFinalizeJob` — sets ready / ready_with_errors / failed
- [x] `AudioSessionCleanupJob` — hourly; abandons stale recording / rescues stuck processing

### Services
- [x] `AudioQuota` — `snapshot`, `allow_session_start?`, `allow_chunk_seconds?`, `record!`
- [x] `AiAgentsClient#transcribe_chunk` (multipart bytes)
- [x] `AiAgentsClient#extract_audio_insights`
- [x] `AiAgentsClient#delete_insights_by_source` (exact + prefix)

### Routes & schedule
- [x] Routes added under `namespace :api → namespace :v1`; verified via `bin/rails routes`
- [x] `config/schedule.rb` — `AudioSessionCleanupJob` every hour

### Smoke
- [x] All 4 migrations apply cleanly to local dev DB
- [x] Rails runner end-to-end: create session → create chunk → cancel → quota snapshot

### Tests
- [ ] Controller / integration tests (deferred — minitest harness exists but coverage is light across the codebase; will add once frontend is wired and end-to-end manual flow is verified)

---

## PR 2 — `apps/ai-agents` (FastAPI)

Status: **code + tests complete; ready for PR**

### New module
- [x] `app/audio/__init__.py`
- [x] `app/audio/transcription.py` — provider abstraction, OpenAI default
- [x] `app/api/routes/audio.py` — `/transcribe` + `/extract_insights`
- [x] Wire `audio` router in `app/main.py`

### Settings
- [x] `AUDIO_TRANSCRIPTION_PROVIDER` (default `openai`)
- [x] `AUDIO_TRANSCRIPTION_MODEL` (default `gpt-4o-mini-transcribe`)

### Dependencies
- [x] `python-multipart>=0.0.9` added to `pyproject.toml` (FastAPI form parsing for the multipart audio upload)

### Existing modules — extend
- [x] `insight_repository.py#delete_by_source(user_id, source, prefix=False)`
- [x] `memory_service.py#delete_insights_by_source(user_id, source, prefix=False)`
- [x] `memory.py` route — `DELETE /internal/memory/{user_id}/by-source?source=…&prefix=true|false`

### Tests (11 passing)
- [x] `tests/unit/test_audio_transcription.py` — 5 tests: gpt-4o-mini path, whisper-1 segments, missing key, unknown provider, `to_dict`
- [x] `tests/integration/test_audio_routes.py` — 4 tests: /transcribe success + empty-payload 400, /extract_insights with source tag + empty short-circuit
- [x] `tests/integration/test_memory_delete_by_source.py` — 2 tests: exact + prefix
- [x] Full ai-agents suite still green (66 passed)

---

## PR 3 — `apps/frontend` (Expo)

Status: **code complete; ready for `npx expo install` + manual smoke**

### Dependencies
- [x] `expo-audio` (`~1.0.13`) and `expo-file-system` (`~19.0.16`) added to `package.json`
- [x] `app.config.js` — `NSMicrophoneUsageDescription`, Android `RECORD_AUDIO` permission

> Operator step before booting Metro: run `npx expo install expo-audio expo-file-system` to let the SDK pin pull the matching prebuilt native module versions.

### State + services
- [x] `contexts/AudioRecordingContext.js` — provider, chunk rotation, enrollment state
- [x] `services/audioRecorder.js` — expo-audio re-exports + session mode helpers
- [x] `services/audioUploader.js` — AsyncStorage-backed FIFO with `Idempotency-Key`, AppState + NetInfo retry triggers
- [x] `services/apiService.js` — audio session/chunk/enrollment/wipe methods

### Hooks
- [x] Chunk rotation lives directly in `AudioRecordingContext` (no separate hook needed for v1; the timer is internal to the provider)

### Components
- [x] `components/audio/RecordingBar.js` — root-mounted floating bar
- [x] `components/audio/RecordingStateIndicator.js`
- [x] `components/audio/PermissionGate.js`

### Screens
- [x] `screens/audio/VoiceEnrollmentScreen.js` — required start + stop phrase capture
- [x] `screens/audio/AudioHistoryScreen.js` — list + global wipe
- [x] `screens/audio/AudioSessionDetailScreen.js` — chunk transcripts + per-session delete

### Integration
- [x] `App.js` wraps with `AudioRecordingProvider`; `RootNavigator` mounts `RecordingBar` above `MainTabs` for authenticated+onboarded users
- [x] `screens/profile/ProfileScreen.js` — `SOURCE_CONFIG` gains an `audio` entry; `resolveSourceConfig` + `sourceBucketKey` collapse `audio:<sid>` entries under one row
- [x] `screens/settings/PrivacyScreen.js` — danger-zone "Borrar audio entrenado" action
- [x] `navigation/ProfileStack.js` — registers `VoiceEnrollment`, `AudioHistory`, `AudioSessionDetail`

### Tests
- [ ] `audioUploader` queue retry / idempotency unit tests (deferred — frontend has no test harness checked in yet; will add once we land the end-to-end manual smoke)
- [ ] `useChunkRotation` timing test (deferred — rotation lives inside the provider, not its own hook)

### Verification
- [x] All new + edited JS files parse cleanly through `babel-preset-expo`

---

## Decisions reference

Pulled from the plan's "Decisions resolved" section:

| Knob | Value |
|---|---|
| Chunk length | 5 min |
| Daily quota | 480 transcribed min/user/day |
| Default model | `gpt-4o-mini-transcribe` |
| Retention | manual deletion only (no auto-purge) |
| Phrase capture | required, not skippable |
| Encryption | none at app level in v1 |
| Stale session cutoff | 24h |
| Phase 2 non-user audio | discard raw, keep anonymized text |
| Phase 2 enrollment fail | block + retry |

---

## Bugs found & fixed during smoke testing (2026-04-29)

- **`enforce_enrollment!` did `throw :abort` from a regular controller action** (`app/controllers/api/v1/audio_sessions_controller.rb`). Rails only honours `throw :abort` inside callbacks, not plain controller methods, so every `POST /audio/sessions` 500'd with `UncaughtThrowError`. Fixed: filter now returns boolean; caller does `return unless enforce_enrollment!`.
- **`finalize_outcome!` raised `PG::GroupingError`** (`app/models/audio_session.rb`). The `has_many :audio_chunks, -> { order(:sequence_number) }` default scope carries its `ORDER BY` into the `.group(:transcription_status).count` query; Postgres rejects an `ORDER BY` on a column that isn't in `GROUP BY`. Fixed: prepend `reorder(nil)` before grouping.

## Notes & gotchas (filled in as we hit them)

- **Migrations FK type mismatch.** `users.id` is bigint while audio sessions / voice enrollments / audio usages use uuid PKs. Drop `type: :uuid` from `t.references :user` in those migrations; `audio_chunks → audio_session` keeps `type: :uuid` because `audio_sessions.id` is uuid.
- **`python-multipart` is required** for the FastAPI `/internal/audio/transcribe` endpoint (multipart bytes in). Already added to `pyproject.toml`.
- **Pre-existing repository unused imports** (`AsyncSession`, `text` in `insight_repository.py`; `Optional` in `memory_service.py`) are not from PR 2; verified with `git stash` before touching.
- **`expo-file-system` v19 split.** `deleteAsync` now lives at `expo-file-system/legacy`. The uploader imports from `legacy` so chunk cleanup keeps working without rewriting to the new `File` class API.
- **`RecordingBar` mount point.** It calls `useNavigation()`, so it must live inside `NavigationContainer` (not `App.js`). Mounted in `RootNavigator` next to `MainTabs`, behind the same auth/onboarding gate.
- **Phrase capture is required, not skippable.** `AudioRecordingContext.start()` short-circuits with `reason: "enrollment_required"` if the server returns no `ready` enrollment; UI never offers a "skip" affordance.
