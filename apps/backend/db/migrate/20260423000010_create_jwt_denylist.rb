# JWT access-token blacklist. When a user signs out, the access token's
# jti (JWT ID) is stored here until the token's natural expiry. Any
# incoming request carrying a denylisted jti is rejected.
class CreateJwtDenylist < ActiveRecord::Migration[8.1]
  def change
    create_table :jwt_denylist do |t|
      t.string   :jti,     null: false
      t.datetime :exp,     null: false   # natural token expiry; row GC'd after
      t.timestamps
    end
    add_index :jwt_denylist, :jti, unique: true
    add_index :jwt_denylist, :exp
  end
end
