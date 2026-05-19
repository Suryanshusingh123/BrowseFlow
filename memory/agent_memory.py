"""
AgentMemory — composes all three memory layers into one object.

This is the only import other modules need:

    from memory.agent_memory import agent_memory

    agent_memory.sessions.has("amazon.in")
    agent_memory.results.get("search amazon laptops")
    agent_memory.preferences.get("max_steps")

One singleton instance is created at the bottom of this file.
All three layers share a single MemoryStore (same base directory).
"""

from memory.store import MemoryStore
from memory.sessions import SessionMemory
from memory.results import ResultsMemory
from memory.preferences import PreferencesMemory
from memory.site_knowledge import SiteKnowledgeMemory


class AgentMemory:
    """
    Single access point for all persistent agent state.

    Attributes:
        sessions       — browser login state per domain
        results        — cached extraction results
        preferences    — user settings / request defaults
        site_knowledge — learned facts about specific websites
    """

    def __init__(self, base_dir: str = "memory"):
        store = MemoryStore(base_dir)
        self.sessions       = SessionMemory(store)
        self.results        = ResultsMemory(store)
        self.preferences    = PreferencesMemory(store)
        self.site_knowledge = SiteKnowledgeMemory(store)

    def __repr__(self) -> str:
        n_sessions = len(self.sessions.list_all())
        n_results  = len(self.results.list_all())
        prefs      = self.preferences.get_all()
        return (
            f"AgentMemory("
            f"sessions={n_sessions}, "
            f"cached_results={n_results}, "
            f"preferences={list(prefs.keys())})"
        )


# Global singleton — import this everywhere
agent_memory = AgentMemory()
