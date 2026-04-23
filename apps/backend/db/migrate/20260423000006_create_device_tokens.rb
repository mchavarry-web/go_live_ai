# One push-notification token per device installation. The same user can
# have multiple tokens (phone + tablet + web). Rotate by marking `active`
# false on the old token when a new one registers for the same device.
class CreateDeviceTokens < ActiveRecord::Migration[8.1]
  def change
    create_table :device_tokens, id: :uuid do |t|
      t.references :user, null: false, foreign_key: true, type: :bigint, index: true
      t.string   :token,     null: false
      t.string   :platform,  null: false             # "ios" | "android" | "web"
      t.boolean  :active,    null: false, default: true
      t.jsonb    :metadata,  null: false, default: {}
      t.timestamps
    end
    add_index :device_tokens, :token, unique: true
  end
end
