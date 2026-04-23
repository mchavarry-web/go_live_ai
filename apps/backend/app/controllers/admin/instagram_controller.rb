# Admin panel for Instagram ingestion. Replaces gln-web-front/src/app/dashboard
# (Next.js) with a Hotwire page. Lists users with Instagram data, shows
# last-ingested metadata, and lets an operator re-run extraction on demand.
class Admin::InstagramController < Admin::AdminController
  def index
    @instagram_connections = SocialConnection.for("instagram")
                                              .includes(:user)
                                              .order(updated_at: :desc)
  end

  def extract
    conn = SocialConnection.for("instagram").find(params[:id])
    ExtractInsightsJob.perform_later(user_id: conn.user_id, provider: "instagram")
    redirect_to admin_instagram_path, notice: "Extracción encolada para #{conn.user.email}"
  end
end
