# frozen_string_literal: true

# Phase 16 — immutable archive of provider-shaped social payloads.
#
# Today ``SocialConnection.metadata.raw_data`` is overwritten on every
# fetch, so when extraction logic improves we can't redrive against the
# old payload. This table snapshots each fetch so we can replay later.
# Cascades on user delete; eviction job keeps the latest 12 per
# (user, platform).
class CreateSocialDataSnapshots < ActiveRecord::Migration[8.1]
  def change
    create_table :social_data_snapshots do |t|
      t.references :user, null: false, foreign_key: { on_delete: :cascade }
      t.string  :platform, null: false
      t.datetime :fetched_at, null: false
      t.jsonb   :raw_data, null: false
      t.integer :byte_size, null: false, default: 0
      t.integer :extraction_version, null: false, default: 1
      t.timestamps
    end

    add_index :social_data_snapshots, [:user_id, :platform, :fetched_at],
              order: { fetched_at: :desc },
              name:  :ix_social_snapshots_user_platform_fetched
  end
end
