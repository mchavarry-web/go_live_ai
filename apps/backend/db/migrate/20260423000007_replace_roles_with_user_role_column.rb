# Drop the multi-role join (roles + user_roles) and replace it with a single
# `role` enum column on users. Go Live has exactly two roles — 'user' and
# 'administrator' — and the template's polymorphic role infrastructure is
# overkill. Dev-only port; no data migration needed.
class ReplaceRolesWithUserRoleColumn < ActiveRecord::Migration[8.1]
  def up
    add_column :users, :role, :string, null: false, default: "user"
    add_index  :users, :role

    drop_table :user_roles, if_exists: true
    drop_table :roles,      if_exists: true
  end

  def down
    create_table :roles do |t|
      t.string :name
      t.string :description
      t.timestamps
    end
    create_table :user_roles do |t|
      t.bigint :user_id
      t.bigint :role_id
      t.timestamps
    end
    remove_index  :users, :role, if_exists: true
    remove_column :users, :role
  end
end
