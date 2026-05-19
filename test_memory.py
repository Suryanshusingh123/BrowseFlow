"""
Memory system tests — all three layers: sessions, results, preferences.

These tests are entirely offline — no browser, no AI, no network.
We test the storage logic directly: read/write/TTL/normalization/cleanup.

Run: python test_memory.py
"""

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# ── shared helpers ────────────────────────────────────────────

PASS = 0
FAIL = 0

def ok(msg):
    global PASS
    PASS += 1
    print(f"  ✓ {msg}")

def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  ✗ {msg}")

def section(title):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")

def make_store(tmp_dir):
    """Create a MemoryStore rooted in a throwaway temp directory."""
    from memory.store import MemoryStore
    return MemoryStore(base_dir=tmp_dir)


# ══════════════════════════════════════════════════════════════
# 1. MemoryStore — base JSON utilities
# ══════════════════════════════════════════════════════════════

def test_store():
    section("1. MemoryStore — read/write/delete/age")

    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(tmp)

        # ── write + read round-trip ──
        data = {"items": [{"title": "Laptop", "price": "₹85,000"}], "total": 1}
        store.write(data, "test.json")
        read_back = store.read("test.json")
        if read_back == data:
            ok("write → read round-trip preserves data exactly")
        else:
            fail(f"Round-trip mismatch: {read_back}")

        # ── missing file returns {} ──
        missing = store.read("does_not_exist.json")
        if missing == {}:
            ok("Missing file returns empty dict (no exception)")
        else:
            fail(f"Expected {{}}, got {missing!r}")

        # ── nested path creation ──
        store.write({"x": 1}, "subdir", "nested.json")
        nested = store.read("subdir", "nested.json")
        if nested == {"x": 1}:
            ok("Nested subdirectory created automatically")
        else:
            fail(f"Nested write failed: {nested}")

        # ── delete ──
        store.write({"temp": True}, "delete_me.json")
        existed = store.delete("delete_me.json")
        gone = store.read("delete_me.json")
        if existed and gone == {}:
            ok("delete() returns True and file is gone")
        else:
            fail(f"delete() failed: existed={existed}, gone={gone}")

        # ── delete non-existent ──
        result = store.delete("ghost.json")
        if result is False:
            ok("delete() returns False for non-existent file")
        else:
            fail(f"Expected False, got {result!r}")

        # ── age_hours ──
        now_iso = store.now_iso()
        age = store.age_hours(now_iso)
        if 0.0 <= age < 0.01:  # just created — should be ~0
            ok(f"age_hours(just now) ≈ 0 ({age:.4f}h)")
        else:
            fail(f"age_hours(just now) expected ~0, got {age}")

        # ── age_hours on garbage string ──
        age_bad = store.age_hours("not-a-date")
        if age_bad == float("inf"):
            ok("age_hours(invalid) returns inf (safely treated as maximally old)")
        else:
            fail(f"Expected inf, got {age_bad}")

        # ── list_files ──
        store.write({}, "results", "a.json")
        store.write({}, "results", "b.json")
        files = store.list_files("results")
        names = [f.name for f in files]
        if "a.json" in names and "b.json" in names:
            ok(f"list_files returns all files in subdirectory ({len(files)} found)")
        else:
            fail(f"list_files returned {names}")


# ══════════════════════════════════════════════════════════════
# 2. SessionMemory
# ══════════════════════════════════════════════════════════════

def test_sessions():
    section("2. SessionMemory — domain keys, has(), list, delete")

    with tempfile.TemporaryDirectory() as tmp:
        from memory.sessions import SessionMemory
        store = make_store(tmp)
        sessions = SessionMemory(store)

        # ── domain key normalisation ──
        cases = [
            ("amazon.in",                  "amazon_in"),
            ("www.flipkart.com",            "www_flipkart_com"),
            ("https://amazon.in/products", "amazon_in"),
            ("https://shop.example.com/",  "shop_example_com"),
        ]
        all_ok = True
        for input_val, expected_key in cases:
            got = sessions._domain_key(input_val)
            if got != expected_key:
                fail(f"_domain_key({input_val!r}): expected {expected_key!r}, got {got!r}")
                all_ok = False
        if all_ok:
            ok(f"All {len(cases)} domain key normalizations correct")

        # ── has() returns False before any session saved ──
        if not sessions.has("amazon.in"):
            ok("has('amazon.in') = False before saving")
        else:
            fail("has() should return False for unsaved domain")

        # ── get_path() returns None before saving ──
        path = sessions.get_path("amazon.in")
        if path is None:
            ok("get_path() returns None when no session exists")
        else:
            fail(f"Expected None, got {path!r}")

        # ── save() via mock Playwright context ──
        # We don't need a real browser — just mock context.storage_state()
        # to write a fake state file. That's all save() needs from Playwright.
        mock_ctx = AsyncMock()
        async def fake_storage_state(path):
            import json
            fake_state = {
                "cookies": [
                    {"name": "session_id", "value": "abc123", "domain": "amazon.in"},
                    {"name": "csrf_token", "value": "xyz789", "domain": "amazon.in"},
                ],
                "origins": [
                    {"origin": "https://amazon.in", "localStorage": [{"name": "user", "value": "test"}]}
                ]
            }
            Path(path).write_text(json.dumps(fake_state))
        mock_ctx.storage_state = fake_storage_state

        asyncio.run(sessions.save(mock_ctx, "amazon.in"))

        # ── has() returns True after save ──
        if sessions.has("amazon.in"):
            ok("has('amazon.in') = True after save()")
        else:
            fail("has() should return True after save()")

        # ── get_path() returns a valid path after save ──
        path = sessions.get_path("amazon.in")
        if path and Path(path).exists():
            ok(f"get_path() returns valid path: {Path(path).name}")
        else:
            fail(f"get_path() should return existing path, got {path!r}")

        # ── saved file has our metadata ──
        import json
        saved = json.loads(Path(path).read_text())
        meta = saved.get("_meta", {})
        if meta.get("domain") == "amazon.in" and meta.get("cookie_count") == 2:
            ok(f"Saved file has metadata (domain={meta['domain']}, cookies={meta['cookie_count']})")
        else:
            fail(f"Metadata missing or wrong: {meta}")

        # ── list_all() ──
        listings = sessions.list_all()
        if len(listings) == 1 and listings[0]["domain"] == "amazon.in":
            ok("list_all() returns saved session with correct domain")
        else:
            fail(f"list_all() returned: {listings}")

        # ── delete() ──
        existed = sessions.delete("amazon.in")
        if existed and not sessions.has("amazon.in"):
            ok("delete() removes session and has() returns False")
        else:
            fail(f"delete() failed: existed={existed}, has={sessions.has('amazon.in')}")

        # ── delete() on nonexistent ──
        result = sessions.delete("ghost.com")
        if result is False:
            ok("delete() returns False for unknown domain")
        else:
            fail(f"Expected False, got {result!r}")


# ══════════════════════════════════════════════════════════════
# 3. ResultsMemory
# ══════════════════════════════════════════════════════════════

def test_results():
    section("3. ResultsMemory — save, get, TTL, normalization, cleanup")

    with tempfile.TemporaryDirectory() as tmp:
        from memory.results import ResultsMemory
        store = make_store(tmp)
        results = ResultsMemory(store)

        fake_result = {
            "items": [
                {"title": "ASUS ROG", "price": {"amount": 89999, "currency": "INR"}},
                {"title": "Lenovo LOQ", "price": {"amount": 75990, "currency": "INR"}},
            ],
            "total": 2,
        }
        goal = "Search Amazon for gaming laptops under ₹1 lakh"

        # ── get() returns None before any save ──
        hit = results.get(goal)
        if hit is None:
            ok("get() returns None before saving")
        else:
            fail(f"Expected None, got {hit!r}")

        # ── save then get ──
        results.save(goal, fake_result)
        hit = results.get(goal, max_age_hours=1.0)
        if hit == fake_result:
            ok("save → get round-trip returns exact result")
        else:
            fail(f"Round-trip mismatch: got {hit!r}")

        # ── goal normalization — same goal, different casing/spacing ──
        variants = [
            "search amazon for gaming laptops under ₹1 lakh",          # lowercase
            "SEARCH AMAZON FOR GAMING LAPTOPS UNDER ₹1 LAKH",          # uppercase
            "  Search Amazon   for gaming laptops  under ₹1 lakh  ",   # extra spaces
        ]
        all_match = True
        for variant in variants:
            hit = results.get(variant, max_age_hours=1.0)
            if hit != fake_result:
                fail(f"Variant {variant!r} should hit cache, got: {hit!r}")
                all_match = False
        if all_match:
            ok(f"Goal normalization: {len(variants)} variants all hit the same cache entry")

        # ── TTL: expired result returns None ──
        # Trick: manually set saved_at to 2 hours ago
        import json
        from datetime import datetime, timezone, timedelta
        key = results._goal_key(goal)
        path = Path(tmp) / "results" / f"{key}.json"
        data = json.loads(path.read_text())
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        data["saved_at"] = old_time
        path.write_text(json.dumps(data))

        expired = results.get(goal, max_age_hours=1.0)
        if expired is None:
            ok("TTL: result saved 2h ago is not returned with max_age_hours=1.0")
        else:
            fail("TTL check failed — stale result was returned")

        # ── same stale result IS returned with a longer TTL ──
        still_valid = results.get(goal, max_age_hours=24.0)
        if still_valid == fake_result:
            ok("Same stale result IS returned with max_age_hours=24.0")
        else:
            fail("Expected stale result with generous TTL")

        # ── delete() ──
        existed = results.delete(goal)
        if existed and results.get(goal, max_age_hours=999) is None:
            ok("delete() removes result from cache")
        else:
            fail("delete() failed to remove result")

        # ── list_all() ──
        results.save("goal one", {"items": [], "total": 0})
        results.save("goal two", {"items": [{"title": "x"}], "total": 1})
        listing = results.list_all()
        if len(listing) == 2:
            ok(f"list_all() returns {len(listing)} entries")
        else:
            fail(f"Expected 2 entries, got {len(listing)}: {listing}")

        # check listing shape
        entry = listing[0]
        required_keys = {"goal", "saved_at", "item_count", "age_hours", "key"}
        if required_keys.issubset(entry.keys()):
            ok(f"list_all() entries have all required fields: {required_keys}")
        else:
            fail(f"Missing keys in listing entry: {entry.keys()}")

        # ── clear_stale() ──
        # Make one entry old
        for f in Path(tmp).glob("results/*.json"):
            data = json.loads(f.read_text())
            old_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
            data["saved_at"] = old_time
            f.write_text(json.dumps(data))
            break  # only age one file

        deleted = results.clear_stale(max_age_hours=3.0)
        if deleted == 1:
            ok("clear_stale() deleted exactly the 1 file older than 3 hours")
        else:
            fail(f"clear_stale() deleted {deleted} files (expected 1)")


# ══════════════════════════════════════════════════════════════
# 4. PreferencesMemory
# ══════════════════════════════════════════════════════════════

def test_preferences():
    section("4. PreferencesMemory — get, set, defaults, reset")

    with tempfile.TemporaryDirectory() as tmp:
        from memory.preferences import PreferencesMemory, DEFAULTS
        store = make_store(tmp)
        prefs = PreferencesMemory(store)

        # ── get before any set returns default ──
        default_max = prefs.get("max_steps")
        if default_max == DEFAULTS["max_steps"]:
            ok(f"get('max_steps') before set returns default ({DEFAULTS['max_steps']})")
        else:
            fail(f"Expected {DEFAULTS['max_steps']}, got {default_max}")

        # ── unknown key returns default arg ──
        val = prefs.get("nonexistent_key", default="fallback")
        if val == "fallback":
            ok("get(unknown_key, default='fallback') returns fallback")
        else:
            fail(f"Expected 'fallback', got {val!r}")

        # ── set + get ──
        prefs.set("max_steps", 25)
        got = prefs.get("max_steps")
        if got == 25:
            ok("set('max_steps', 25) → get returns 25")
        else:
            fail(f"Expected 25, got {got!r}")

        # ── set persists across new instances (same store) ──
        prefs2 = PreferencesMemory(store)
        got2 = prefs2.get("max_steps")
        if got2 == 25:
            ok("Preferences persist across instances (loaded from disk)")
        else:
            fail(f"Persistence failed: new instance returned {got2!r}")

        # ── set_many ──
        prefs.set_many({"summarize_by_default": True, "cache_ttl_hours": 2.5})
        if prefs.get("summarize_by_default") is True and prefs.get("cache_ttl_hours") == 2.5:
            ok("set_many() updates multiple keys atomically")
        else:
            fail("set_many() failed")

        # ── get_all merges defaults ──
        all_prefs = prefs.get_all()
        for key, default_val in DEFAULTS.items():
            if key not in all_prefs:
                fail(f"get_all() missing key: {key!r}")
                break
        else:
            ok(f"get_all() contains all {len(DEFAULTS)} default keys")

        # stored value takes precedence in get_all
        if all_prefs["max_steps"] == 25:
            ok("get_all() stored value (25) beats default (15) for max_steps")
        else:
            fail(f"get_all() max_steps should be 25, got {all_prefs['max_steps']}")

        # ── reset single key ──
        prefs.reset("max_steps")
        restored = prefs.get("max_steps")
        if restored == DEFAULTS["max_steps"]:
            ok(f"reset('max_steps') restores default ({DEFAULTS['max_steps']})")
        else:
            fail(f"reset() failed: got {restored!r}")

        # ── reset all ──
        prefs.set("summarize_by_default", True)
        prefs.set("cache_ttl_hours", 5.0)
        prefs.reset()  # wipe everything
        all_after = prefs.get_all()
        if all_after == DEFAULTS:
            ok("reset() with no args restores all defaults")
        else:
            fail(f"After reset(), expected DEFAULTS, got {all_after}")


# ══════════════════════════════════════════════════════════════
# 5. AgentMemory — composed facade + singleton
# ══════════════════════════════════════════════════════════════

def test_agent_memory_facade():
    section("5. AgentMemory — composed facade")

    with tempfile.TemporaryDirectory() as tmp:
        from memory.agent_memory import AgentMemory
        mem = AgentMemory(base_dir=tmp)

        # All three layers accessible
        if hasattr(mem, "sessions") and hasattr(mem, "results") and hasattr(mem, "preferences"):
            ok("AgentMemory exposes .sessions, .results, .preferences")
        else:
            fail("AgentMemory missing layer(s)")

        # Layers are distinct objects
        if mem.sessions is not mem.results:
            ok("sessions and results are different objects (no cross-contamination)")
        else:
            fail("sessions and results are the same object — bug!")

        # Singleton import works
        from memory.agent_memory import agent_memory
        if agent_memory is not None:
            ok("Global singleton 'agent_memory' importable")
        else:
            fail("agent_memory singleton is None")

        # repr doesn't crash
        try:
            r = repr(mem)
            if "AgentMemory" in r:
                ok(f"repr() works: {r}")
            else:
                fail(f"Unexpected repr: {r!r}")
        except Exception as e:
            fail(f"repr() raised: {e}")


# ══════════════════════════════════════════════════════════════
# 6. Integration — preferences act as request defaults
# ══════════════════════════════════════════════════════════════

def test_preference_as_request_default():
    """
    Simulate the logic in main.py: preferences fill in when the
    request uses the schema default value.
    """
    section("6. Integration — preferences fill in request defaults")

    with tempfile.TemporaryDirectory() as tmp:
        from memory.agent_memory import AgentMemory
        mem = AgentMemory(base_dir=tmp)
        prefs = mem.preferences

        # User sets preferences
        prefs.set_many({
            "max_steps": 30,
            "summarize_by_default": True,
            "cache_ttl_hours": 0.5,
        })

        # Simulate main.py preference resolution
        # Request with all defaults (user didn't specify anything)
        req_max_steps      = 15     # schema default
        req_summarize      = False  # schema default
        req_cache_ttl      = 1.0    # schema default

        # main.py logic
        effective_max_steps = req_max_steps if req_max_steps != 15 else prefs.get("max_steps", 15)
        effective_summarize = req_summarize or prefs.get("summarize_by_default", False)
        effective_ttl       = req_cache_ttl if req_cache_ttl != 1.0 else prefs.get("cache_ttl_hours", 1.0)

        if effective_max_steps == 30:
            ok("max_steps: preference (30) used when request has schema default (15)")
        else:
            fail(f"max_steps: expected 30 from preference, got {effective_max_steps}")

        if effective_summarize is True:
            ok("summarize: preference (True) used when request is False (schema default)")
        else:
            fail("summarize_by_default preference not applied")

        if effective_ttl == 0.5:
            ok("cache_ttl_hours: preference (0.5) used when request has schema default (1.0)")
        else:
            fail(f"cache_ttl_hours: expected 0.5 from preference, got {effective_ttl}")

        # Now simulate a request that EXPLICITLY overrides preferences
        req_max_steps_explicit = 5   # user explicitly asked for 5 steps
        effective_explicit = req_max_steps_explicit if req_max_steps_explicit != 15 else prefs.get("max_steps", 15)
        if effective_explicit == 5:
            ok("Explicit request value (5) wins over preference (30)")
        else:
            fail(f"Request should override preference, got {effective_explicit}")


# ══════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "═" * 55)
    print("  Memory System — Test Suite")
    print("═" * 55)

    test_store()
    test_sessions()
    test_results()
    test_preferences()
    test_agent_memory_facade()
    test_preference_as_request_default()

    total = PASS + FAIL
    print("\n" + "═" * 55)
    if FAIL == 0:
        print(f"  ✓ All {total} checks passed — memory system is solid")
    else:
        print(f"  Results: {PASS}/{total} passed   {FAIL} FAILED")
    print("═" * 55 + "\n")
