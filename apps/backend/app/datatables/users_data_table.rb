class UsersDataTable
  include ActionView::Helpers::UrlHelper
  include ActionView::Helpers::TagHelper

  delegate :params, :link_to, :admin_user_path, :current_user, to: :@view_context

  def initialize(params, opts = {})
    @params = params
    @view_context = opts[:view_context]
  end

  def as_json(options = {})
    {
      draw: params[:draw].to_i,
      recordsTotal: User.count,
      recordsFiltered: filtered_users_count,
      data: data
    }
  end

  private

  def data
    users.map do |user|
      [
        user.id,
        user.name,
        user.email,
        user.phone_number || 'N/A',
        roles_badges(user),
        organization_name(user),
        two_factor_status(user),
        actions(user)
      ]
    end
  end

  def roles_badges(user)
    user.roles.map do |role|
      badge_color = case role.name
      when 'administrator' then 'bg-red-100 text-red-800'
      when 'client' then 'bg-blue-100 text-blue-800'
      when 'emergency_contact' then 'bg-green-100 text-green-800'
      else 'bg-gray-100 text-gray-800'
      end

      "<span class='inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium #{badge_color}'>#{role_name_spanish(role.name)}</span>"
    end.join(' ').html_safe
  end

  def role_name_spanish(role_name)
    {
      'administrator' => 'Administrador',
      'client' => 'Cliente',
      'emergency_contact' => 'Contacto de Emergencia'
    }[role_name] || role_name.humanize
  end

  def organization_name(user)
    # For now, return N/A since we don't have organization association yet
    'N/A'
  end

  def two_factor_status(user)
    user.two_factor_enabled? ? 'Sí' : 'No'
  end

  def users
    @users ||= fetch_users
  end

  def fetch_users
    users = User.includes(:roles).all
    users = users.where("email ILIKE ? OR first_name ILIKE ? OR last_name ILIKE ?",
                        "%#{search_value}%", "%#{search_value}%", "%#{search_value}%") if search_value.present?
    users = sort_records(users)
    users = users.limit(per_page).offset(page * per_page)
    users
  end

  def sort_records(records)
    if params[:order].present?
      column_index = params[:order]['0'][:column].to_i
      direction = params[:order]['0'][:dir]

      # Map column indices to database columns
      column_name = case column_index
      when 0 then 'id'
      when 1 then 'first_name'
      when 2 then 'email'
      when 3 then 'phone_number'
      else 'id'
      end

      records.order("#{column_name} #{direction}")
    else
      records.order(id: :desc)
    end
  end

  def filtered_users_count
    users = User.all
    users = users.where("email ILIKE ? OR first_name ILIKE ? OR last_name ILIKE ?",
                        "%#{search_value}%", "%#{search_value}%", "%#{search_value}%") if search_value.present?
    users.count
  end

  def actions(user)
    actions = []
    actions << link_to('Ver', admin_user_path(user), class: "btn btn-sm btn-outline-primary")
    actions << link_to('Editar', [:edit, :admin, user], class: "btn btn-sm btn-outline-secondary")

    # Add "Borrar 2FA" button if user has 2FA enabled and is not current user
    # if current_user.admin? && user != current_user && user.two_factor_enabled?
    #   actions << link_to('Borrar 2FA', [:remove_two_factor, :admin, user],
    #                     data: {
    #                       turbo_method: :delete,
    #                       turbo_confirm: "¿Está seguro de que desea eliminar la configuración 2FA de #{user.name}?"
    #                     },
    #                     class: "btn btn-sm btn-outline-warning")
    # end

    actions << link_to('Eliminar', [:admin, user],
                      data: {
                        turbo_method: :delete,
                        turbo_confirm: "¿Está seguro de que desea eliminar este usuario?"
                      },
                      class: "btn btn-sm btn-outline-danger")
    actions.join(" ").html_safe
  end

  def page
    params[:start].to_i / per_page
  end

  def per_page
    params[:length].to_i > 0 ? params[:length].to_i : 10
  end

  def search_value
    params.dig(:search, :value)
  end
end
