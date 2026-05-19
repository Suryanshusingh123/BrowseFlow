"""
Run session store — tracks active /run-async runs in memory.

Why in-memory and not on disk?
  asyncio.Event objects can't be serialized to JSON.
  Run sessions only need to live as long as the agent loop —
  once the run is done, the session can be garbage-collected.

The central mechanism:
  RunSession.approval_event is an asyncio.Event.
  The agent loop calls await approval_event.wait() to suspend itself.
  The approve/deny endpoint calls approval_event.set() to resume it.
  No polling, no sleep loops — the event loop handles the scheduling.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RunSession:
    run_id: str
    status: str = "running"
    # "running"           — agent is executing steps
    # "awaiting_approval" — agent is paused, waiting for human
    # "done"              — agent finished successfully
    # "error"             — agent crashed

    pending_action: Optional[dict] = None
    # The action the agent wants to take but needs approval for.
    # Set before pausing, cleared after resuming.

    approval_event: asyncio.Event = field(default_factory=asyncio.Event)
    # The pause/resume primitive.
    # Agent calls .wait() to suspend. Approve/deny calls .set() to resume.

    approved: bool = False
    # Set by the approve/deny endpoint before calling .set() on the event.
    # The agent reads this after waking to know which path to take.

    result: Optional[dict] = None
    error:  Optional[str]  = None


class RunSessionStore:
    """In-memory store for all active run sessions."""

    def __init__(self):
        self._sessions: dict[str, RunSession] = {}

    def create(self, run_id: str) -> RunSession:
        session = RunSession(run_id=run_id)
        self._sessions[run_id] = session
        return session

    def get(self, run_id: str) -> Optional[RunSession]:
        return self._sessions.get(run_id)

    def delete(self, run_id: str) -> None:
        self._sessions.pop(run_id, None)

    def list_active(self) -> list[dict]:
        return [
            {
                "run_id": s.run_id,
                "status": s.status,
                "pending_action": s.pending_action,
            }
            for s in self._sessions.values()
        ]


# Global singleton — shared between the agent loop and the HTTP endpoints
run_sessions = RunSessionStore()
