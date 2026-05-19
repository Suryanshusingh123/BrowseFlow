"""
Session Memory — persist browser login state across agent runs.

The core mechanism is Playwright's built-in storage_state API:

  SAVING:
    await context.storage_state(path="memory/sessions/amazon_in.json")

  LOADING:
    context = await browser.new_context(storage_state="memory/sessions/amazon_in.json")

A storage_state file contains:
  - cookies: all cookies the browser set (session tokens, CSRF tokens, etc.)
  - origins: localStorage and sessionStorage per origin

This means: if the agent logs in to amazon.in and we save the session,
the next run starts with the browser already authenticated.
No re-login needed.

IMPORTANT: sessions can expire server-side even if we hold the cookies.
We don't control that — if a session is expired, the agent will be
redirected to the login page and can re-authenticate.

Domain key format: "amazon.in" → "amazon_in"
  - dots replaced with underscores (dots are special in some filesystems)
  - lowercased
  - stored at memory/sessions/amazon_in.json
"""

import re
from pathlib import Path
from urllib.parse import urlparse
from memory.store import MemoryStore


class SessionMemory:
    """Stores and retrieves Playwright browser session state per domain."""

    def __init__(self, store: MemoryStore):
        self._store = store
        # Ensure the sessions subdirectory exists
        (store.base / "sessions").mkdir(exist_ok=True)

    # ── Public API ────────────────────────────────────────────

    def has(self, domain: str) -> bool:
        """True if we have a saved session for this domain."""
        key = self._domain_key(domain)
        return (self._store.base / "sessions" / f"{key}.json").exists()

    def get_path(self, domain: str) -> str | None:
        """
        Return the filesystem path to the session file, or None if it doesn't exist.

        This path is passed directly to Playwright's new_context(storage_state=...).
        Playwright wants a string path or a dict — we use a path so Playwright
        reads the file directly, keeping the dict out of Python memory.
        """
        key = self._domain_key(domain)
        path = self._store.base / "sessions" / f"{key}.json"
        return str(path) if path.exists() else None

    async def save(self, context, domain: str) -> str:
        """
        Dump a Playwright BrowserContext's full cookie+localStorage state to disk.

        Must be called BEFORE the context is closed — once closed, the state
        is gone. In browser/engine.py we call this in the finally block, just
        before context.close().

        Returns the path where the session was saved (for logging).
        """
        key = self._domain_key(domain)
        path = self._store.base / "sessions" / f"{key}.json"

        # Playwright writes the file itself — we just tell it where
        await context.storage_state(path=str(path))

        # Add our own metadata on top (cookie count, save time)
        # We do this AFTER Playwright writes so we can count what it saved
        import json
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["_meta"] = {
            "domain": domain,
            "saved_at": self._store.now_iso(),
            "cookie_count": len(raw.get("cookies", [])),
        }
        path.write_text(
            json.dumps(raw, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(f"[Memory] Session saved for '{domain}' ({raw['_meta']['cookie_count']} cookies)")
        return str(path)

    def delete(self, domain: str) -> bool:
        """Delete a saved session. Returns True if it existed."""
        key = self._domain_key(domain)
        existed = self._store.delete("sessions", f"{key}.json")
        if existed:
            print(f"[Memory] Session deleted for '{domain}'")
        return existed

    def list_all(self) -> list[dict]:
        """
        List all saved sessions with metadata.

        Returns a list of dicts:
          [{"domain": "amazon.in", "saved_at": "...", "cookie_count": 12}, ...]
        """
        sessions = []
        for path in self._store.list_files("sessions"):
            data = self._store.read("sessions", path.name)
            meta = data.get("_meta", {})
            if not meta:
                # Old file without metadata — derive domain from filename
                meta = {
                    "domain": path.stem.replace("_", "."),
                    "saved_at": "unknown",
                    "cookie_count": len(data.get("cookies", [])),
                }
            sessions.append(meta)
        return sessions

    # ── Internal helpers ──────────────────────────────────────

    @staticmethod
    def _domain_key(domain_or_url: str) -> str:
        """
        Convert a domain or URL to a safe filename key.

        "amazon.in"                → "amazon_in"
        "https://amazon.in/search" → "amazon_in"
        "www.flipkart.com"         → "www_flipkart_com"
        """
        # Strip URL scheme and path if a full URL was passed
        s = domain_or_url.strip()
        if s.startswith("http"):
            s = urlparse(s).netloc
        # Replace any non-alphanumeric character with underscore
        return re.sub(r"[^\w]", "_", s.lower()).strip("_")
