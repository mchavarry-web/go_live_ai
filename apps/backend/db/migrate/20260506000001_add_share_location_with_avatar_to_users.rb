# frozen_string_literal: true

# Phase 10 — reactive location context.
#
# Privacy-gated flag: when true, the avatar's reactive chat prompt
# receives the user's last known coordinates so it can answer "qué hago
# hoy en Lima"-type questions naturally. Default off — explicit toggle.
class AddShareLocationWithAvatarToUsers < ActiveRecord::Migration[8.1]
  def change
    add_column :users, :share_location_with_avatar, :boolean, default: false, null: false
  end
end
