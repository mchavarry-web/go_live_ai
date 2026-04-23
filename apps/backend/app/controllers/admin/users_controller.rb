class Admin::UsersController < Admin::AdminController
  before_action :set_user, only: %i[show edit update destroy promote demote]

  def index
    authorize! :read, User
    @users = User.order(created_at: :desc)
  end

  def show
    authorize! :read, @user
  end

  def new
    authorize! :create, User
    @user = User.new
  end

  def create
    @user = User.new(user_params)
    @user.password                ||= SecureRandom.alphanumeric(12)
    @user.password_confirmation   ||= @user.password
    authorize! :create, @user

    if @user.save
      redirect_to admin_users_path, notice: "Usuario creado exitosamente"
    else
      render :new, status: :unprocessable_entity
    end
  end

  def edit
    authorize! :update, @user
  end

  def update
    authorize! :update, @user
    if @user.update(user_params)
      redirect_to admin_user_path(@user), notice: "Usuario actualizado"
    else
      render :edit, status: :unprocessable_entity
    end
  end

  def destroy
    authorize! :destroy, @user
    @user.destroy
    redirect_to admin_users_path, notice: "Usuario eliminado"
  end

  # Promote a user to administrator.
  def promote
    authorize! :update, @user
    @user.make_admin!
    redirect_to admin_user_path(@user), notice: "#{@user.email} ahora es administrador"
  end

  # Revoke administrator access.
  def demote
    authorize! :update, @user
    @user.revoke_admin!
    redirect_to admin_user_path(@user), notice: "Administrador revocado para #{@user.email}"
  end

  private

  def set_user
    @user = User.find(params[:id])
  end

  def user_params
    params.require(:user).permit(:email, :first_name, :last_name, :phone_number,
                                 :country, :timezone, :formality_level, :role,
                                 :password, :password_confirmation)
  end
end
