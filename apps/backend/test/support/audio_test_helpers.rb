# frozen_string_literal: true

# Records every call made to it and returns canned responses, so audio tests
# never open a network connection to FastAPI. Swap it in with:
#
#   stub_ai_client(fake) { ...request / perform_now... }
#
# (minitest 6 no longer ships minitest/mock, so AudioTestHelpers#stub_ai_client
# provides the class-method stub.)
#
# Configure per-test via the keyword args; `transcription:` may be a Hash,
# nil (simulates an unparseable/empty upstream body), or an exception class /
# instance (raised when transcribe_chunk is invoked).
class FakeAiAgentsClient
  attr_reader :calls

  def initialize(transcription: { "text" => "hola" }, insights: { "stored" => 1, "events" => 0 })
    @transcription = transcription
    @insights      = insights
    @calls         = []
  end

  def called?(name)
    @calls.any? { |c| c[:name] == name }
  end

  def calls_for(name)
    @calls.select { |c| c[:name] == name }
  end

  def transcribe_chunk(**kwargs)
    # Don't record the IO object itself — keep the call log inspectable.
    @calls << { name: :transcribe_chunk, args: kwargs.except(:audio_io) }
    raise @transcription if @transcription.is_a?(Exception) || (@transcription.is_a?(Class) && @transcription <= Exception)
    @transcription
  end

  def extract_audio_insights(**kwargs)
    @calls << { name: :extract_audio_insights, args: kwargs }
    @insights
  end

  def delete_insights_by_source(**kwargs)
    @calls << { name: :delete_insights_by_source, args: kwargs }
    { "deleted" => 0 }
  end

  def synthesize_speech(**kwargs)
    @calls << { name: :synthesize_speech, args: kwargs.except(:text) }
    nil
  end
end

module AudioTestHelpers
  # Route every `AiAgentsClient.new` to `fake` for the duration of the block.
  # AiAgentsClient defines no custom `new`, so removing the singleton method
  # afterwards restores the inherited Class#new.
  def stub_ai_client(fake)
    AiAgentsClient.define_singleton_method(:new) { |*, **| fake }
    yield
  ensure
    AiAgentsClient.singleton_class.send(:remove_method, :new)
  end

  # Full User.create! (unlike fixtures) so the ensure_avatar callback runs —
  # audio jobs and message hooks expect user.avatar to exist.
  def create_user!(timezone: "UTC", **attrs)
    User.create!(
      email:    "user-#{SecureRandom.hex(6)}@example.com",
      password: "password123",
      timezone: timezone,
      **attrs
    )
  end

  def auth_headers(user)
    { "Authorization" => "Bearer #{Auth::JwtIssuer.access_token(user)}" }
  end

  def enroll_voice!(user)
    user.create_voice_enrollment!(status: "ready")
  end

  def create_recording_session!(user, **attrs)
    user.audio_sessions.create!(started_at: Time.current, status: "recording", **attrs)
  end

  def create_chunk!(session, sequence_number:, status: "pending", duration: 120.0, **attrs)
    session.audio_chunks.create!(
      sequence_number:      sequence_number,
      started_at:           Time.current,
      duration_seconds:     duration,
      transcription_status: status,
      **attrs
    )
  end

  def attach_wav!(chunk)
    File.open(wav_fixture_path, "rb") { |f| chunk.audio = f }
    chunk.save!
    chunk
  end

  def wav_fixture_path
    Rails.root.join("test/fixtures/files/tiny.wav")
  end

  # For multipart controller posts.
  def wav_upload
    Rack::Test::UploadedFile.new(wav_fixture_path, "audio/wav")
  end

  # AudioQuota reads the cap from ENV on every call; pin it for a block.
  def with_audio_quota_cap(seconds)
    previous = ENV[AudioQuota::ENV_KEY]
    ENV[AudioQuota::ENV_KEY] = seconds.to_s
    yield
  ensure
    if previous.nil?
      ENV.delete(AudioQuota::ENV_KEY)
    else
      ENV[AudioQuota::ENV_KEY] = previous
    end
  end
end
