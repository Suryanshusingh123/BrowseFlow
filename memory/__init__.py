"""
Agent Memory — persistent state across runs.

Three layers:
  sessions     — browser cookies + localStorage (login state)
  results      — cached extraction results with TTL
  preferences  — user settings that act as request defaults

Usage:
    from memory.agent_memory import agent_memory

    # Sessions
    agent_memory.sessions.has("amazon.in")
    await agent_memory.sessions.save(context, "amazon.in")

    # Results
    agent_memory.results.get("search amazon for laptops")
    agent_memory.results.save("search amazon for laptops", result_dict)

    # Preferences
    agent_memory.preferences.get("max_steps", default=15)
    agent_memory.preferences.set("summarize_by_default", True)
"""

from memory.agent_memory import agent_memory

__all__ = ["agent_memory"]
