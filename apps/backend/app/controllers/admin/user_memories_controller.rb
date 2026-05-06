# Drill-down into the FastAPI-stored RAG memory for a single user.
#
# All persistence lives in apps/ai-agents — this controller proxies via
# AiAgentsClient. There is no Rails model; the records are plain hashes
# shaped like:
#   { "id"=>"…", "content"=>"…", "category"=>"…", "source"=>"…",
#     "confidence"=>0.95, "created_at"=>"2026-…" }
class Admin::UserMemoriesController < Admin::AdminController
  before_action :set_user
  before_action :set_client

  def index
    authorize! :read, @user
    response = @client.list_insights(@user.id) || {}
    cats     = @client.insight_categories(@user.id) || {}
    srcs     = @client.insight_sources(@user.id) || {}
    @insights        = (response["insights"] || []).map(&:with_indifferent_access)
    @total           = response["total_insights"].to_i
    @knowledge_level = response["knowledge_level"]
    @categories      = (cats["counts"]   || {}).sort_by { |_, n| -n }
    @sources         = (srcs["sources"]  || {}).sort_by { |_, n| -n }

    @selected_category = params[:category].presence
    @selected_source   = params[:source].presence
    @q                 = params[:q].presence
    @insights = @insights.select { |i| i["category"] == @selected_category } if @selected_category
    @insights = @insights.select { |i| i["source"]   == @selected_source }   if @selected_source
    @insights = @insights.select { |i| i["content"].to_s.downcase.include?(@q.downcase) } if @q
  rescue StandardError => e
    Rails.logger.warn("[admin/memories] index failed: #{e.class}: #{e.message}")
    @insights, @categories, @sources = [], [], []
    @total = 0
    @upstream_error = e.message
  end

  def show
    authorize! :read, @user
    @insight = find_insight!(params[:id])
    redirect_to admin_user_memories_path(@user), alert: "Insight no encontrado." unless @insight
  end

  def edit
    authorize! :update, @user
    @insight = find_insight!(params[:id])
    redirect_to admin_user_memories_path(@user), alert: "Insight no encontrado." unless @insight
  end

  def update
    authorize! :update, @user
    content = params.require(:insight).permit(:content)[:content]
    result  = @client.update_insight(user_id: @user.id, insight_id: params[:id], content: content)
    if result.is_a?(Hash) && result["id"]
      redirect_to admin_user_memory_path(@user, params[:id]), notice: "Insight actualizado."
    else
      redirect_to edit_admin_user_memory_path(@user, params[:id]),
                  alert: "No se pudo actualizar (#{result.inspect.first(120)})."
    end
  end

  def destroy
    authorize! :update, @user
    if @client.delete_insight(user_id: @user.id, insight_id: params[:id])
      redirect_to admin_user_memories_path(@user), notice: "Insight eliminado."
    else
      redirect_to admin_user_memories_path(@user), alert: "No se pudo eliminar el insight."
    end
  end

  private

  def set_user
    @user = User.find(params[:user_id])
  end

  def set_client
    @client = AiAgentsClient.new
  end

  # FastAPI does not expose a single-insight GET, so we hit the list and
  # filter client-side. List size is bounded (insights are per-user) so this
  # is acceptable for an admin-only screen.
  def find_insight!(id)
    list = (@client.list_insights(@user.id) || {})["insights"] || []
    list.map(&:with_indifferent_access).find { |i| i["id"] == id }
  end
end
