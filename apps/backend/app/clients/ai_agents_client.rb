# frozen_string_literal: true

# HTTP client for the FastAPI ai-agents service.
#
# Every method talks to an endpoint documented in /docs/endpoints.md. The
# internal-token header guards the FastAPI boundary; without it, ai-agents
# returns 401.
#
# Streaming (stream_chat) yields chunks as they arrive so ChatGenerationJob
# can broadcast each one over ActionCable.
class AiAgentsClient
  include HTTParty

  base_uri ENV.fetch("AI_AGENTS_BASE_URL", "http://localhost:8001")
  headers "X-Internal-Token" => ENV.fetch("AI_AGENTS_INTERNAL_TOKEN", "")
  default_timeout 30

  # ── Chat ──────────────────────────────────────────────────────────────

  # @param payload [Hash] ChatRequest shape (see apps/ai-agents/app/models/schemas.py)
  def generate_chat(payload)
    post_json("/internal/chat/generate", payload, timeout: 90)
  end

  # Wave B.4 (2026-05-06) — durable post-turn learning. Called by
  # PostTurnLearningJob after the assistant Message has been persisted.
  # Returns a Hash with insights_new / events_new / persona_notes /
  # summary_written / slang_calibrated / took_ms keys (LearnResponse).
  def run_post_turn_learning(payload)
    post_json("/internal/chat/learn", payload, timeout: 90)
  end

  # Streams /internal/chat/stream. FastAPI emits SSE-framed text chunks
  # ("data: <json>\n\n"). We yield the *plain text* content of each chunk so
  # the caller (ChatGenerationJob) can broadcast it directly over ActionCable.
  #
  # Returns a hash with any out-of-band data captured during the stream:
  #   { telemetry: {...} | nil, error: "<reason>" | nil }
  # FastAPI emits a final telemetry frame (kind=:telemetry) right before
  # [DONE] so the caller can stitch it together with its own timestamps.
  # If generation fails mid-stream FastAPI emits an error frame instead of
  # tokens; `error` carries that reason (e.g. "Service temporarily
  # unavailable (rate limit)") so the caller broadcasts it verbatim.
  def stream_chat(payload, &block)
    buffer = +""
    telemetry = nil
    upstream_error = nil
    flush = lambda do |frame|
      result = parse_sse_frame(frame)
      case result
      when ::String
        yield result if !result.empty?
      when ::Hash
        case result[:kind]
        when :token
          yield result[:text] if result[:text] && !result[:text].empty?
        when :telemetry
          telemetry = result[:data]
        when :error
          upstream_error = result[:message].presence
        end
      end
    end
    self.class.post(
      "/internal/chat/stream",
      body: payload.to_json,
      headers: { "Content-Type" => "application/json" },
      stream_body: true,
      timeout: 120
    ) do |raw_chunk|
      buffer << raw_chunk
      while (idx = buffer.index("\n\n"))
        frame = buffer.slice!(0, idx + 2)
        flush.call(frame)
      end
    end
    # flush trailing line if server did not terminate with \n\n
    flush.call(buffer) unless buffer.empty?
    { telemetry: telemetry, error: upstream_error }
  end

  def generate_proactive(payload)
    post_json("/internal/chat/proactive-generate", payload, timeout: 60)
  end

  # ── Insights / memory ─────────────────────────────────────────────────

  # FastAPI exposes one endpoint per platform shape, not a single generic one.
  #   instagram → /internal/insights/extract-instagram
  #   facebook|twitter|spotify → /internal/insights/extract-social
  # Rails normalises this so callers just pass `platform:`.
  def extract_insights(platform:, user_id:, payload:)
    path = case platform
           when "instagram" then "/internal/insights/extract-instagram"
           else                  "/internal/insights/extract-social"
           end
    body = { user_id: user_id, platform: platform }
    body[:data] = payload if payload.is_a?(Hash) && payload.any?
    post_json(path, body, timeout: 60)
  end

  def list_insights(user_id)
    # FastAPI returns {user_id, total_insights, knowledge_level, insights[]}.
    self.class.get("/internal/memory/#{user_id}").parsed_response
  end

  def insight_categories(user_id)
    # → {user_id, counts: {category => n}, total}
    self.class.get("/internal/memory/#{user_id}/categories").parsed_response
  end

  def insight_sources(user_id)
    # → {user_id, sources: {source => n}, total}
    self.class.get("/internal/memory/#{user_id}/sources").parsed_response
  end

  def update_insight(user_id:, insight_id:, content:)
    self.class.patch(
      "/internal/memory/#{user_id}/insights/#{insight_id}",
      body: { content: content }.to_json,
      headers: { "Content-Type" => "application/json" }
    ).parsed_response
  end

  def delete_insight(user_id:, insight_id:)
    self.class.delete("/internal/memory/#{user_id}/insights/#{insight_id}").code == 204
  end

  def delete_all_insights(user_id)
    self.class.delete("/internal/memory/#{user_id}").code == 204
  end

  # Direct manual-fact storage (DEV-93). Hits FastAPI's teach route, which
  # embeds the text and stores an ACTIVE insight (source: manual,
  # confidence 1.0) so it is immediately retrievable by chat-time semantic
  # search — unlike /internal/insights/extract, whose LLM chain can
  # legitimately store nothing (confidence floors, dedupe, quota errors).
  #
  # Returns the stored Insight hash ({id, user_id, category, content,
  # confidence, source, created_at}) or nil on failure.
  def teach(user_id:, message:, category: nil)
    body = { content: message }
    body[:category] = category if category.present?
    response = self.class.post(
      "/internal/memory/#{user_id}/teach",
      body: body.to_json,
      headers: { "Content-Type" => "application/json" },
      timeout: 30
    )
    if response.code >= 400
      Rails.logger.warn(
        "[ai-client] teach non-2xx user=#{user_id} http=#{response.code} " \
        "body=#{response.body.to_s.first(500)}"
      )
      return nil
    end
    response.parsed_response
  rescue StandardError => e
    Rails.logger.warn("[ai-client] teach failed user=#{user_id}: #{e.class}: #{e.message}")
    nil
  end

  def search_memory(user_id:, query:)
    post_json("/internal/memory/search", { user_id: user_id, query: query })
  end

  # ── Audio ─────────────────────────────────────────────────────────────

  # Stream chunk bytes to FastAPI for transcription. We send a multipart
  # POST so dev (FileSystem Shrine) and prod (S3 Shrine) work identically.
  # Presigned-URL transfer is deferred until S3 chunk volumes justify it.
  def transcribe_chunk(user_id:, audio_io:, language: nil)
    body = { "user_id" => user_id.to_s, "audio" => audio_io }
    body["language"] = language if language.present?

    started = Process.clock_gettime(Process::CLOCK_MONOTONIC) * 1000.0
    response = self.class.post(
      "/internal/audio/transcribe",
      multipart: true,
      body: body,
      timeout: 120
    )
    took_ms = Process.clock_gettime(Process::CLOCK_MONOTONIC) * 1000.0 - started

    parsed = response.parsed_response
    Rails.logger.info(
      "[ai-client] transcribe user=#{user_id} took=#{took_ms.to_i}ms http=#{response.code} " \
      "body_keys=#{parsed.is_a?(Hash) ? parsed.keys.inspect : parsed.class.name} " \
      "lang=#{language.inspect}"
    )
    if response.code >= 400
      Rails.logger.warn("[ai-client] transcribe non-2xx body=#{parsed.inspect.first(500)}")
    end
    parsed
  end

  def extract_audio_insights(user_id:, transcript:, source:, context: "", timezone: nil, recorded_at: nil, audio_chunk_id: nil, audio_session_id: nil)
    started = Process.clock_gettime(Process::CLOCK_MONOTONIC) * 1000.0
    body = {
      user_id:           user_id.to_s,
      transcript:        transcript,
      source:            source,
      context:           context,
      timezone:          timezone,
      recorded_at:       recorded_at,
      audio_chunk_id:    audio_chunk_id,
      audio_session_id:  audio_session_id
    }.compact
    response = self.class.post(
      "/internal/audio/extract_insights",
      body: body.to_json,
      headers: { "Content-Type" => "application/json" },
      timeout: 60
    )
    took_ms = Process.clock_gettime(Process::CLOCK_MONOTONIC) * 1000.0 - started

    parsed = response.parsed_response
    stored = parsed.is_a?(Hash) ? parsed["stored"] : nil
    events = parsed.is_a?(Hash) ? parsed["events"] : nil
    Rails.logger.info(
      "[ai-client] extract_audio_insights user=#{user_id} source=#{source} " \
      "took=#{took_ms.to_i}ms http=#{response.code} stored=#{stored.inspect} " \
      "events=#{events.inspect} transcript_chars=#{transcript.length}"
    )
    if response.code >= 400
      Rails.logger.warn("[ai-client] extract_audio_insights non-2xx body=#{parsed.inspect.first(500)}")
    end
    parsed
  end

  # Synthesize ``text`` to spoken audio. Returns the raw bytes plus the
  # provider-reported metadata so the caller can attach it via Shrine.
  #
  # Returns: { bytes: String (binary), mime: "audio/mpeg", voice:, model:, provider: }
  #          or nil on non-2xx (caller decides whether to retry / persist text-only).
  def synthesize_speech(text:, voice: nil, audio_format: "mp3")
    body = { text: text, audio_format: audio_format }
    body[:voice] = voice if voice.present?

    started = Process.clock_gettime(Process::CLOCK_MONOTONIC) * 1000.0
    response = self.class.post(
      "/internal/audio/synthesize",
      body: body.to_json,
      headers: { "Content-Type" => "application/json" },
      timeout: 90
    )
    took_ms = Process.clock_gettime(Process::CLOCK_MONOTONIC) * 1000.0 - started

    if response.code >= 400
      Rails.logger.warn(
        "[ai-client] synthesize non-2xx http=#{response.code} took=#{took_ms.to_i}ms " \
        "body=#{response.body.to_s.first(500)}"
      )
      return nil
    end

    bytes = response.body.to_s.b # ensure ASCII-8BIT (binary)
    Rails.logger.info(
      "[ai-client] synthesize chars=#{text.length} bytes=#{bytes.bytesize} " \
      "took=#{took_ms.to_i}ms voice=#{response.headers["x-audio-voice"].inspect}"
    )
    {
      bytes:    bytes,
      mime:     response.headers["content-type"] || "audio/mpeg",
      voice:    response.headers["x-audio-voice"],
      model:    response.headers["x-audio-model"],
      provider: response.headers["x-audio-provider"]
    }
  end

  # Bulk delete insights matching a source string. With prefix=true,
  # source matches by leading substring (e.g. source="audio" deletes all
  # rows whose source begins with "audio:").
  def delete_insights_by_source(user_id:, source:, prefix: false)
    response = self.class.delete(
      "/internal/memory/#{user_id}/by-source",
      query: { source: source, prefix: prefix.to_s }
    )
    response.parsed_response
  end

  # ── Psychological profiling (DEV-98) ──────────────────────────────────

  # Runs the external profiling providers (Humantic AI / Sentino) over the
  # supplied corpus and/or LinkedIn URL. Env-gated on the FastAPI side: a
  # provider with no API key configured is skipped and reported in the
  # response's `errors` hash, so this is safe to call with no keys set.
  #
  # Returns { "user_id", "profiles" => {provider => traits|nil},
  #           "errors" => {provider => reason} } or nil on failure.
  def run_psych_profiling(user_id:, text_corpus: nil, linkedin_url: nil)
    body = { user_id: user_id.to_s }
    body[:text_corpus]  = text_corpus  if text_corpus.present?
    body[:linkedin_url] = linkedin_url if linkedin_url.present?
    post_json("/internal/profile/psych", body, timeout: 120)
  rescue StandardError => e
    Rails.logger.warn("[ai-client] run_psych_profiling failed user=#{user_id}: #{e.class}: #{e.message}")
    nil
  end

  # → { "user_id", "profiles" => {provider => {traits, source_summary, ...}} }
  def psych_profiles(user_id)
    self.class.get("/internal/profile/psych/#{user_id}").parsed_response
  end

  # ── Health ────────────────────────────────────────────────────────────

  def health_ok?
    self.class.get("/health", timeout: 2).code == 200
  rescue StandardError
    false
  end

  private

  # FastAPI emits SSE frames of the form:
  #   data: {"token": "<text>"}\n\n         → token chunk
  #   data: {"telemetry": {...}}\n\n         → final hop-timestamps payload
  #   data: {"error": "..."}\n\n             → upstream error
  #   data: [DONE]\n\n                       → end-of-stream sentinel
  # Return value:
  #   String "" (empty/done/error frames — caller skips)
  #   String "..." (legacy plain-text frames — content)
  #   Hash { kind: :token,     text: "..." }
  #   Hash { kind: :telemetry, data: {...}  }
  def parse_sse_frame(frame)
    payload = frame
      .split("\n")
      .filter_map { |line| line.start_with?("data:") ? line.sub(/^data:\s?/, "") : nil }
      .join("")
    return "" if payload.empty? || payload == "[DONE]"

    if payload.start_with?("{")
      parsed = begin
        JSON.parse(payload)
      rescue JSON::ParserError
        return payload
      end
      return { kind: :telemetry, data: parsed["telemetry"] } if parsed.key?("telemetry")
      return { kind: :token,     text: parsed["token"].to_s } if parsed.key?("token")
      # Upstream (FastAPI) reported a generation failure mid-stream — surface
      # the reason so the caller can broadcast it instead of a blank "empty
      # response". Not appended to the assistant text.
      return { kind: :error, message: parsed["error"].to_s } if parsed.key?("error")
      return ""
    end

    payload
  end

  def post_json(path, payload, timeout: nil)
    opts = {
      body: payload.to_json,
      headers: { "Content-Type" => "application/json" }
    }
    opts[:timeout] = timeout if timeout
    self.class.post(path, opts).parsed_response
  end
end
