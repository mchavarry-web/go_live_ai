# A 5-minute slice of a recording session. Each chunk uploads independently,
# carries its own transcription state, and stores the resulting transcript
# inline so the History screen can render without round-tripping FastAPI.
class CreateAudioChunks < ActiveRecord::Migration[8.1]
  def change
    create_table :audio_chunks, id: :uuid do |t|
      t.references :audio_session, null: false, foreign_key: true, type: :uuid
      t.integer  :sequence_number, null: false
      t.datetime :started_at, null: false
      t.float    :duration_seconds
      # Shrine attachment in :store_private (see AudioChunkUploader).
      t.text     :audio_data
      # transcription_status: pending | running | done | failed | skipped_quota
      t.string   :transcription_status, null: false, default: "pending"
      t.text     :transcript
      t.jsonb    :segments, null: false, default: []
      t.string   :language
      t.integer  :transcription_attempts, null: false, default: 0
      t.string   :idempotency_key
      t.jsonb    :metadata, null: false, default: {}
      t.timestamps
    end
    add_index :audio_chunks, [:audio_session_id, :sequence_number], unique: true
    add_index :audio_chunks, :transcription_status
  end
end
