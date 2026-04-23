# frozen_string_literal: true

class DeviseCreateUsers < ActiveRecord::Migration[8.1]
  def change
    create_table :users do |t|
      ## Database authenticatable
      t.string :email,              null: false, default: ""
      t.string :encrypted_password, null: false, default: ""

      ## Recoverable
      t.string   :reset_password_token
      t.datetime :reset_password_sent_at

      ## Rememberable
      t.datetime :remember_created_at

      ## Trackable
      t.integer  :sign_in_count, default: 0, null: false
      t.datetime :current_sign_in_at
      t.datetime :last_sign_in_at
      t.string   :current_sign_in_ip
      t.string   :last_sign_in_ip

      ## Custom fields
      t.string :first_name
      t.string :last_name
      t.string :phone_number
      t.datetime :phone_verified_at

      ## Two-Factor Authentication
      t.boolean :two_factor_enabled, default: false
      t.string :two_factor_method # sms, authenticator
      t.string :two_factor_secret
      t.text :otp_backup_codes

      ## User Profile Image
      t.text :user_image_data

      t.timestamps null: false
    end

    add_index :users, :email,                unique: true
    add_index :users, :reset_password_token, unique: true
    add_index :users, :phone_number,         unique: true
  end
end
