class Admin::DashboardController < Admin::AdminController
  def index
    @users_count         = User.count
    @admins_count        = User.where(role: "administrator").count
    @onboarded_count     = User.where.not(onboarding_completed_at: nil).count

    @conversations_count = Conversation.count
    @messages_count      = Message.count
    @proactive_count     = Message.where.not(proactive_skill: nil).count

    @social_totals       = SocialConnection.group(:provider).count # { "spotify" => 2, ... }
    @device_tokens_count = DeviceToken.active.count

    @recent_users    = User.order(created_at: :desc).limit(5)
    @recent_messages = Message.includes(conversation: :user).order(created_at: :desc).limit(5)
  end
end
