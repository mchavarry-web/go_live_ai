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
  def stream_chat(payload, &block)
    buffer = +""
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
        content = parse_sse_frame(frame)
        yield content if content && !content.empty?
      end
    end
    # flush trailing line if server did not terminate with \n\n
    unless buffer.empty?
      content = parse_sse_frame(buffer)
      yield content if content && !content.empty?
    end
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
    self.class.get("/internal/insights/#{user_id}").parsed_response
  end

  def search_memory(user_id:, query:)
    post_json("/internal/memory/search", { user_id: user_id, query: query })
  end

  # ── Health ────────────────────────────────────────────────────────────

  def health_ok?
    self.class.get("/health", timeout: 2).code == 200
  rescue StandardError
    false
  end

  private

  # FastAPI emits SSE frames of the form:
  #   data: <text-or-json>\n
  #   \n
  # The content lines may be:
  #   - plain text tokens (from LangChain streaming)
  #   - a JSON object like {"type": "done"} or {"type": "error", "message": "..."}
  # We return the raw data portion (caller decides how to treat it).
  def parse_sse_frame(frame)
    frame
      .split("\n")
      .filter_map { |line| line.start_with?("data:") ? line.sub(/^data:\s?/, "") : nil }
      .join("")
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
