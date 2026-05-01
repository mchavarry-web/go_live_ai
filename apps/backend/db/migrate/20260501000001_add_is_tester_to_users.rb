class AddIsTesterToUsers < ActiveRecord::Migration[8.1]
  def change
    add_column :users, :is_tester, :boolean, default: false, null: false
  end
end
