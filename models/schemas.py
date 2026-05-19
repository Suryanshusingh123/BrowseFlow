from pydantic import BaseModel
from typing import Optional, Any


class AgentRequest(BaseModel):
    """What the user sends to our API."""
    goal: str
    max_steps: int = 15
    summarize: bool = False      # Phase 4: set True to get AI analysis on top of extraction

    # Memory fields (all optional — memory is always opt-in)
    session: Optional[str] = None
    """
    Domain key for session persistence, e.g. "amazon.in".
    If set:
      - Loads saved cookies before the run (agent starts logged in).
      - Saves updated cookies after the run (new login persisted).
    """

    use_cache: bool = False
    """
    If True, return cached results if a fresh result exists for this goal.
    The agent loop is skipped entirely on a cache hit — zero browser overhead.
    """

    cache_ttl_hours: float = 1.0
    """
    How old a cached result can be before it's considered stale.
    Only matters when use_cache=True.
    """


class AgentResponse(BaseModel):
    """What our API returns."""
    success: bool
    result: Optional[dict] = None
    summary: Optional[str] = None
    steps_taken: Optional[int] = None
    history: Optional[list] = None
    error: Optional[str] = None
    from_cache: bool = False     # True when the result came from memory, not a live run


# ── Memory endpoint schemas ────────────────────────────────────

class PreferencesUpdate(BaseModel):
    """Body for POST /memory/preferences"""
    max_steps:            Optional[int]   = None
    summarize_by_default: Optional[bool]  = None
    cache_ttl_hours:      Optional[float] = None
    preferred_currency:   Optional[str]   = None
    preferred_sites:      Optional[list]  = None
    default_session:      Optional[str]   = None


# ── Phase 6: Multi-site comparison ────────────────────────────

class CompareRequest(BaseModel):
    """Search the same query across multiple sites in parallel."""
    query: str
    """What to search for, e.g. "gaming laptops under 80000"."""

    sites: list[str] = ["amazon.in", "flipkart.com"]
    """Which sites to compare. Passed to the agent as part of its goal."""

    max_steps: int = 12
    """Steps per site. Lower than /run default because each site is one focused task."""

    summarize: bool = True
    """Run cross-site AI comparison after extracting from all sites."""


class SiteResult(BaseModel):
    """Extraction result for one site."""
    success: bool
    items: list = []
    total: int = 0
    steps_taken: int = 0
    error: Optional[str] = None


class CompareResponse(BaseModel):
    """What /compare returns."""
    success: bool
    query: str
    sites: list[str]
    results: dict[str, SiteResult]
    """Per-site extraction results, keyed by site name."""

    comparison: Optional[dict] = None
    """Cross-site AI analysis: price_winner, rating_winner, recommendation, etc.
    Only present when summarize=True and at least two sites succeeded."""
