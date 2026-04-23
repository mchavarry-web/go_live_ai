# Replace the bounded knowledge_level column with unbounded counters.
# knowledge_level becomes a computed method on the model; raw counters
# drive it. Counter caches are maintained via after_create_commit hooks on
# Message + SocialConnection + a nightly Sidekiq sync from FastAPI.
class ReplaceAvatarKnowledgeLevelWithCounters < ActiveRecord::Migration[8.1]
  def change
    change_table :avatars do |t|
      t.integer  :insights_count,           null: false, default: 0
      t.integer  :conversations_count,      null: false, default: 0
      t.integer  :messages_count,           null: false, default: 0
      t.integer  :social_connections_count, null: false, default: 0
      t.integer  :days_active,              null: false, default: 0
      t.datetime :last_interaction_at
    end
    remove_column :avatars, :knowledge_level, :integer, default: 1, null: false
  end
end
