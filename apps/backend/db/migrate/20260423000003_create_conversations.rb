# Conversation owns a thread of Messages between a User and their avatar.
# `title` is auto-generated from the first user message; nullable until set.
# `last_active_at` powers inactivity detection (the proactive-greeting "absence"
# input) and conversation-list ordering in the Expo drawer.
class CreateConversations < ActiveRecord::Migration[8.1]
  def change
    create_table :conversations, id: :uuid do |t|
      t.references :user, null: false, foreign_key: true, type: :bigint, index: true
      t.string   :title
      t.datetime :last_active_at, null: false
      t.timestamps
    end
    add_index :conversations, %i[user_id last_active_at]
  end
end
