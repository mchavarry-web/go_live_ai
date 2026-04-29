# This file is auto-generated from the current state of the database. Instead
# of editing this file, please use the migrations feature of Active Record to
# incrementally modify your database, and then regenerate this schema definition.
#
# This file is the source Rails uses to define your schema when running `bin/rails
# db:schema:load`. When creating a new database, `bin/rails db:schema:load` tends to
# be faster and is potentially less error prone than running all of your
# migrations from scratch. Old migrations may fail to apply correctly if those
# migrations use external dependencies or application code.
#
# It's strongly recommended that you check this file into your version control system.

ActiveRecord::Schema[8.1].define(version: 2026_04_29_000001) do
  # These are extensions that must be enabled in order to support this database
  enable_extension "pg_catalog.plpgsql"

  create_table "audio_chunks", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.text "audio_data"
    t.uuid "audio_session_id", null: false
    t.datetime "created_at", null: false
    t.float "duration_seconds"
    t.string "idempotency_key"
    t.string "language"
    t.jsonb "metadata", default: {}, null: false
    t.jsonb "segments", default: [], null: false
    t.integer "sequence_number", null: false
    t.datetime "started_at", null: false
    t.text "transcript"
    t.integer "transcription_attempts", default: 0, null: false
    t.string "transcription_status", default: "pending", null: false
    t.datetime "updated_at", null: false
    t.index ["audio_session_id", "sequence_number"], name: "index_audio_chunks_on_audio_session_id_and_sequence_number", unique: true
    t.index ["audio_session_id"], name: "index_audio_chunks_on_audio_session_id"
    t.index ["transcription_status"], name: "index_audio_chunks_on_transcription_status"
  end

  create_table "audio_sessions", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.datetime "created_at", null: false
    t.datetime "ended_at"
    t.jsonb "metadata", default: {}, null: false
    t.datetime "started_at", null: false
    t.string "status", default: "recording", null: false
    t.integer "total_duration_seconds", default: 0, null: false
    t.integer "transcribed_seconds", default: 0, null: false
    t.datetime "updated_at", null: false
    t.bigint "user_id", null: false
    t.index ["status"], name: "index_audio_sessions_on_status"
    t.index ["user_id", "started_at"], name: "index_audio_sessions_on_user_id_and_started_at"
    t.index ["user_id"], name: "index_audio_sessions_on_user_id"
  end

  create_table "audio_usages", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.datetime "created_at", null: false
    t.integer "transcribed_seconds", default: 0, null: false
    t.datetime "updated_at", null: false
    t.integer "uploaded_chunks", default: 0, null: false
    t.date "usage_date", null: false
    t.bigint "user_id", null: false
    t.index ["user_id", "usage_date"], name: "index_audio_usages_on_user_id_and_usage_date", unique: true
    t.index ["user_id"], name: "index_audio_usages_on_user_id"
  end

  create_table "avatars", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.string "active_mode", default: "friends", null: false
    t.jsonb "appearance", default: {}, null: false
    t.jsonb "behavior", default: {}, null: false
    t.integer "conversations_count", default: 0, null: false
    t.datetime "created_at", null: false
    t.integer "days_active", default: 0, null: false
    t.integer "insights_count", default: 0, null: false
    t.datetime "last_interaction_at"
    t.integer "messages_count", default: 0, null: false
    t.jsonb "mode_message_counts", default: {}, null: false
    t.string "name"
    t.integer "social_connections_count", default: 0, null: false
    t.datetime "updated_at", null: false
    t.bigint "user_id", null: false
    t.index ["active_mode"], name: "index_avatars_on_active_mode"
    t.index ["user_id"], name: "index_avatars_on_user_id", unique: true
  end

  create_table "conversations", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.datetime "created_at", null: false
    t.datetime "last_active_at", null: false
    t.string "title"
    t.datetime "updated_at", null: false
    t.bigint "user_id", null: false
    t.index ["user_id", "last_active_at"], name: "index_conversations_on_user_id_and_last_active_at"
    t.index ["user_id"], name: "index_conversations_on_user_id"
  end

  create_table "device_tokens", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.boolean "active", default: true, null: false
    t.datetime "created_at", null: false
    t.jsonb "metadata", default: {}, null: false
    t.string "platform", null: false
    t.string "token", null: false
    t.datetime "updated_at", null: false
    t.bigint "user_id", null: false
    t.index ["token"], name: "index_device_tokens_on_token", unique: true
    t.index ["user_id"], name: "index_device_tokens_on_user_id"
  end

  create_table "feature_settings", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.datetime "created_at", null: false
    t.boolean "enabled", default: true, null: false
    t.string "key", null: false
    t.jsonb "metadata", default: {}, null: false
    t.datetime "updated_at", null: false
    t.index ["key"], name: "index_feature_settings_on_key", unique: true
  end

  create_table "jwt_denylist", force: :cascade do |t|
    t.datetime "created_at", null: false
    t.datetime "exp", null: false
    t.string "jti", null: false
    t.datetime "updated_at", null: false
    t.index ["exp"], name: "index_jwt_denylist_on_exp"
    t.index ["jti"], name: "index_jwt_denylist_on_jti", unique: true
  end

  create_table "messages", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.text "content", default: "", null: false
    t.uuid "conversation_id", null: false
    t.datetime "created_at", null: false
    t.jsonb "metadata", default: {}, null: false
    t.string "proactive_skill"
    t.string "role", null: false
    t.datetime "updated_at", null: false
    t.index ["conversation_id", "created_at"], name: "index_messages_on_conversation_id_and_created_at"
    t.index ["conversation_id"], name: "index_messages_on_conversation_id"
  end

  create_table "social_connections", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.text "access_token"
    t.datetime "created_at", null: false
    t.datetime "expires_at"
    t.string "external_user_id"
    t.jsonb "metadata", default: {}, null: false
    t.string "provider", null: false
    t.text "refresh_token"
    t.string "scopes"
    t.datetime "updated_at", null: false
    t.bigint "user_id", null: false
    t.index ["user_id", "provider"], name: "index_social_connections_on_user_id_and_provider", unique: true
    t.index ["user_id"], name: "index_social_connections_on_user_id"
  end

  create_table "user_feature_settings", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.datetime "created_at", null: false
    t.boolean "enabled", default: true, null: false
    t.string "key", null: false
    t.datetime "updated_at", null: false
    t.bigint "user_id", null: false
    t.index ["user_id", "key"], name: "index_user_feature_settings_on_user_id_and_key", unique: true
    t.index ["user_id"], name: "index_user_feature_settings_on_user_id"
  end

  create_table "users", force: :cascade do |t|
    t.string "country", limit: 2
    t.datetime "created_at", null: false
    t.datetime "current_sign_in_at"
    t.string "current_sign_in_ip"
    t.string "email", default: "", null: false
    t.string "encrypted_password", default: "", null: false
    t.string "first_name"
    t.float "formality_level"
    t.float "last_latitude"
    t.float "last_longitude"
    t.string "last_name"
    t.datetime "last_proactive_at"
    t.string "last_proactive_skill"
    t.datetime "last_sign_in_at"
    t.string "last_sign_in_ip"
    t.datetime "onboarding_completed_at"
    t.text "otp_backup_codes"
    t.string "phone_number"
    t.datetime "phone_verified_at"
    t.string "provider"
    t.string "provider_uid"
    t.datetime "remember_created_at"
    t.datetime "reset_password_sent_at"
    t.string "reset_password_token"
    t.string "role", default: "user", null: false
    t.integer "sign_in_count", default: 0, null: false
    t.string "timezone"
    t.boolean "two_factor_enabled", default: false
    t.string "two_factor_method"
    t.string "two_factor_secret"
    t.datetime "updated_at", null: false
    t.text "user_image_data"
    t.index ["email"], name: "index_users_on_email", unique: true
    t.index ["phone_number"], name: "index_users_on_phone_number", unique: true
    t.index ["provider", "provider_uid"], name: "index_users_on_provider_and_provider_uid", unique: true, where: "(provider_uid IS NOT NULL)"
    t.index ["reset_password_token"], name: "index_users_on_reset_password_token", unique: true
    t.index ["role"], name: "index_users_on_role"
  end

  create_table "voice_enrollments", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.datetime "created_at", null: false
    t.float "embedding_quality"
    t.text "start_phrase_audio_data"
    t.string "start_phrase_text"
    t.string "status", default: "pending", null: false
    t.text "stop_phrase_audio_data"
    t.string "stop_phrase_text"
    t.datetime "updated_at", null: false
    t.bigint "user_id", null: false
    t.index ["user_id"], name: "index_voice_enrollments_on_user_id", unique: true
  end

  add_foreign_key "audio_chunks", "audio_sessions"
  add_foreign_key "audio_sessions", "users"
  add_foreign_key "audio_usages", "users"
  add_foreign_key "avatars", "users"
  add_foreign_key "conversations", "users"
  add_foreign_key "device_tokens", "users"
  add_foreign_key "messages", "conversations"
  add_foreign_key "social_connections", "users"
  add_foreign_key "user_feature_settings", "users"
  add_foreign_key "voice_enrollments", "users"
end
