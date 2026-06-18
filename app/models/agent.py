"""Agent action and status models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    ANALYZE_MARKET = "analyze_market"
    EXECUTE_TRADE = "execute_trade"
    SUBSCRIBE_EVENTS = "subscribe_events"
    REBALANCE = "rebalance"
    CHECK_HEALTH = "check_health"


class AgentAction(BaseModel):
    """A request to trigger an agent action."""

    action_type: ActionType
    params: dict = Field(default_factory=dict, description="Action-specific parameters")
    priority: int = Field(default=0, ge=0, le=10, description="0=low, 10=critical")


class AgentActionResponse(BaseModel):
    """Response after submitting an agent action."""

    task_id: str
    status: str  # accepted | rejected | error
    message: str


class AgentInfo(BaseModel):
    """Status of a single agent."""

    agent_id: str
    agent_type: str  # market | execution | listener
    status: str  # idle | running | error | stopped
    current_task: str | None = None
    uptime_seconds: float = 0.0


class AgentStatusResponse(BaseModel):
    """Status overview of all agents."""

    agents: list[AgentInfo] = Field(default_factory=list)
    active_tasks: int = 0
