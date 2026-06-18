"""Base agent class — all agents inherit from this.

Provides lifecycle management, logging, and a standard interface
for running agent loops.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """Abstract base class for all AthleteX agents.

    Subclasses must implement:
        - setup()   — one-time initialisation
        - step()    — single iteration of the agent loop
        - teardown() — cleanup on shutdown
    """

    def __init__(self, agent_id: str, agent_type: str) -> None:
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.logger = logging.getLogger(f"ax-agent.{agent_type}.{agent_id}")
        self._running = False
        self._started_at: float | None = None
        self._current_task: str | None = None

    # ── Lifecycle ─────────────────────────────────────────────────

    @abstractmethod
    async def setup(self) -> None:
        """One-time initialisation (connect to chain, load config, etc.)."""
        ...

    @abstractmethod
    async def step(self) -> None:
        """Execute one iteration of the agent loop.

        Called repeatedly while the agent is running.
        Implementations should be idempotent and handle their own errors.
        """
        ...

    @abstractmethod
    async def teardown(self) -> None:
        """Cleanup on shutdown (close connections, flush state)."""
        ...

    # ── Run loop ──────────────────────────────────────────────────

    async def run(self, interval_seconds: float = 10.0) -> None:
        """Main agent loop — calls step() at the configured interval.

        Args:
            interval_seconds: Delay between step() calls.
        """
        self._running = True
        self._started_at = time.time()
        self.logger.info("Agent %s starting", self.agent_id)

        try:
            await self.setup()
            while self._running:
                try:
                    await self.step()
                except Exception:
                    self.logger.exception("Error in agent step")
                await asyncio.sleep(interval_seconds)
        finally:
            await self.teardown()
            self.logger.info("Agent %s stopped", self.agent_id)

    def stop(self) -> None:
        """Signal the agent to stop after the current step."""
        self._running = False

    # ── Status ────────────────────────────────────────────────────

    @property
    def status(self) -> str:
        if self._running:
            return "running"
        return "stopped"

    @property
    def uptime(self) -> float:
        if self._started_at is None:
            return 0.0
        return time.time() - self._started_at

    def to_dict(self) -> dict[str, Any]:
        """Serialise agent status for the API."""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "status": self.status,
            "current_task": self._current_task,
            "uptime_seconds": round(self.uptime, 2),
        }
