"""
Preferences Memory — persistent user settings that act as request defaults.

PREFERENCES VS REQUEST FIELDS:
  Every preference has a corresponding request field that overrides it.
  Preferences fill in when the request doesn't specify a value.

  Example:
    preferences: {"max_steps": 20, "summarize_by_default": true}
    request: {"goal": "...", "max_steps": null, "summarize": null}

    Effective values:
      max_steps → 20   (from preferences, request was null)
      summarize → true  (from preferences, request was null)

  If the request explicitly says max_steps=10, preferences are ignored.
  The request always wins — preferences are defaults, not overrides.

AVAILABLE PREFERENCES:
  max_steps           int     Max agent loop steps (default: 15)
  summarize_by_default bool    Always run AI summarization (default: false)
  cache_ttl_hours     float   How long to trust cached results (default: 1.0)
  preferred_currency  str     Normalize prices to this currency, e.g. "INR" (default: null)
  preferred_sites     list    Hint: prefer these domains for searches (default: [])
  default_session     str     Auto-load session for this domain if no session specified (default: null)

Storage: memory/preferences.json (a flat JSON dict, no nesting needed)
"""

from typing import Any
from memory.store import MemoryStore


# Default values for every known preference key.
# Used when the preference hasn't been set yet.
DEFAULTS: dict[str, Any] = {
    "max_steps":            15,
    "summarize_by_default": False,
    "cache_ttl_hours":      1.0,
    "preferred_currency":   None,
    "preferred_sites":      [],
    "default_session":      None,
}


class PreferencesMemory:
    """Persistent key-value store for user preferences."""

    def __init__(self, store: MemoryStore):
        self._store = store
        self._file = "preferences.json"

    # ── Public API ────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a preference value.

        Lookup order:
          1. Stored value (set by user)
          2. DEFAULTS dict
          3. The `default` argument (fallback of last resort)
        """
        prefs = self._store.read(self._file)
        if key in prefs:
            return prefs[key]
        return DEFAULTS.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set a preference. Persists immediately to disk.

        We load → update → save on every write to avoid
        losing other keys. This is fine at human-interaction
        frequency (not called in a tight loop).
        """
        prefs = self._store.read(self._file)
        prefs[key] = value
        self._store.write(prefs, self._file)
        print(f"[Memory] Preference set: {key} = {value!r}")

    def set_many(self, updates: dict[str, Any]) -> None:
        """Set multiple preferences atomically (single disk write)."""
        prefs = self._store.read(self._file)
        prefs.update(updates)
        self._store.write(prefs, self._file)
        print(f"[Memory] Preferences updated: {list(updates.keys())}")

    def get_all(self) -> dict[str, Any]:
        """
        Return all preferences merged with defaults.

        Stored values take precedence over defaults.
        Unknown stored keys are included as-is (forward compat).
        """
        stored = self._store.read(self._file)
        # Start with defaults, overlay stored values
        return {**DEFAULTS, **stored}

    def reset(self, key: str | None = None) -> None:
        """
        Reset a single key (or ALL preferences) to defaults.

        reset("max_steps")  → only max_steps reverts to 15
        reset()             → full wipe back to factory defaults
        """
        if key is None:
            self._store.write({}, self._file)
            print("[Memory] All preferences reset to defaults")
        else:
            prefs = self._store.read(self._file)
            prefs.pop(key, None)
            self._store.write(prefs, self._file)
            print(f"[Memory] Preference '{key}' reset to default ({DEFAULTS.get(key)!r})")
