# One row per chat turn (user OR assistant).
# `role` mirrors OpenAI / LangChain convention — user | assistant | system.
# `metadata` carries anything the FastAPI side wants to stamp on the message:
# tool calls, token counts, detected emotion, proactive_skill_id, etc.
class CreateMessages < ActiveRecord::Migration[8.1]
  def change
    create_table :messages, id: :uuid do |t|
      t.references :conversation, null: false, foreign_key: true, type: :uuid, index: true
      t.string :role,    null: false                  # "user" | "assistant" | "system"
      t.text   :content, null: false, default: ""
      t.string :proactive_skill                       # set only on assistant proactive greetings
      t.jsonb  :metadata, null: false, default: {}
      t.timestamps
    end
    add_index :messages, %i[conversation_id created_at]
  end
end
