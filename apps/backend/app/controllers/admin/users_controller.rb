class Admin::UsersController < Admin::AdminController
  before_action :set_user,
                only: %i[show edit update destroy promote demote
                         reset_onboarding extract disconnect_social]

  def index
    authorize! :read, User
    scope = User.order(created_at: :desc)
    scope = scope.where("email ILIKE ?", "%#{params[:q]}%") if params[:q].present?
    scope = scope.where(provider: params[:provider]) if params[:provider].present?
    scope = scope.where(role: params[:role])         if params[:role].present?
    if params[:onboarded] == "true"
      scope = scope.where.not(onboarding_completed_at: nil)
    elsif params[:onboarded] == "false"
      scope = scope.where(onboarding_completed_at: nil)
    end
    @users = scope.limit(500)
    @q = params.slice(:q, :provider, :role, :onboarded).permit!.to_h
  end

  def show
    authorize! :read, @user
    @avatar              = @user.avatar
    @social_connections  = @user.social_connections.order(:provider)
    @device_tokens       = @user.device_tokens.order(created_at: :desc)
    @conversations       = @user.conversations.recent.limit(10)
    @recent_messages     = @user.messages.order(created_at: :desc).limit(20)
    @disabled_user_flags = @user.user_feature_settings.where(enabled: false).pluck(:key)
    @insights_count      = @avatar&.insights_count.to_i
  end

  def new
    authorize! :create, User
    @user = User.new
  end

  def create
    @user = User.new(user_params)
    @user.password              ||= SecureRandom.alphanumeric(12)
    @user.password_confirmation ||= @user.password
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

  def promote
    authorize! :update, @user
    @user.make_admin!
    redirect_to admin_user_path(@user), notice: "#{@user.email} ahora es administrador"
  end

  def demote
    authorize! :update, @user
    @user.revoke_admin!
    redirect_to admin_user_path(@user), notice: "Administrador revocado para #{@user.email}"
  end

  # Operator actions (admin-only shortcuts that the mobile app can't trigger).
  def reset_onboarding
    authorize! :update, @user
    @user.update!(onboarding_completed_at: nil)
    redirect_to admin_user_path(@user), notice: "Onboarding reseteado para #{@user.email}"
  end

  def extract
    authorize! :update, @user
    provider = params.require(:provider)
    ExtractInsightsJob.perform_later(user_id: @user.id, provider: provider)
    redirect_to admin_user_path(@user), notice: "Extracción (#{provider}) encolada"
  end

  def disconnect_social
    authorize! :update, @user
    conn = @user.social_connections.find_by(provider: params.require(:provider))
    return redirect_to admin_user_path(@user), alert: "Conexión no encontrada" unless conn
    conn.destroy!
    redirect_to admin_user_path(@user), notice: "Conexión #{conn.provider} desconectada"
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
