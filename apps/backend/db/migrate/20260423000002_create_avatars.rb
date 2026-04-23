# Avatar model — 1:1 with User. The "personality brain" metadata for the
# per-user avatar. Prompt-time fields (e.g. persona_evolution state, insights)
# live in the FastAPI pgvector DB; only the user-visible knobs live here.
class CreateAvatars < ActiveRecord::Migration[8.1]
  def change
    create_table :avatars, id: :uuid do |t|
      t.references :user, null: false, foreign_key: true, type: :bigint, index: { unique: true }
      t.string   :name
      t.integer  :knowledge_level, null: false, default: 1        # 1..10
      t.jsonb    :appearance,      null: false, default: {}
      t.jsonb    :behavior,        null: false, default: {}
      t.timestamps
    end
  end
end
