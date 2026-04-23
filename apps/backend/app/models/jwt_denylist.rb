# frozen_string_literal: true

class JwtDenylist < ApplicationRecord
  self.table_name = "jwt_denylist"

  # Rows are expected to GC themselves via a nightly sweeper; any row past
  # its `exp` is safe to delete.
  def self.sweep_expired!
    where("exp < ?", Time.current).delete_all
  end

  def self.denylisted?(jti)
    exists?(jti: jti)
  end
end
