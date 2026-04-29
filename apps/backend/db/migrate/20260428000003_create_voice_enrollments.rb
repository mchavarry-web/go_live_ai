# One enrollment record per user, holding the start/stop trigger phrase
# recordings + their transcribed text. Phase 1 stores them as samples for
# Phase 2 (no embedding computed yet).
class CreateVoiceEnrollments < ActiveRecord::Migration[8.1]
  def change
    create_table :voice_enrollments, id: :uuid do |t|
      t.references :user, null: false, foreign_key: true, index: { unique: true }
      t.text   :start_phrase_audio_data
      t.text   :stop_phrase_audio_data
      t.string :start_phrase_text
      t.string :stop_phrase_text
      # Phase 1 statuses: pending | ready
      # Phase 2 will add: enrolling | failed
      t.string :status, null: false, default: "pending"
      t.float  :embedding_quality
      t.timestamps
    end
  end
end
