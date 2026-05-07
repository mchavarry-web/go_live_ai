# frozen_string_literal: true

# Wave C.4 (2026-05-06) — draft-mode action proposals.
#
# This controller persists proposed agent actions and exposes the
# approve/reject/edit lifecycle. **No proposal is executed by this
# controller.** Execution lives behind a future per-capability adapter
# that consumes approved rows. See docs/autonomous_agent_design.md.
class Api::V1::AgentProposalsController < Api::V1::BaseController
  before_action :load_proposal, only: %i[show approve reject edit]

  # GET /api/v1/agent/proposals?status=proposed
  def index
    scope = current_user.agent_action_logs.recent
    scope = scope.where(approval_status: params[:status]) if params[:status].present?
    render json: scope.limit(50).map { |p| serialize(p) }
  end

  # GET /api/v1/agent/proposals/:id
  def show
    render json: serialize(@proposal)
  end

  # POST /api/v1/agent/proposals
  def create
    proposal = current_user.agent_action_logs.new(create_params)
    proposal.approval_status = "proposed"
    proposal.status          = "proposed"
    if proposal.save
      render json: serialize(proposal), status: :created
    else
      render_error(proposal.errors.full_messages.join(", "), :unprocessable_entity)
    end
  end

  # PATCH /api/v1/agent/proposals/:id/approve
  #
  # Marks the row approved. Does NOT execute the underlying capability.
  def approve
    return render_error("not pending", :conflict) unless @proposal.pending?
    @proposal.transition_to!("approved")
    render json: serialize(@proposal)
  end

  # PATCH /api/v1/agent/proposals/:id/reject
  def reject
    return render_error("not pending", :conflict) unless @proposal.pending?
    @proposal.transition_to!("rejected")
    render json: serialize(@proposal)
  end

  # PATCH /api/v1/agent/proposals/:id/edit
  #
  # Updates the structured tool_input on a still-pending proposal.
  def edit
    return render_error("not pending", :conflict) unless @proposal.pending?
    if @proposal.update(edit_params)
      render json: serialize(@proposal)
    else
      render_error(@proposal.errors.full_messages.join(", "), :unprocessable_entity)
    end
  end

  private

  def load_proposal
    @proposal = current_user.agent_action_logs.find(params[:id])
  end

  def create_params
    params.permit(
      :conversation_id, :capability, :requested_action, :tool_name, :risk_level,
      tool_input: {}
    )
  end

  def edit_params
    params.permit(:requested_action, tool_input: {})
  end

  def serialize(proposal)
    {
      id:                proposal.id,
      conversation_id:   proposal.conversation_id,
      capability:        proposal.capability,
      requested_action:  proposal.requested_action,
      tool_name:         proposal.tool_name,
      tool_input:        proposal.tool_input,
      tool_output:       proposal.tool_output,
      risk_level:        proposal.risk_level,
      approval_status:   proposal.approval_status,
      executed_at:       proposal.executed_at&.iso8601,
      rollback_available: proposal.rollback_available,
      created_at:        proposal.created_at.iso8601,
      updated_at:        proposal.updated_at.iso8601
    }
  end
end
