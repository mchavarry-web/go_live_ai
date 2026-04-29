# Continuous-audio recording session (a "day of audio" or any contiguous
# user-initiated capture). Chunks belong to one session; the session owns
# total duration and overall lifecycle status.
class CreateAudioSessions < ActiveRecord::Migration[8.1]
  def change
    create_table :audio_sessions, id: :uuid do |t|
      t.references :user, null: false, foreign_key: true
      t.datetime :started_at, null: false
      t.datetime :ended_at
      t.integer  :total_duration_seconds, null: false, default: 0
      t.integer  :transcribed_seconds,    null: false, default: 0
      # status: recording | finalizing | processing | ready | ready_with_errors |
      #         cancelled | failed | abandoned | deleted
      t.string   :status, null: false, default: "recording"
      t.jsonb    :metadata, null: false, default: {}
      t.timestamps
    end
    add_index :audio_sessions, [:user_id, :started_at]
    add_index :audio_sessions, :status
  end
end
