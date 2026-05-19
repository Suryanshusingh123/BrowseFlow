"""
Results Memory — cache extracted data with time-to-live.

WHY CACHE RESULTS?
  Browser + AI extraction is slow (5–30 seconds per run).
  If the user asks "search Amazon for gaming laptops" twice in an hour,
  the second call should return immediately — no browser, no AI calls.

  The cache saves the full structured output (items + metadata) so the
  response is identical to a live run.

HOW WE MATCH GOALS:
  We can't do an exact string match — "Search Amazon for gaming laptops"
  and "search amazon for gaming laptops" are the same intent.

  Solution:
    1. Normalize: lowercase + collapse whitespace
    2. SHA-256 hash the normalized string
    3. Use the first 16 hex chars as the key (2^64 space — no collisions in practice)

  Result files: memory/results/{16-char-hash}.json

WHAT'S STORED:
  {
    "goal":     "search amazon for gaming laptops",   ← original (for display)
    "saved_at": "2025-01-15T10:30:00+00:00",
    "result":   { ... }                               ← exactly what the agent returned
  }

TTL:
  Default 1 hour. Configurable per-request with cache_ttl_hours.
  After TTL, the file stays on disk but get() returns None,
  triggering a fresh run. Old files are only cleaned up by clear_stale().
"""

import hashlib
from memory.store import MemoryStore


class ResultsMemory:
    """Cache agent extraction results keyed by (normalized) goal string."""

    def __init__(self, store: MemoryStore):
        self._store = store
        (store.base / "results").mkdir(exist_ok=True)

    # ── Public API ────────────────────────────────────────────

    def get(self, goal: str, max_age_hours: float = 1.0) -> dict | None:
        """
        Return cached result if it exists and is fresh. Otherwise None.

        Args:
            goal:          The natural language task (same as AgentRequest.goal)
            max_age_hours: How old a cached result can be before we ignore it

        Returns:
            The cached result dict, or None if not found / too old.
        """
        key = self._goal_key(goal)
        data = self._store.read("results", f"{key}.json")

        if not data:
            return None  # never cached

        age = self._store.age_hours(data.get("saved_at", ""))
        if age > max_age_hours:
            print(f"[Memory] Cache miss for goal (age={age:.1f}h > TTL={max_age_hours}h)")
            return None

        print(f"[Memory] Cache hit! Returning results from {age:.1f}h ago (TTL={max_age_hours}h)")
        return data["result"]

    def save(self, goal: str, result: dict) -> None:
        """
        Save an agent result to cache.

        Called after a successful agent run so the next identical
        (or normalized-identical) goal can skip the browser entirely.
        """
        key = self._goal_key(goal)
        data = {
            "goal":     goal,
            "saved_at": self._store.now_iso(),
            "result":   result,
        }
        self._store.write(data, "results", f"{key}.json")
        item_count = len(result.get("items", []))
        print(f"[Memory] Cached result for goal ({item_count} items, key={key})")

    def delete(self, goal: str) -> bool:
        """Manually invalidate a cached result. Returns True if it existed."""
        key = self._goal_key(goal)
        return self._store.delete("results", f"{key}.json")

    def list_all(self) -> list[dict]:
        """
        List all cached results with metadata.

        Returns:
          [{"goal": "...", "saved_at": "...", "item_count": 5, "age_hours": 0.3}, ...]
        """
        entries = []
        for path in self._store.list_files("results"):
            data = self._store.read("results", path.name)
            if not data:
                continue
            result = data.get("result", {})
            entries.append({
                "goal":       data.get("goal", "unknown"),
                "saved_at":   data.get("saved_at", "unknown"),
                "item_count": len(result.get("items", [])),
                "age_hours":  round(self._store.age_hours(data.get("saved_at", "")), 2),
                "key":        path.stem,
            })
        return sorted(entries, key=lambda x: x["saved_at"], reverse=True)

    def clear_stale(self, max_age_hours: float = 24.0) -> int:
        """
        Delete cached results older than max_age_hours.

        Returns the number of files deleted.
        Useful to run periodically to prevent unbounded disk growth.
        """
        deleted = 0
        for path in self._store.list_files("results"):
            data = self._store.read("results", path.name)
            age = self._store.age_hours(data.get("saved_at", ""))
            if age > max_age_hours:
                self._store.delete("results", path.name)
                deleted += 1
        if deleted:
            print(f"[Memory] Cleared {deleted} stale result(s) older than {max_age_hours}h")
        return deleted

    # ── Internal helpers ──────────────────────────────────────

    @staticmethod
    def _goal_key(goal: str) -> str:
        """
        Normalize goal → stable 16-char hex key.

        "Search Amazon for GAMING laptops"
        "search amazon for gaming laptops"
        "  search  amazon  for  gaming  laptops  "

        All three produce the same key.
        """
        normalized = " ".join(goal.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
