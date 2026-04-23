# Idempotent seed. Creates the two roles Go Live uses and one admin user.

puts "Creating roles..."
ROLES = [
  { name: "administrator", description: "System administrator — full access to /admin" },
  { name: "user",          description: "End user (mobile app)" }
].freeze

ROLES.each do |attrs|
  Role.find_or_create_by!(name: attrs[:name]) do |r|
    r.description = attrs[:description]
  end
end
puts "  → #{Role.count} roles: #{Role.pluck(:name).join(', ')}"

admin_email = "admin@golive.local"
puts "Creating admin user (#{admin_email})..."

admin = User.find_or_initialize_by(email: admin_email)
if admin.new_record?
  admin.first_name = "Admin"
  admin.last_name  = "User"
  admin.password   = "password123"
  admin.password_confirmation = "password123"
  admin.provider   = "email"
  admin.save!
  admin.add_role(:administrator)
  puts "  → created (password: password123)"
else
  admin.add_role(:administrator) unless admin.admin?
  puts "  → already exists"
end
