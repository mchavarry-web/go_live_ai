# frozen_string_literal: true

require "test_helper"
require_relative "../../../support/audio_test_helpers"

# POST /api/v1/chat/conversations/:conversation_id/messages/voice
#
# Behavior contract only — error copy is asserted as "an error key exists",
# never as an exact string (the wording is owned by a separate workstream).
class Api::V1::MessagesControllerVoiceTest < ActionDispatch::IntegrationTest
  include ActiveJob::TestHelper
  include AudioTestHelpers

  setup do
    @user         = create_user!
    @conversation = @user.conversations.create!
    @path         = "/api/v1/chat/conversations/#{@conversation.id}/messages/voice"
  end

  def post_voice(fake, params: { audio: wav_upload }, headers: {})
    stub_ai_client(fake) do
      post @path, params: params, headers: auth_headers(@user).merge(headers)
    end
  end

  test "requires a JWT" do
    post @path, params: { audio: wav_upload }
    assert_response :unauthorized
  end

  test "valid audio → 202, user message with transcript + attached audio, voice job enqueued" do
    fake = FakeAiAgentsClient.new(transcription: { "text" => "hola desde el micrófono", "language" => "es" })

    assert_difference("@conversation.messages.count", 1) do
      post_voice(fake)
    end
    assert_response :accepted

    msg = @conversation.messages.sole
    assert_equal "user", msg.role
    assert_equal "hola desde el micrófono", msg.content
    assert msg.audio?, "source audio should be attached to the message"
    assert_equal true, msg.metadata["voice_input"]
    assert_equal "es", msg.metadata["language"]

    body = JSON.parse(response.body)
    assert_equal msg.id, body.dig("message", "id")
    assert_equal true, body.dig("message", "has_audio")

    assert_enqueued_jobs 1, only: ChatGenerationJob
    assert_enqueued_with(
      job:  ChatGenerationJob,
      args: ->(args) {
        kwargs = args.first
        kwargs[:voice_response] == true &&
          kwargs[:conversation_id] == @conversation.id &&
          kwargs[:user_message_id] == msg.id
      }
    )
  end

  test "transcription language param is forwarded to the AI client" do
    fake = FakeAiAgentsClient.new(transcription: { "text" => "ok" })
    post_voice(fake, params: { audio: wav_upload, language: "es" })
    assert_equal "es", fake.calls_for(:transcribe_chunk).first[:args][:language]
    assert_equal @user.id, fake.calls_for(:transcribe_chunk).first[:args][:user_id]
  end

  test "empty transcript → 422 with an error body, nothing persisted or enqueued" do
    fake = FakeAiAgentsClient.new(transcription: { "text" => "   " })

    assert_no_difference("Message.count") do
      assert_no_enqueued_jobs(only: ChatGenerationJob) do
        post_voice(fake)
      end
    end

    assert_response :unprocessable_entity
    assert JSON.parse(response.body)["error"].present?
  end

  test "unparseable transcription response (nil) → 422" do
    assert_no_difference("Message.count") do
      post_voice(FakeAiAgentsClient.new(transcription: nil))
    end
    assert_response :unprocessable_entity
    assert JSON.parse(response.body)["error"].present?
  end

  test "missing audio param → 422 without calling the AI client" do
    fake = FakeAiAgentsClient.new
    assert_no_difference("Message.count") do
      post_voice(fake, params: {})
    end
    assert_response :unprocessable_entity
    assert JSON.parse(response.body)["error"].present?
    refute fake.called?(:transcribe_chunk)
  end

  test "another user's conversation → 404" do
    other_conv = create_user!.conversations.create!
    fake = FakeAiAgentsClient.new
    stub_ai_client(fake) do
      post "/api/v1/chat/conversations/#{other_conv.id}/messages/voice",
           params: { audio: wav_upload }, headers: auth_headers(@user)
    end
    assert_response :not_found
    assert_equal 0, other_conv.messages.count
  end
end
