# frozen_string_literal: true

# Wave C.2 (2026-05-06) — per-user agent capability permissions.
# See docs/autonomous_agent_design.md.
class CreateAgentPermissions < ActiveRecord::Migration[8.1]
  def change
    create_table :agent_permissions do |t|
      t.references :user, null: false, foreign_key: { on_delete: :cascade }
      t.string  :capability,         null: false
      t.jsonb   :scope,              null: false, default: {}
      t.boolean :enabled,            null: false, default: false
      t.boolean :approval_required,  null: false, default: true
      t.string  :max_risk_level,     null: false, default: "read_only"
      t.integer :spend_limit_cents
      t.jsonb   :allowed_recipients, null: false, default: []
      t.jsonb   :allowed_domains,    null: false, default: []
      t.jsonb   :quiet_hours,        null: false, default: {}
      t.timestamps
    end

    add_index :agent_permissions, [:user_id, :capability], unique: true,
              name: :ix_agent_permissions_user_capability
    add_index :agent_permissions, [:user_id, :enabled],
              name: :ix_agent_permissions_user_enabled
  end
end
