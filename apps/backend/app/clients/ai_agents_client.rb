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

  # Yields each streamed chunk (String) to the caller.
  def stream_chat(payload, &block)
    self.class.post(
      "/internal/chat/stream",
      body: payload.to_json,
      headers: { "Content-Type" => "application/json" },
      stream_body: true,
      timeout: 120
    ) do |chunk|
      block.call(chunk)
    end
  end

  def generate_proactive(payload)
    post_json("/internal/chat/proactive-generate", payload, timeout: 60)
  end

  # ── Insights / memory ─────────────────────────────────────────────────

  def extract_insights(platform:, user_id:, payload:)
    post_json(
      "/internal/insights/extract",
      { platform: platform, user_id: user_id, payload: payload }
    )
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

  def post_json(path, payload, timeout: nil)
    opts = {
      body: payload.to_json,
      headers: { "Content-Type" => "application/json" }
    }
    opts[:timeout] = timeout if timeout
    self.class.post(path, opts).parsed_response
  end
end
