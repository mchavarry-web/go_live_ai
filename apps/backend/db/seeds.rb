# Idempotent seed. Creates the admin user.

admin_email = "admin@golive.local"
puts "Seeding admin user (#{admin_email})..."

admin = User.find_or_initialize_by(email: admin_email)
if admin.new_record?
  admin.first_name = "Admin"
  admin.last_name  = "User"
  admin.password   = "password123"
  admin.password_confirmation = "password123"
  admin.provider   = "email"
  admin.role       = "administrator"
  admin.save!
  puts "  → created (password: password123)"
else
  admin.update!(role: "administrator") unless admin.admin?
  puts "  → already exists, role ensured"
end
