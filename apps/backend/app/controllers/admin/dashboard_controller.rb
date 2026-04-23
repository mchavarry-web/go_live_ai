class Admin::DashboardController < Admin::AdminController
  def index
    @users_count = User.count
    @administrators_count = User.joins(:roles).where(roles: { name: 'administrator' }).distinct.count
    @clients_count = User.joins(:roles).where(roles: { name: 'client' }).distinct.count
    @emergency_contacts_count = User.joins(:roles).where(roles: { name: 'emergency_contact' }).distinct.count
  end
end
