# This file should ensure the existence of records required to run the application in every environment (production,
# development, test). The code here should be idempotent so that it can be executed at any point in every environment.
# The data can then be loaded with the bin/rails db:seed command (or created alongside the database with db:setup).

puts "Creating roles..."
roles = [
  { name: 'administrator', description: 'System administrator with full access' },
  { name: 'client', description: 'Client user with panic button device' },
  { name: 'emergency_contact', description: 'Emergency contact for clients' }
]

roles.each do |role_attrs|
  Role.find_or_create_by!(name: role_attrs[:name]) do |role|
    role.description = role_attrs[:description]
  end
end

puts "Created #{Role.count} roles"

# Create admin user
puts "Creating admin user..."
admin_email = 'admin@misos.com'
admin = User.find_or_initialize_by(email: admin_email)

if admin.new_record?
  admin.first_name = 'Admin'
  admin.last_name = 'User'
  admin.password = 'password123'
  admin.password_confirmation = 'password123'
  admin.save!

  admin_role = Role.find_by(name: 'administrator')
  admin.roles << admin_role unless admin.roles.include?(admin_role)

  puts "Admin user created: #{admin_email} / password123"
else
  puts "Admin user already exists: #{admin_email}"
end

# Create 2nd admin user
puts "Creating 2nd admin user..."
admin_email = 'augusto@devtechperu.com'
admin = User.find_or_initialize_by(email: admin_email)

if admin.new_record?
  admin.first_name = 'Augusto'
  admin.last_name = 'Admin'
  admin.password = '12345678'
  admin.password_confirmation = '12345678'
  admin.save!

  admin_role = Role.find_by(name: 'administrator')
  admin.roles << admin_role unless admin.roles.include?(admin_role)

  puts "2nd Admin user created: #{admin_email} / 12345678"
else
  puts "2nd Admin user already exists: #{admin_email}"
end
