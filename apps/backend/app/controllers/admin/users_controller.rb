class Admin::UsersController < Admin::AdminController
  before_action :set_user, only: %i[show edit update destroy assign_role remove_role]

  def index
    respond_to do |format|
      format.html do
        authorize! :read, User
        @users = User.all
        @datatable_options = "resource_name:'User';sort_0_desc;"
      end
      format.json do
        authorize! :read, User
        render json: UsersDataTable.new(params, view_context: view_context)
      end
    end
  end

  def show
    authorize! :read, @user
  end

  def new
    authorize! :create, User
    @user = User.new
    @available_roles = Role.all
  end

  def create
    @user = User.new(user_params.except(:role_ids))

    # Auto-generate password if both password and confirmation are blank
    if @user.password.blank? && user_params[:password_confirmation].blank?
      generated_password = SecureRandom.alphanumeric(12)
      @user.password = generated_password
      @user.password_confirmation = generated_password
    end

    authorize! :create, @user

    if @user.save
      # Assign roles if provided
      if user_params[:role_ids].present?
        role_ids = user_params[:role_ids].reject(&:blank?)
        @user.role_ids = role_ids
      end

      redirect_to admin_users_path, notice: 'Usuario creado exitosamente'
    else
      @available_roles = Role.all
      render :new, status: :unprocessable_entity
    end
  end

  def edit
    authorize! :update, @user
    @available_roles = Role.all
  end

  def update
    authorize! :update, @user

    # Handle password updates
    update_params = user_params.except(:role_ids)
    if update_params[:password].blank?
      update_params.delete(:password)
      update_params.delete(:password_confirmation)
    end

    if @user.update(update_params)
      # Update roles if provided
      if user_params[:role_ids].present?
        role_ids = user_params[:role_ids].reject(&:blank?)
        @user.role_ids = role_ids
      end

      redirect_to admin_users_path, notice: 'Usuario actualizado exitosamente'
    else
      @available_roles = Role.all
      render :edit, status: :unprocessable_entity
    end
  end

  def destroy
    authorize! :destroy, @user

    if @user.destroy
      redirect_to admin_users_path, notice: 'Usuario eliminado exitosamente'
    else
      redirect_to admin_users_path, alert: 'El usuario no pudo ser eliminado'
    end
  end

  def assign_role
    authorize! :update, @user
    role = Role.find(params[:role_id])

    unless @user.roles.include?(role)
      @user.roles << role
      redirect_to admin_user_path(@user), notice: "Rol #{role.name} asignado exitosamente"
    else
      redirect_to admin_user_path(@user), alert: 'El usuario ya tiene este rol'
    end
  end

  def remove_role
    authorize! :update, @user
    role = Role.find(params[:role_id])

    if @user.roles.include?(role)
      @user.roles.delete(role)
      redirect_to admin_user_path(@user), notice: "Rol #{role.name} eliminado exitosamente"
    else
      redirect_to admin_user_path(@user), alert: 'El usuario no tiene este rol'
    end
  end

  private

  def set_user
    @user = User.find(params[:id])
  end

  def user_params
    params.require(:user).permit(
      :first_name,
      :last_name,
      :email,
      :phone_number,
      :password,
      :password_confirmation,
      :two_factor_enabled,
      :two_factor_method,
      :user_image,
      role_ids: []
    )
  end
end
