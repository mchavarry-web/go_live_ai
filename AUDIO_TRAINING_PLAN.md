# AUDIO_TRAINING_PLAN

A new training pathway for the avatar: **continuous ambient audio**. The user records their day (or chunks of it) and the system extracts insights, behavioral patterns, and over time a voice fingerprint that lets us distinguish the user from everyone else around them.

This complements the three existing pathways:

| Source | What feeds the avatar |
|---|---|
| Conversational chat | direct user statements + insights extracted by `insight_chain` |
| Social ingestion (IG/FB/Twitter/Spotify) | structured posts → platform-specific extractor chains |
| Onboarding questionnaire | static seed (age range, interests, values, personality sliders) |
| **Audio (this plan)** | **transcripts + tone/behavior signals + speaker-attributed memory** |

---

## Goals & non-goals

**MVP goals (Phase 1) — manual recording, transcription, insights, retention:**
- A persistent bottom-bar recording UI with start/stop, elapsed time, and a "recording" indicator.
- An optional onboarding step that captures the two trigger-phrase recordings — these are stored as **text labels + raw audio samples for later** (not yet used to identify the user). Recording the feature is fully manual via button taps in v1; the phrase capture is purely UX scaffolding for Phase 2.
- Continuous recording can run for hours; client cuts the stream into ~5-minute chunks and uploads each chunk independently as soon as it closes.
- Each chunk lands in Rails, gets pushed to FastAPI for transcription, and the transcript is fed to the existing `insight_chain` so the avatar learns from it.
- User can pause / resume / stop / cancel and review session history with transcripts.
- Strict consent UX (always-on REC indicator, first-run legal warning, retention default, per-session and global wipe).
- Server-side daily quota enforcement so a runaway session can't drain the OpenAI bill.

**Phase 2 — speaker identity (the part that needs more samples to be reliable):**
- Voice fingerprinting from the enrolled phrases + accumulated session audio (not the 4-8s phrase alone — see the "Why we defer fingerprinting" sidebar below).
- Speaker diarization so we only keep user-attributed segments as memory.
- On-device wake-word detection so the user can say the trigger phrase hands-free.
- Background-mode recording so the screen can lock during a session.

**Why we defer voice fingerprinting to Phase 2.** Resemblyzer (and any speaker-recognition embedding) is sensitive to clip length and recording conditions. A 4–8 second mobile-recorded utterance gives an embedding with measurable but not reliable accuracy in noisy real-world environments — false positives and negatives are common. The right approach is: (a) collect the trigger phrases in Phase 1 as text + audio, (b) once a user has accumulated minutes of session audio, build a much higher-confidence embedding from the union of those samples, (c) only then turn on diarization-based filtering. Until that day, **Phase 1 transcripts include every voice captured by the mic** — which is precisely why Phase 1 needs strict consent UX and is not the right place to claim "the avatar only listens to you."

**Phase 3:**
- Prosody / tone analysis: pitch, pace, emotional valence per chunk (informs `behavior.tone_*` weights and `slang_calibrator`).
- Multi-speaker conversation modeling: insights about *people the user talks to*, not just the user.
- Real-time streaming transcription for live coaching / interruptions.

**Explicit non-goals (to keep scope sane):**
- No third-party audio (e.g., podcasts, calls). Only first-party microphone capture.
- No always-on continuous capture without explicit user start. Recording is opt-in per session.
- No live conversation analysis in v1 — chunks are processed asynchronously.

---

## End-to-end UX

### First-run setup (gate to feature unlock — Phase 1)

```
User taps recording bar → "Activar entrenamiento por audio"
  → [1/3] Privacy + legal warning modal:
           "Las grabaciones pueden capturar voces de otras personas.
            Solo activa el entrenamiento cuando sea legal grabar en tu
            jurisdicción. Las leyes de consentimiento varían por país y
            por estado/provincia — verifica las tuyas." (Aceptar / Cancelar)
  → [2/3] "Graba la frase que usarás para iniciar una sesión cuando
           tengamos detección de voz (próximamente). Por ejemplo:
           «Iniciar entrenamiento por audio»."
  → record button (hold-to-talk, auto-stops at 4s silence) + playback
  → [3/3] Same for the stop phrase.
  → confirm → upload both clips
  → Rails persists VoiceEnrollment with status="ready" (Phase 1 doesn't
     compute an embedding; it just stores audio + transcript text)
  → user lands back on recording bar, now showing "Listo para grabar"
```

The trigger phrases are **required** in Phase 1 even though they aren't used yet — both phrases must be recorded before the feature unlocks. They serve two purposes: (a) the text labels shown in UI ("Tu frase de inicio: «...»") and (b) raw audio samples that Phase 2 will combine with session audio to produce a reliable voice embedding. Capturing them up-front means Phase 2 can ship without forcing every user back through a re-onboarding flow.

### Steady-state usage

```
User taps "Iniciar" (or, Phase 2, says the wake phrase)
  → mic permission check (one-time)
  → recording starts; bottom bar expands to show:
       elapsed time   ●REC   waveform   [Pausar] [Detener]
  → Every CHUNK_MINUTES (default 5), client:
       • finalizes current file (m4a, AAC, ~96kbps mono, 16 kHz)
       • starts a new file in the same session
       • enqueues uploaded chunk to background upload queue
  → Network-aware queue: if offline, chunks pile up locally; on reconnect, they
     drain in order. Local files retained until server confirms persisted.
  → User taps "Detener" → final chunk closes + uploads + session marked complete
  → Once all chunks of a session have transcripts, "Sesión procesada" appears
     in the user's audio history.
```

### History / management

A new `AudioHistoryScreen` (under Profile or Ajustes):
- List of past sessions, descending by start time
- Per-session: total duration, chunk count, transcript preview, status badge
- Tap → full transcript with timestamps, audio scrubber per chunk
- Per-session "Eliminar" (deletes file + transcript + derived insights flagged with `source="audio:<session_id>"`)
- Global "Eliminar todo el audio" for GDPR-style wipe

---

## Architecture

```
Expo bottom bar
  │ records m4a chunks (5min each) + uploads each as multipart POST
  ▼
Rails (apps/backend)
  • POST /api/v1/audio/sessions             → create session
  • POST /api/v1/audio/sessions/:id/chunks  → upload chunk file
  • POST /api/v1/audio/sessions/:id/finish  → mark session complete
  • GET  /api/v1/audio/sessions             → list w/ status
  • GET  /api/v1/audio/sessions/:id         → detail + chunks + transcripts
  • DELETE /api/v1/audio/sessions/:id       → wipe
  • POST /api/v1/audio/voice_enrollment     → upload start/stop phrase clips
  • DELETE /api/v1/audio/voice_enrollment   → reset enrollment
  │
  │ Stores chunk audio in Shrine (FileSystem dev / S3 prod)
  │ AudioChunkProcessJob (Sidekiq) per chunk → AiAgentsClient#transcribe_chunk
  ▼
FastAPI (apps/ai-agents)
  • POST /internal/audio/transcribe         → multipart audio bytes → returns segments
                                              (v1 contract: Rails streams the file, FastAPI
                                               does NOT pull from a URL; see "Audio transfer
                                               contract" below)
  • POST /internal/audio/extract_insights   → transcript → insights
                                              (delegates to insight_chain w/ source="audio:<sid>")
  • POST /internal/audio/voice_print        → Phase 2: enrollment embedding → pgvector
  • POST /internal/audio/identify           → Phase 2: diarized chunk → speaker labels
```

### Audio transfer contract (Rails → FastAPI)

The first plan draft had FastAPI pulling chunk audio from a URL. That breaks in dev (Shrine's `store_private` lives at `apps/backend/storage/`, not on a public web server) and is a footgun in prod (a leaked or improperly-scoped presigned URL exposes raw audio).

**v1 contract — Rails streams bytes inline.** `AudioChunkProcessJob` reads the chunk through Shrine's IO and POSTs it as multipart form-data to `/internal/audio/transcribe`:

```ruby
# AiAgentsClient#transcribe_chunk
chunk.audio.open do |io|
  multipart = {
    audio:    UploadIO.new(io, "audio/m4a", "chunk_#{chunk.id}.m4a"),
    user_id:  chunk.audio_session.user_id,
    language: chunk.audio_session.metadata["language"]
  }
  http.post("/internal/audio/transcribe", multipart, internal_token_headers)
end
```

This works identically in dev (FileSystem) and prod (S3) because Shrine abstracts the storage backend. FastAPI receives the bytes, hands them to the transcription provider, returns `{text, segments, language}`. No URL ever leaves Rails; nothing FastAPI sees survives the request.

**Phase 2 / S3-only optimization.** When prod chunks routinely cross 10 MB or transcription jobs cluster, switch to **short-lived presigned URLs scoped to a single GET** (`expires_in: 5.minutes`) and have FastAPI download them. This is opt-in via env (`AUDIO_TRANSFER_MODE=presigned`) and only activates when `Shrine.storages[:store_private]` is an `S3` storage. Local dev stays on inline streaming forever.

### Why split this way

- **Rails owns the lifecycle and storage.** Same auth, same Shrine pattern as existing `user_image`. No new auth surface.
- **FastAPI owns the ML.** OpenAI transcription in Phase 1; pyannote + Resemblyzer in Phase 2. All inside the Python venv that already has langchain + pgvector.
- **Sidekiq decouples upload from processing.** A chunk POST returns 202 in <100ms; transcription happens out-of-band like every other AI workload.
- **No raw audio crosses HTTP boundaries unnecessarily.** Rails reads from `store_private`, streams bytes to FastAPI, FastAPI hands to OpenAI. No public URLs. No FastAPI-side persistence of audio.

---

## Data model

### Rails — `apps/backend/db/migrate/`

```ruby
# 20260429000001_create_audio_sessions.rb
create_table :audio_sessions, id: :uuid do |t|
  t.references :user, null: false, foreign_key: true, type: :uuid
  t.datetime :started_at, null: false
  t.datetime :ended_at
  t.integer  :total_duration_seconds, default: 0
  t.integer  :transcribed_seconds,    default: 0   # billed minutes (server-counted)
  t.string   :status, null: false, default: "recording"
  # status: recording | finalizing | processing | ready | ready_with_errors |
  #         cancelled | failed | abandoned | deleted
  t.jsonb    :metadata, default: {}
  t.timestamps
end
add_index :audio_sessions, [:user_id, :started_at]
add_index :audio_sessions, :status

# 20260429000002_create_audio_chunks.rb
create_table :audio_chunks, id: :uuid do |t|
  t.references :audio_session, null: false, foreign_key: true, type: :uuid
  t.integer  :sequence_number, null: false
  t.datetime :started_at, null: false
  t.float    :duration_seconds
  t.text     :audio_data            # Shrine attachment (store_private)
  t.string   :transcription_status, default: "pending"
  # transcription_status: pending | running | done | failed
  t.text     :transcript            # full text (kept here for fast queries)
  t.jsonb    :segments              # [{start, end, text, speaker?}]
  t.string   :language              # ISO 639-1 ("es", "en")
  t.integer  :transcription_attempts, default: 0
  t.jsonb    :metadata, default: {}
  t.timestamps
end
add_index :audio_chunks, [:audio_session_id, :sequence_number], unique: true
add_index :audio_chunks, :transcription_status

# 20260429000003_create_voice_enrollments.rb
create_table :voice_enrollments, id: :uuid do |t|
  t.references :user, null: false, foreign_key: true, type: :uuid, index: { unique: true }
  t.text     :start_phrase_audio_data       # Shrine attachment (Phase 1: stored, not analyzed)
  t.text     :stop_phrase_audio_data
  t.string   :start_phrase_text             # transcript of the recording
  t.string   :stop_phrase_text
  t.string   :status, default: "pending"
  # Phase 1 statuses: pending | ready | skipped
  # Phase 2 adds:    enrolling | failed
  t.float    :embedding_quality             # null in Phase 1; populated by VoicePrintJob in Phase 2
  t.timestamps
end

# 20260429000004_create_audio_usages.rb
# Daily rollup for server-side quota enforcement. Updated by AudioChunkProcessJob
# on successful transcription so a misbehaving client can't bypass the cap.
create_table :audio_usages, id: :uuid do |t|
  t.references :user, null: false, foreign_key: true, type: :uuid
  t.date     :usage_date, null: false              # in user's timezone
  t.integer  :transcribed_seconds, default: 0
  t.integer  :uploaded_chunks,     default: 0
  t.timestamps
end
add_index :audio_usages, [:user_id, :usage_date], unique: true
```

`transcript` and `segments` are stored as plaintext in v1. If the threat model changes later we can wrap them with ActiveRecord encryption (Rails 8 native, already configured in `apps/backend/config/initializers/active_record_encryption.rb`) without a schema change.

### FastAPI — Phase 1: insight bulk-delete by source prefix

Insights extracted from audio reuse the existing `insights` table with `source="audio:<session_id>"`. The current `delete_insight` route only handles one id at a time, so wipe operations need a new endpoint:

```python
# apps/ai-agents/app/api/routes/memory.py — new in Phase 1
@router.delete(
    "/{user_id}/by-source",
    summary="Delete insights matching a source prefix or exact source",
    description="Used for bulk wipe (e.g. all audio insights, or all from one session).",
)
async def delete_insights_by_source(
    user_id: str, source: str, prefix: bool = False, ...
) -> dict:
    deleted = await memory_service.delete_insights_by_source(
        user_id=user_id, source=source, prefix=prefix
    )
    return {"deleted": deleted}
```

Rails calls it as:
- `DELETE /internal/memory/<user_id>/by-source?source=audio:<sid>` for one session
- `DELETE /internal/memory/<user_id>/by-source?source=audio&prefix=true` for "all audio"

Frontend bucket grouping: `ProfileScreen.js`'s `SOURCE_CONFIG` is currently exact-key match. Extend the lookup to **fall through to a prefix match** so anything starting with `audio:` aggregates under one "Audio" entry:

```js
function lookupSourceConfig(source) {
  if (SOURCE_CONFIG[source]) return SOURCE_CONFIG[source];
  const prefix = source.split(":")[0];
  return SOURCE_CONFIG[prefix] || { icon: "ellipse", label: source, color: colors.textSecondary };
}
// And aggregate by prefix when one exists:
const bucketKey = source.includes(":") ? source.split(":")[0] : source;
insightsBySource[bucketKey] = (insightsBySource[bucketKey] || 0) + 1;
```

### FastAPI — Phase 2: voice fingerprint table

```python
# Phase 2 alembic migration — not needed for v1 ship
op.create_table(
    "voice_prints",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
    sa.Column("embedding", Vector(256), nullable=False),
    sa.Column("source_clips", postgresql.JSONB, nullable=False),
    sa.Column("samples_seconds", sa.Float, nullable=False),  # accumulated audio used
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
)
op.create_index(
    "voice_prints_embedding_idx",
    "voice_prints",
    ["embedding"],
    postgresql_using="ivfflat",
    postgresql_ops={"embedding": "vector_cosine_ops"},
)
```

---

## Frontend implementation (Expo)

### Library choice

Use **`expo-audio`** (replaces `expo-av` recording in SDK 54+). It supports AAC/m4a output, pause/resume, metering, and — for Phase 2 — background recording via `setAudioModeAsync({ allowsBackgroundRecording: true })`. Install via the SDK-aware command so the version pin matches the rest of the Expo dependencies (don't hand-pin `^0.4.0` in `package.json`):

```bash
npx expo install expo-audio
```

Background recording is gated by `setAudioModeAsync` flags (set at session start in Phase 2):
```js
import { setAudioModeAsync } from "expo-audio";
await setAudioModeAsync({
  allowsRecording: true,
  allowsBackgroundRecording: true,        // Phase 2 — requires the iOS entitlement
  playsInSilentMode: true,
  shouldPlayInBackground: false,
});
```

`app.config.js` additions:
```js
ios: {
  ...
  infoPlist: {
    ITSAppUsesNonExemptEncryption: false,
    NSMicrophoneUsageDescription:
      "Tu avatar aprende de tus conversaciones y contexto cuando activas el entrenamiento por audio.",
    UIBackgroundModes: ["audio"]   // Phase 2 — required to keep recording when screen is off
  }
},
android: {
  ...
  permissions: [
    "RECORD_AUDIO",
    "FOREGROUND_SERVICE",            // Phase 2 — needed for the persistent notification
    "FOREGROUND_SERVICE_MICROPHONE"
  ]
}
```

### Component layout

```
apps/frontend/
  components/audio/
    RecordingBar.js              # the persistent bottom bar
    RecordingStateIndicator.js   # ●REC + animated waveform
    PermissionGate.js            # one-shot mic permission UX
  screens/audio/
    VoiceEnrollmentScreen.js     # 2-step phrase recording
    AudioHistoryScreen.js        # session list
    AudioSessionDetailScreen.js  # transcript + scrub
  contexts/
    AudioRecordingContext.js     # global recording state — outlives screen mounts
  services/
    audioRecorder.js             # wraps expo-audio Recording
    audioUploader.js             # background-upload queue with retry
  hooks/
    useAudioSession.js
    useChunkRotation.js          # timer that rolls files every N minutes
```

### Why a Context (not Zustand)

The recording state must survive route transitions and tab switches. The `AudioRecordingContext` lives at the same level as `AuthContext` (root provider in `App.js`), exposing:

```js
{
  status: "idle" | "enrolling" | "ready" | "recording" | "paused",
  session: { id, startedAt, chunksUploaded, chunksPending } | null,
  durationSeconds,
  start(), pause(), resume(), stop(),
  enrollment: { status, startPhraseText, stopPhraseText },
  enroll({ startBlob, stopBlob }), resetEnrollment()
}
```

Audio happens to fit Zustand fine, but tying it to Context makes it explicit that this is persistent app-wide state, not server-cached state (which is what TanStack Query is for, per CLAUDE.md).

### Bottom bar visibility

The `RecordingBar` mounts in the root layout *above* `MainTabs` so it's visible on every screen. It only renders when `status !== "idle"` OR the user has audio enabled in settings. When idle, it collapses to a thin tappable strip showing "Activar entrenamiento por audio".

```js
// apps/frontend/App.js (relevant excerpt)
<NavigationContainer>
  <View style={{ flex: 1 }}>
    <RootNavigator />
    <RecordingBar />   // floats above tab bar
  </View>
</NavigationContainer>
```

### Chunking strategy

Two viable approaches; we'll go with **(b)** for v1.

**(a) Continuous recording with offline split.** Record one long file, split client-side via ffmpeg-kit. *Rejected*: react-native-ffmpeg is heavy and an iOS background-mode crash risk. Splitting also means we can't upload chunks until the session ends.

**(b) Stop/start rotation.** Every `CHUNK_MINUTES` (default 5):
1. `recording.stopAndUnloadAsync()` → file ready
2. `recording = new Audio.Recording(); await recording.prepareToRecordAsync(opts); await recording.startAsync()`
3. Hand off the closed file URI to the upload queue
4. Continue from step 1

Brief gap between stop and start (~50–150ms) is acceptable. We log it in `chunk.metadata` so future analysis can ignore the boundary if needed.

### Upload queue

`audioUploader.js` keeps a FIFO of pending chunks in AsyncStorage so it survives app kills:

```js
{
  pending: [
    { localUri, sessionId, sequenceNumber, durationSeconds, attempts: 0 },
    ...
  ]
}
```

On every `enqueue()`, `AppState` change to active, or `NetInfo` reconnect, the queue tries to drain. Each chunk POST is multipart; on success the local file is deleted, on failure the entry's `attempts` is incremented (max 5, then mark `failed` and surface in UI).

This is the same shape as the photo-upload queue in many social apps — battle-tested pattern, no clever tricks.

---

## Backend (Rails)

### Routes

`resources` go alongside the `member` block, not inside it. The right form:

```ruby
# config/routes.rb additions inside namespace :api → namespace :v1
scope "audio" do
  resources :sessions, only: %i[index show create destroy], controller: "audio_sessions" do
    post :finish, on: :member
    post :cancel, on: :member
    resources :chunks, only: %i[create], controller: "audio_chunks"
  end

  post   "voice_enrollment", to: "voice_enrollments#create"
  get    "voice_enrollment", to: "voice_enrollments#show"
  delete "voice_enrollment", to: "voice_enrollments#destroy"

  post   "wipe", to: "audio_sessions#wipe_all"   # GDPR-style total wipe
end
```

### Models & jobs

```
app/models/audio_session.rb               # state-machine on status
app/models/audio_chunk.rb                 # encrypts :transcript, :segments
app/models/voice_enrollment.rb
app/models/audio_usage.rb                 # daily quota rollup
app/jobs/audio_chunk_process_job.rb       # transcribe + extract insights
app/jobs/audio_session_finalize_job.rb    # close out partials, set ready / ready_with_errors
app/jobs/audio_session_cleanup_job.rb     # hourly cron; abandons stale recording sessions
app/jobs/voice_print_enroll_job.rb        # Phase 2 only
app/services/audio_quota.rb               # Phase 1 — server-side daily cap check
app/services/ai_agents_client.rb          # +#transcribe_chunk, +#delete_insights_by_source
```

**Session status state-machine:**
```
recording  ─▶ finalizing  ─▶ processing  ─▶ ready
                                       └─▶ ready_with_errors   (some chunks failed)
                                       └─▶ failed              (all chunks failed)
recording  ─▶ cancelled    (user explicitly cancelled mid-recording — chunks discarded)
recording  ─▶ abandoned    (cleanup job finds session > 24h old still in `recording`)
ready/ready_with_errors  ─▶ deleted   (user wipe or retention)
```

`AudioChunkProcessJob` flow (Phase 1):
1. Load chunk; if `transcription_status != "pending"` and not retrying, return (idempotent).
2. **Quota check.** `AudioQuota.check!(user, additional_seconds: chunk.duration_seconds)` — raises `AudioQuota::Exceeded` if over the daily cap. Mark chunk `transcription_status: "skipped_quota"` and stop.
3. Mark chunk `running`; bump `transcription_attempts`.
4. POST chunk **bytes** (not URL) to FastAPI `/internal/audio/transcribe` with `{user_id, language: …}` — see "Audio transfer contract" above.
5. Persist returned `transcript` + `segments` (encrypted) to the chunk.
6. POST transcript to FastAPI `/internal/audio/extract_insights` with `source: "audio:<session_id>"`.
7. Bump `Avatar.insights_count` if any persisted (existing pattern).
8. `AudioUsage` upsert: `+= chunk.duration_seconds.to_i` for `(user_id, today_in_user_tz)`.
9. Mark chunk `done`. If all chunks of the session are `done` and the session is `processing`, fire `AudioSessionFinalizeJob`.

**`AudioSessionFinalizeJob`** decides between `ready` (all chunks done) and `ready_with_errors` (some failed after max retries) and writes a per-session summary into `metadata`.

**`AudioSessionCleanupJob`** runs hourly (existing `whenever` schedule):
- Sessions in `recording` and `started_at < 24.hours.ago` → mark `abandoned`, finalize whatever chunks made it through.
- Sessions in `processing` and `updated_at < 6.hours.ago` → re-enqueue `AudioChunkProcessJob` for stuck chunks once, then mark `ready_with_errors` if still stuck.

### Idempotent chunk uploads

Offline queue retries can hit the server twice with the same `(audio_session_id, sequence_number)`. The unique index makes the second insert fail; we handle it explicitly:

```ruby
class Api::V1::AudioChunksController < Api::V1::BaseController
  def create
    session = current_user.audio_sessions.find(params[:session_id])
    existing = session.audio_chunks.find_by(sequence_number: params[:sequence_number])

    if existing
      # Two cases:
      #  (a) Re-upload of a chunk we already accepted but client never saw the 202
      #      response. Return the existing chunk, idempotent.
      #  (b) Client wants to replace a chunk whose processing already started.
      #      Refuse — we don't want partial transcripts overwritten.
      if existing.transcription_status == "pending" && params[:audio].present?
        existing.audio = params[:audio]
        existing.save!
        return render_success(chunk: serialize(existing), status: :ok)
      end
      return render_success(chunk: serialize(existing), status: :ok)
    end

    chunk = session.audio_chunks.create!(create_params.merge(transcription_status: "pending"))
    AudioChunkProcessJob.perform_later(chunk_id: chunk.id)
    render_success({ chunk: serialize(chunk) }, status: :accepted)
  end
end
```

The client also sends an `Idempotency-Key` header (a uuid generated per chunk-attempt and persisted alongside the chunk in AsyncStorage) which we record in `metadata` so we can audit double-deliveries without behavior change.

### Storage

Reuse `Shrine` (already in the Gemfile). Audio attachments use the existing **`store_private`** storage so they're never publicly served.

```ruby
class AudioChunkUploader < Shrine
  plugin :determine_mime_type
  plugin :validation_helpers
  plugin :default_storage, store: :store_private, cache: :cache

  Attacher.validate do
    validate_max_size 25 * 1024 * 1024            # 25MB cap per chunk
    validate_mime_type %w[audio/mp4 audio/m4a audio/x-m4a audio/mpeg]
  end
end
```

Dev: FileSystem under `apps/backend/storage/private/`. Prod: S3 with `S3_AWS_*` envs (already wired in `config/initializers/shrine.rb`). The same uploader is used for `voice_enrollments.start_phrase_audio_data` and `stop_phrase_audio_data`.

**Encryption at rest:** v1 ships without app-level encryption. We rely on:
- S3 SSE-S3 (AES-256, server-managed key) — default-on for new buckets in prod.
- Postgres TLS in transit + standard disk encryption from the host.

ActiveRecord encryption on `transcript`/`segments` and per-user KMS envelope encryption are deferred until we have a customer / threat that justifies the operational cost.

### Endpoint shapes

```http
POST /api/v1/audio/sessions
→ 201 { session: { id, started_at, status: "recording", quota: { used_seconds, daily_cap_seconds } } }
   (or 429 + { error: "daily quota exceeded", quota: {...} })

POST /api/v1/audio/sessions/:id/chunks
Content-Type: multipart/form-data
Idempotency-Key: <client-generated uuid>
fields: sequence_number, started_at, duration_seconds, audio (file)
→ 202 { chunk: { id, sequence_number, transcription_status: "pending" } }
   (or 200 with the existing chunk if a duplicate sequence_number is re-uploaded)

POST /api/v1/audio/sessions/:id/finish
→ { session: { id, ended_at, status: "processing", chunk_count } }

POST /api/v1/audio/sessions/:id/cancel
→ { session: { id, status: "cancelled" } }
   (server-side: stops processing, deletes any pending chunks)

GET /api/v1/audio/sessions
→ { sessions: [{ id, started_at, ended_at, status, total_duration_seconds, chunk_count, transcript_preview }] }

GET /api/v1/audio/sessions/:id
→ { session: { ..., chunks: [{ id, sequence_number, started_at, duration_seconds,
                               transcript, segments, transcription_status }] } }

DELETE /api/v1/audio/sessions/:id
→ { deleted: true }
   (cascades: Shrine files, audio_chunks rows, FastAPI insights with source="audio:<id>")

POST /api/v1/audio/wipe
→ { deleted: { sessions: N, chunks: M, insights: K } }
   (cascades: every audio_session for the user + bulk-delete-by-source-prefix in FastAPI)

POST /api/v1/audio/voice_enrollment
multipart: start_phrase (file)?, stop_phrase (file)?, start_phrase_text?, stop_phrase_text?
→ 201 { enrollment: { status: "ready" | "skipped", start_phrase_text, stop_phrase_text } }

GET /api/v1/audio/voice_enrollment
→ { enrollment: { status, start_phrase_text, stop_phrase_text, has_audio: bool } }

DELETE /api/v1/audio/voice_enrollment
→ { deleted: true }
```

---

## AI agents (FastAPI)

### New module layout (Phase 1)

```
apps/ai-agents/app/
  audio/
    __init__.py
    transcription.py        # OpenAI transcription provider abstraction
  api/routes/
    audio.py                # /internal/audio/* endpoints (Phase 1: transcribe + extract)
```

Phase 2 adds:
```
  audio/
    voice_print.py          # Resemblyzer embedding extractor
    speaker_id.py           # cosine-similarity identification
    diarization.py          # pyannote.audio pipeline
  repositories/
    voice_print_repository.py
  models/
    voice_print.py          # SQLAlchemy model
```

### Transcription (v1)

OpenAI offers three transcription models with similar APIs:

| Model | Price | Notes |
|---|---|---|
| `gpt-4o-mini-transcribe` | ~$0.003/min | Lowest cost, good accuracy. **Default for MVP.** |
| `gpt-4o-transcribe` | ~$0.006/min | Best accuracy; same price as Whisper-1 with newer model. |
| `whisper-1` | $0.006/min | Original Whisper API. Fallback. Returns `verbose_json` with segments natively. |

Make both the provider and model **configurable via env** so we can swap providers (or self-host) later without code changes:

```
AUDIO_TRANSCRIPTION_PROVIDER=openai            # default; future values: "self_hosted_whisper"
AUDIO_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe   # confirmed default
```

Note: only `whisper-1` returns `verbose_json` segments natively today; the `gpt-4o-*` models return text. With `gpt-4o-mini-transcribe` as the v1 default, we accept text-only transcripts (no per-utterance timestamps in `audio_chunks.segments`); the `AudioSessionDetailScreen` shows transcripts as flat blocks of text per chunk. If we need per-utterance scrubbing later, flip the env to `whisper-1`.

```python
# apps/ai-agents/app/audio/transcription.py
async def transcribe_bytes(
    audio: bytes,
    *,
    filename: str = "chunk.m4a",
    mime: str = "audio/m4a",
    language: str | None = None,
    model: str | None = None,
) -> Transcription:
    """Receive raw audio bytes from Rails (multipart) and return text + segments."""
    chosen_model = model or settings.audio_transcription_model
    extra = {"response_format": "verbose_json"} if chosen_model == "whisper-1" else {}
    resp = await openai_client.audio.transcriptions.create(
        model=chosen_model,
        file=(filename, audio, mime),
        language=language,
        **extra,
    )
    if chosen_model == "whisper-1":
        return Transcription(
            text=resp.text,
            segments=[Segment(start=s.start, end=s.end, text=s.text) for s in resp.segments],
            language=resp.language,
        )
    return Transcription(text=resp.text, segments=[], language=language)
```

Cost reference (default model): a 5-min chunk is ~$0.015; an 8-hour day ~$1.50. Combined with the daily quota cap, dogfooding cost stays predictable.

**Insight extraction reuses existing chain.** The transcript goes into the same `insight_chain` that handles chat messages — it already classifies into `personal_history | preference | relationship | goal | emotion | health`. We tag every produced insight with `source="audio:<session_id>"`.

### Speaker diarization (Phase 2)

`pyannote.audio` pipeline `pyannote/speaker-diarization-3.1` via HuggingFace token. Needs the HF model cache mounted; runs on CPU but slow (~real-time on a 4-vCPU box). Run it in a dedicated Sidekiq queue with concurrency=1 to avoid memory blowups.

Output per chunk: `[{start, end, speaker_label}]` where `speaker_label` is anonymous (`SPEAKER_00`, `SPEAKER_01`). We embed each speaker's pooled audio and cosine-match against the enrolled voice print to label one as the user. Other speakers stay anonymous.

### Voice fingerprint enrollment (Phase 2)

`Resemblyzer` (lightweight, no GPU required) produces a 256-d voice embedding. The Phase 2 enrollment **does not rely on the 4-8s phrase clip alone** — instead it pools embeddings from:
1. The two enrollment phrase clips (if recorded)
2. The first ~5 minutes of accumulated session audio after diarization runs and identifies the dominant single speaker

This produces a much more reliable embedding than Phase 1 would have.

```python
# Phase 2
def enroll(clips: list[Path]) -> tuple[np.ndarray, float]:
    """Returns (normalized_embedding, quality_score 0..1)."""
    embeds = [encoder.embed_utterance(preprocess_wav(c)) for c in clips]
    pooled = np.mean(embeds, axis=0)
    pooled = pooled / np.linalg.norm(pooled)
    quality = _intra_clip_similarity(embeds)   # higher = more consistent voice across clips
    return pooled, quality
```

At identification time, each diarized speaker turn is embedded the same way and compared with cosine similarity; threshold ~0.65–0.75 claims "this is the user."

### Privacy: discard non-user audio (Phase 2 default)

When diarization is on:
- **Keep** only segments labeled as the user → text + features.
- **Discard** raw audio for non-user segments after diarization completes.
- **Tag** the kept transcript with speaker labels so insights can still distinguish "user said X" vs "user heard Y" — but the non-user *text* is anonymized (`speaker: "other"`).

### FastAPI endpoints

Phase 1:
```python
# apps/ai-agents/app/api/routes/audio.py
@router.post("/transcribe")
async def transcribe(audio: UploadFile, user_id: str = Form(...), language: str | None = Form(None)) -> TranscribeResponse:
    """Multipart audio in, transcript out. Audio bytes never persisted."""

@router.post("/extract_insights")
async def extract_insights_from_transcript(req: AudioInsightsRequest) -> InsightExtractionResponse:
    # delegates to existing insight_chain, tags source="audio:<session_id>"
```

Phase 2 adds `/voice_print` and `/identify` plus the diarization queue.

All under the existing `X-Internal-Token` middleware.

---

## Voice activation (Phase 2)

Two paths considered:

| Approach | Pros | Cons |
|---|---|---|
| **Picovoice Porcupine** custom keyword | tiny model, on-device, fast, already supports Spanish | requires per-keyword model training in Picovoice console (~5 min); commercial license for prod |
| **Apple SFSpeechRecognizer** + DTW match against enrolled clip | uses what we already have (the recorded phrase) | Apple's continuous-recognition API has minute-level rate limits per device; not battery-friendly for always-listening |

Recommendation: **defer to Phase 2** and start with manual button. When we tackle it, Porcupine is the right tool for always-listening, and we use the user's recorded phrase only as an *audible confirmation cue*, not as the actual wake-word matcher (Porcupine doesn't work that way). The trade-off is the user can't pick arbitrary phrases — they pick from a small library of pretrained options, OR we train a custom keyword on the server when the user changes it.

In v1, the recorded phrase is purely:
1. The voice fingerprint sample.
2. The text label shown in UI ("Tu frase de inicio: «Iniciar entrenamiento por audio»").

The actual session start is a button tap.

---

## Privacy, consent, and compliance

This is the riskiest feature in the product so far. Treat it accordingly.

**Phase 1 reality check.** Without diarization, every chunk transcript captures *every* voice the mic picks up — the user, family members, coworkers, baristas. The avatar will see all of it as if the user said it (or, more accurately, as if the user heard it). This is a real privacy and accuracy concern and the UX must reflect that, not paper over it.

- **Explicit per-session consent.** Big "●REC" indicator + "Estás grabando audio" copy in the bar. Never silent recording.
- **Bystander consent disclosure (Phase 1, stricter copy).** First-run modal:
  > *"Las grabaciones pueden capturar voces de otras personas presentes. Las leyes de consentimiento varían por país y, en muchos casos, por estado o provincia — verifica las tuyas antes de activar esta función. Te recomendamos avisar a quienes estén contigo. **No la uses en reuniones privadas, llamadas médicas, o cualquier contexto donde no tengas el consentimiento explícito de los presentes.**"*
- **Avoid country-specific legal claims.** The Phase 1 copy stays generic ("verifica tu jurisdicción"). We don't ship statements like "PE is one-party consent" because (a) the rules differ for one-party / two-party / business-relationship contexts, (b) we'd be giving legal advice, and (c) US users see this same product and the rules differ across 50+ states. If we want jurisdiction-aware copy, we punt that to a Phase 2 effort with actual legal review.
- **No diarization yet ⇒ no "the avatar only hears you."** Don't put marketing copy that implies user-only listening until Phase 2 ships diarization + the discard-non-user-audio policy. v1 transcripts capture everyone.
- **Lock screen visibility.** When recording is active and the screen is locked, iOS's red recording indicator and Android's notification both surface. This is a feature, not something to hide.
- **Retention.** **No automatic purge in v1** — sessions persist indefinitely until the user explicitly deletes them (per-session "Eliminar" or global "Eliminar todo el audio"). The retention picker UI is deferred until we have data on how much storage real users accumulate. The wipe and delete actions are still required v1 surfaces.
- **Per-session and global wipe.** "Eliminar todo el audio" deletes:
  - All `audio_sessions` + `audio_chunks` rows + their Shrine files
  - All insights with `source LIKE 'audio:%'` from FastAPI (via the new `delete_insights_by_source` route with `prefix=true`)
  - Phase 2: the user's `voice_prints` row in pgvector
- **Encryption.** No app-level encryption in v1 — transcripts and audio sit at rest with whatever the storage layer provides (Postgres TLS in transit + S3 default-on encryption when running on S3). We can add ActiveRecord encryption on `transcript`/`segments` later without a schema change if the threat model changes.
- **Audit log.** Every session start/stop, cancellation, retention purge, and wipe writes an `audit_log` row that the user can review in their privacy panel.
- **Don't send raw audio to third parties beyond the transcription provider.** No analytics SDK should ship the audio buffer. We already don't have any third-party analytics in the app, but worth a code review gate.

---

## Phasing & milestones

### Phase 1 — MVP ("the avatar reads your day")
- [ ] Migrations: `audio_sessions`, `audio_chunks`, `voice_enrollments`, `audio_usages` (Rails)
- [ ] Models (plaintext `transcript`/`segments` — no encryption in v1)
- [ ] Controllers: sessions (CRUD + finish + cancel + wipe_all), chunks (idempotent create), voice_enrollments (CRUD)
- [ ] Shrine `AudioChunkUploader` using `store_private`
- [ ] Sidekiq jobs: `AudioChunkProcessJob`, `AudioSessionFinalizeJob`, `AudioSessionCleanupJob` (cron, 24h cutoff)
- [ ] `AudioQuota` service — 480 min/day default, server-enforced; 429 on session create when over cap
- [ ] FastAPI `audio.py` with `/transcribe` (multipart bytes, no URLs) + `/extract_insights` (tagged `audio:<sid>`)
- [ ] FastAPI `delete_insights_by_source` route + service method
- [ ] `AUDIO_TRANSCRIPTION_PROVIDER` (default `openai`) and `AUDIO_TRANSCRIPTION_MODEL` (default `gpt-4o-mini-transcribe`) envs
- [ ] `RecordingBar` (root-mounted, persists across screens), `AudioRecordingContext`, mic permission UX
- [ ] Stop/start chunk rotation every `CHUNK_MINUTES` + offline-safe upload queue with `Idempotency-Key`
- [ ] `VoiceEnrollmentScreen` (start + stop phrases **required**, no fingerprint computation in v1)
- [ ] `AudioHistoryScreen` + `AudioSessionDetailScreen`
- [ ] Privacy modal + per-session "Eliminar" + global "Eliminar todo el audio" + audit log (no retention picker UI)
- [ ] `ProfileScreen.js` source-bucket grouping by prefix; `audio` entry in `SOURCE_CONFIG`
- [ ] Tests: chunk rotation timing, idempotent retries, quota enforcement (allow → at-cap → over-cap transitions), wipe cascade end-to-end, stale-session cleanup

### Phase 2 — speaker awareness
- [ ] FastAPI `voice_prints` alembic migration + Resemblyzer integration
- [ ] Diarization pipeline (pyannote) on dedicated Sidekiq queue
- [ ] `/voice_print` (build embedding from phrase clips + N seconds of recent session audio)
- [ ] `/identify` endpoint + speaker-aware transcript storage in `audio_chunks.segments`
- [ ] Discard-non-user-audio policy + UI toggle
- [ ] Wake-word library integration (Porcupine eval) — actual hands-free triggering
- [ ] iOS `UIBackgroundModes: audio` + `setAudioModeAsync({ allowsBackgroundRecording: true })`
- [ ] Android foreground service for the persistent recording notification
- [ ] On-device VAD (silence skipping) to cut upload bytes ~50%

### Phase 3 — prosody / behavior
- [ ] Per-chunk pitch / pace / energy features (librosa or pyAudioAnalysis)
- [ ] Tone-evolution chain that nudges `behavior.tone_*` weights based on rolling averages
- [ ] Emotion classification (multilingual model, e.g. `cardiffnlp/twitter-roberta-base-emotion-multilingual`) on transcript segments
- [ ] Aggregate "audio-derived persona insights" surface in Personalidad

---

## Decisions resolved (2026-04-28)

All open questions have been answered by the product owner. Locked-in values:

| # | Decision | Resolution |
|---|---|---|
| 1 | Chunk length | **5 minutes** |
| 2 | Retention | **No automatic purge.** Sessions persist until user deletes them. Per-session and global wipe required; no retention picker UI in v1. |
| 3 | Transcription provider | **OpenAI API**, but selectable via env (`AUDIO_TRANSCRIPTION_PROVIDER`, `AUDIO_TRANSCRIPTION_MODEL`). Self-hosted is a future env value, no code change needed. |
| 4 | Phase 2 non-user audio policy | **(a) Discard raw audio, keep anonymized text** labeled `speaker: "other"`. |
| 5 | Phase 2 enrollment fallback | **(a) Block + retry.** If a user fails enrollment, the feature stays blocked until they re-record successfully. |
| 6 | Stale-session cleanup | **24h cutoff** for sessions stuck in `recording` → `abandoned`. |
| 7 | Daily quota cap | **480 transcribed minutes/day** (8h) — server-enforced via `audio_usages`. |
| 8 | Default transcription model | **`gpt-4o-mini-transcribe`** (~$0.003/min, text-only — no per-utterance timestamps in v1). |
| 9 | Phrase capture | **Required, not skippable.** Both the start and stop trigger phrases must be recorded before the feature unlocks, even though Phase 1 doesn't use them. |
| — | Encryption at rest | **None at app level in v1.** Rely on S3 SSE-S3 in prod and Postgres TLS / disk encryption from the host. ActiveRecord encryption can be added later without a schema change. |
| — | Audio format | AAC/m4a, mono, 16 kHz, ~96 kbps. |
| — | Per-chunk size cap | 25 MB (matches OpenAI API limit). |
| — | Recording state mgmt | `AudioRecordingContext` (Context, not Zustand). |
| — | Recording bar location | Floats above bottom tab bar, mounted at root of `RootNavigator`. |

Phase 1 is unblocked.

---

## Files this plan will touch

```
# Backend (Phase 1)
apps/backend/db/migrate/{20260429000001..4}_*.rb
apps/backend/app/models/{audio_session,audio_chunk,voice_enrollment,audio_usage}.rb
apps/backend/app/controllers/api/v1/{audio_sessions,audio_chunks,voice_enrollments}_controller.rb
apps/backend/app/jobs/{audio_chunk_process,audio_session_finalize,audio_session_cleanup}_job.rb
apps/backend/app/uploaders/audio_chunk_uploader.rb
apps/backend/app/services/audio_quota.rb
apps/backend/app/services/ai_agents_client.rb            # +#transcribe_chunk, +#delete_insights_by_source
apps/backend/config/routes.rb                            # +audio scope
apps/backend/config/schedule.rb                          # +AudioSessionCleanupJob hourly
apps/backend/spec/                                       # request + job specs incl. idempotency, quota, wipe

# AI agents (Phase 1)
apps/ai-agents/app/audio/{__init__,transcription}.py
apps/ai-agents/app/api/routes/audio.py
apps/ai-agents/app/api/routes/memory.py                  # +delete_insights_by_source
apps/ai-agents/app/services/memory_service.py            # +delete_insights_by_source method
apps/ai-agents/app/main.py                               # register audio router
apps/ai-agents/app/config/settings.py                    # +audio_transcription_model
apps/ai-agents/pyproject.toml                            # (no new deps in Phase 1; OpenAI client already there)
apps/ai-agents/tests/                                    # transcribe fixture (mock OpenAI)

# Frontend (Phase 1)
apps/frontend/components/audio/{RecordingBar,RecordingStateIndicator,PermissionGate}.js
apps/frontend/screens/audio/{VoiceEnrollmentScreen,AudioHistoryScreen,AudioSessionDetailScreen}.js
apps/frontend/contexts/AudioRecordingContext.js
apps/frontend/services/{audioRecorder,audioUploader}.js
apps/frontend/hooks/{useAudioSession,useChunkRotation}.js
apps/frontend/screens/profile/ProfileScreen.js           # source-bucket prefix grouping; "audio" SOURCE_CONFIG entry
apps/frontend/screens/settings/PrivacyScreen.js          # retention picker + wipe action
apps/frontend/App.js                                     # mount RecordingBar globally
apps/frontend/app.config.js                              # NSMicrophoneUsageDescription (background mode is Phase 2)
apps/frontend/package.json                               # +expo-audio (via `npx expo install`)
```

Phase 2 adds:
```
apps/ai-agents/alembic/versions/<ts>_voice_prints.py
apps/ai-agents/app/audio/{voice_print,speaker_id,diarization}.py
apps/ai-agents/app/repositories/voice_print_repository.py
apps/ai-agents/app/models/voice_print.py
apps/backend/app/jobs/voice_print_enroll_job.rb
```

---

## Risk register

| Risk | Mitigation |
|---|---|
| iOS terminates app mid-session (Phase 1: foreground only) | Phase 1 keeps screen-on UX; if backgrounded, recording stops cleanly with the last chunk uploaded. Persist chunk + queue state to AsyncStorage every chunk-close so resumption is safe even after a hard kill. Background recording is Phase 2 with the entitlement. |
| Transcription API outage stalls processing | Sidekiq exponential-backoff retry. Chunks stay `pending` until they succeed; UI shows "Procesando" not "Failed." After max attempts, chunk goes to `failed` and the session resolves to `ready_with_errors`. |
| Phase 1 transcripts include third-party voices | Strict consent UX, always-on REC indicator, lock-screen visibility, retention default 30d, easy wipe. The honest framing in onboarding ("Las grabaciones pueden capturar voces de otras personas") is the primary mitigation. |
| Storage explosion from 8h-a-day power users | S3 lifecycle rule: transition raw audio to Glacier after 30 days; delete after retention window. Transcripts stay queryable in Postgres regardless. |
| Cost explosion from runaway recording | Server-side `audio_usages` daily cap (**default 480 min/day** — i.e. 8h) enforced in `AudioChunkProcessJob`; chunks past the cap are stored but not transcribed (`transcription_status: "skipped_quota"`). Cap is the source of truth, not the client. |
| Idempotency-key collisions / duplicate uploads | Unique `(session_id, sequence_number)` index + idempotent re-upload semantics in `AudioChunksController#create` (return existing if already accepted; replace only if still `pending`). |
| Stuck `recording` / `processing` sessions | Hourly `AudioSessionCleanupJob`: > 24h `recording` → `abandoned`, > 6h `processing` → re-try then `ready_with_errors`. |
| Diarization model RAM (Phase 2) | Dedicated Sidekiq queue with concurrency=1. Provision an extra ai-agents worker if it becomes an issue. |
| User's wake phrase is "ok google" / "siri" / "alexa" | Validate in enrollment: reject phrases matching known assistant triggers. |
| Voice fingerprint accuracy in Phase 2 | Embed from pooled samples (phrase clips + early session audio), require `embedding_quality > 0.6` before activating diarization-based filtering. Until then, keep all-speaker transcripts as-is. |
