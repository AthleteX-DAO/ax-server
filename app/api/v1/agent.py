"""Agent control endpoints — trigger actions and query agent status."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.agent import AgentAction, AgentActionResponse, AgentStatusResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/action", response_model=AgentActionResponse)
async def trigger_action(action: AgentAction):
    """Trigger an agent action.

    Dispatches the action to the appropriate agent (market, execution, listener)
    based on the action type. Returns a task ID for tracking.

    Action types:
        - analyze_market: Run market analysis via MarketAgent
        - execute_trade: Submit a trade via ExecutionAgent
        - subscribe_events: Start listening for events via ListenerAgent
    """
    # TODO: Dispatch to agent framework
    return AgentActionResponse(
        task_id="pending",
        status="accepted",
        message=f"Action '{action.action_type}' queued for processing",
    )


@router.get("/status", response_model=AgentStatusResponse)
async def agent_status():
    """Return current status of all active agents.

    Shows which agents are running, their current tasks, and health.
    """
    # TODO: Query agent registry
    return AgentStatusResponse(
        agents=[],
        active_tasks=0,
    )
