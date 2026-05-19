"""
Base storage utilities — read/write JSON files to disk.

All three memory layers (sessions, results, preferences) store their
data as JSON files. This module provides the shared plumbing so each
layer doesn't repeat the same open/json.load/except boilerplate.

Why JSON files and not a database?
  - Zero dependencies (no SQLite setup, no Redis, no migrations)
  - Human-readable — you can inspect/edit memory in a text editor
  - Sufficient for an agent that runs tens of tasks per day, not thousands

The base_dir defaults to "memory/" relative to the project root.
Each layer gets its own subdirectory: sessions/, results/.
Preferences live at the top level as preferences.json.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any


class MemoryStore:
    """Shared JSON-on-disk storage for all memory layers."""

    def __init__(self, base_dir: str = "memory"):
        self.base = Path(base_dir)
        self.base.mkdir(exist_ok=True)

    def read(self, *path_parts: str) -> dict:
        """
        Read a JSON file. Returns {} if the file doesn't exist.

        Using *path_parts lets callers write:
            store.read("sessions", "amazon_in.json")
        instead of building the path themselves.
        """
        path = self.base.joinpath(*path_parts)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def write(self, data: Any, *path_parts: str) -> None:
        """
        Write data as JSON. Creates parent directories if needed.

        indent=2 keeps files human-readable.
        ensure_ascii=False preserves ₹, ¥, etc. in extracted prices.
        """
        path = self.base.joinpath(*path_parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def delete(self, *path_parts: str) -> bool:
        """Delete a file. Returns True if it existed, False if it didn't."""
        path = self.base.joinpath(*path_parts)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_files(self, subdir: str) -> list[Path]:
        """List all JSON files in a subdirectory."""
        d = self.base / subdir
        if not d.exists():
            return []
        return sorted(d.glob("*.json"))

    @staticmethod
    def now_iso() -> str:
        """Current UTC time as ISO 8601 string — used as 'saved_at' timestamps."""
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def age_hours(saved_at_iso: str) -> float:
        """How many hours ago was this timestamp? Used for TTL checks."""
        try:
            saved = datetime.fromisoformat(saved_at_iso)
            delta = datetime.now(timezone.utc) - saved
            return delta.total_seconds() / 3600
        except (ValueError, TypeError):
            return float("inf")  # unparseable = treat as infinitely old
