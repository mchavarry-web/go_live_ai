# frozen_string_literal: true

# Wave C.3 (2026-05-06) — append-only agent action audit log.
# See docs/autonomous_agent_design.md.
class CreateAgentActionLogs < ActiveRecord::Migration[8.1]
  def change
    create_table :agent_action_logs do |t|
      t.references :user, null: false, foreign_key: { on_delete: :cascade }
      # Conversation is tracked via UUID-string reference (Rails uses uuid PKs
      # on conversations) — not a Rails belongs_to to avoid loading a
      # foreign-keyed type at this layer.
      t.string  :conversation_id
      t.string  :capability,        null: false
      t.text    :requested_action,  null: false
      t.string  :tool_name
      t.jsonb   :tool_input,        null: false, default: {}
      t.jsonb   :tool_output,       null: false, default: {}
      t.string  :risk_level,        null: false, default: "read_only"
      t.string  :approval_status,   null: false, default: "proposed"
      t.datetime :executed_at
      t.boolean :rollback_available, null: false, default: false
      t.jsonb   :rollback_payload
      t.string  :status,            null: false, default: "proposed"
      t.text    :error
      t.timestamps
    end

    add_index :agent_action_logs, [:user_id, :executed_at], order: { executed_at: :desc },
              name: :ix_agent_action_logs_user_executed_at
    add_index :agent_action_logs, [:user_id, :approval_status],
              name: :ix_agent_action_logs_user_status
    add_index :agent_action_logs, [:conversation_id],
              name: :ix_agent_action_logs_conversation
  end
end
