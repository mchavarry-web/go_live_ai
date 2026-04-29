# Daily usage rollup for server-enforced quota (default 480 transcribed
# minutes / user / day). One row per (user, usage_date) — usage_date is the
# user's local calendar date. Updated only on successful transcription.
class CreateAudioUsages < ActiveRecord::Migration[8.1]
  def change
    create_table :audio_usages, id: :uuid do |t|
      t.references :user, null: false, foreign_key: true
      t.date     :usage_date, null: false
      t.integer  :transcribed_seconds, null: false, default: 0
      t.integer  :uploaded_chunks,     null: false, default: 0
      t.timestamps
    end
    add_index :audio_usages, [:user_id, :usage_date], unique: true
  end
end
