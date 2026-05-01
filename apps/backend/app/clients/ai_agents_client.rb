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

  # Streams /internal/chat/stream. FastAPI emits SSE-framed text chunks
  # ("data: <json>\n\n"). We yield the *plain text* content of each chunk so
  # the caller (ChatGenerationJob) can broadcast it directly over ActionCable.
  #
  # Returns a hash with any out-of-band data captured during the stream:
  #   { telemetry: { ai_received_at:, ai_first_token_at:, ai_last_token_at:, ai_to_api_done_at: } | nil }
  # FastAPI emits a final telemetry frame (kind=:telemetry) right before
  # [DONE] so the caller can stitch it together with its own timestamps.
  def stream_chat(payload, &block)
    buffer = +""
    telemetry = nil
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
    { telemetry: telemetry }
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

  def delete_insight(user_id:, insight_id:)
    self.class.delete("/internal/memory/#{user_id}/insights/#{insight_id}").code == 204
  end

  def delete_all_insights(user_id)
    self.class.delete("/internal/memory/#{user_id}").code == 204
  end

  def teach(user_id:, message:, context: "")
    post_json(
      "/internal/insights/extract",
      { user_id: user_id, message: message, context: context }
    )
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

    response = self.class.post(
      "/internal/audio/transcribe",
      multipart: true,
      body: body,
      timeout: 120
    )
    response.parsed_response
  end

  def extract_audio_insights(user_id:, transcript:, source:, context: "")
    post_json(
      "/internal/audio/extract_insights",
      { user_id: user_id.to_s, transcript: transcript, source: source, context: context },
      timeout: 60
    )
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
      return "" if parsed.key?("error")  # caller should not append errors
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
