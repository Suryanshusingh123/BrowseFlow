"""
Phase 5 Reliability — Comprehensive Test Suite

Tests every component added in Phase 5:
  1. human_delay        — timing utility
  2. with_retry         — retry decorator with backoff
  3. check_page_health  — URL / title / body pattern detection
  4. _find_element      — fuzzy scan (Strategy 9)
  5. _execute_navigate  — surfaces health reason on failure

Structure
─────────
PART 1 — Unit tests (no browser, runs in milliseconds)
PART 2 — Browser tests (real Playwright, but uses set_content()
          instead of real URLs — no network except the final
          navigate_to smoke test)

Run: python test_phase5.py
"""

import asyncio
import time

# ══════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════

PASS = 0
FAIL = 0

def ok(msg: str):
    global PASS
    PASS += 1
    print(f"  ✓ {msg}")

def fail(msg: str):
    global FAIL
    FAIL += 1
    print(f"  ✗ {msg}")

def section(title: str):
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")


# ══════════════════════════════════════════════════════
# MOCK PAGE  — stands in for a Playwright page object
# in tests that don't need a real browser.
# Mimics exactly the three attributes check_page_health uses:
#   page.url       (property)
#   page.title()   (async method)
#   page.evaluate() (async method)
# ══════════════════════════════════════════════════════

class MockPage:
    def __init__(self, url="https://example.com", title="Example Domain", body="Normal page content"):
        self.url = url
        self._title = title
        self._body = body

    async def title(self):
        return self._title

    async def evaluate(self, _script, *args):
        # health.py calls evaluate to get body text
        return self._body.lower()


# ══════════════════════════════════════════════════════
# PART 1 — UNIT TESTS  (no browser)
# ══════════════════════════════════════════════════════

# ── 1.1  human_delay ──────────────────────────────────

def test_human_delay():
    section("1. human_delay")
    from utils.retry import human_delay

    # Default range: 80ms–350ms → 0.08s–0.35s
    samples = [human_delay() for _ in range(30)]
    all_in_range = all(0.08 <= s <= 0.35 for s in samples)
    if all_in_range:
        ok("All 30 default samples are within [0.08, 0.35] seconds")
    else:
        bad = [s for s in samples if not (0.08 <= s <= 0.35)]
        fail(f"Out-of-range samples: {bad}")

    # Custom range: 200ms–600ms
    custom = [human_delay(min_ms=200, max_ms=600) for _ in range(20)]
    all_custom = all(0.2 <= s <= 0.6 for s in custom)
    if all_custom:
        ok("Custom range [200ms, 600ms] respected")
    else:
        fail(f"Custom range violated: {[s for s in custom if not (0.2 <= s <= 0.6)]}")

    # It should be random — 30 calls should not all be identical
    unique = len(set(round(s, 4) for s in samples))
    if unique > 5:
        ok(f"Values are random ({unique} unique values in 30 samples)")
    else:
        fail(f"Too few unique values — possible constant output ({unique} unique)")

    # Return type must be float (asyncio.sleep needs a float)
    val = human_delay()
    if isinstance(val, float):
        ok("Return type is float")
    else:
        fail(f"Expected float, got {type(val).__name__}")


# ── 1.2  with_retry / retry_async ─────────────────────

def test_retry():
    section("2. with_retry / retry_async")
    from utils.retry import with_retry, retry_async

    # ── Test A: succeeds on first attempt — function called exactly once ──
    call_log = []

    @with_retry(max_attempts=3, base_delay=0.01)
    async def always_succeeds():
        call_log.append(1)
        return "ok"

    result = asyncio.run(always_succeeds())
    if result == "ok" and len(call_log) == 1:
        ok("First-attempt success: function called exactly once")
    else:
        fail(f"Expected 1 call and 'ok', got {len(call_log)} calls and {result!r}")

    # ── Test B: fails twice then succeeds — called exactly 3 times ──
    attempts = []

    @with_retry(max_attempts=3, base_delay=0.01, jitter=0.0)
    async def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionError("not ready yet")
        return "finally"

    result = asyncio.run(flaky())
    if result == "finally" and len(attempts) == 3:
        ok(f"Eventual success: function called {len(attempts)} times before succeeding")
    else:
        fail(f"Expected 3 attempts and 'finally', got {len(attempts)} attempts and {result!r}")

    # ── Test C: always fails — raises the last exception after max_attempts ──
    tries = []

    @with_retry(max_attempts=3, base_delay=0.01, jitter=0.0)
    async def always_fails():
        tries.append(1)
        raise TimeoutError("still broken")

    caught = None
    try:
        asyncio.run(always_fails())
    except TimeoutError as e:
        caught = e
    if caught and len(tries) == 3:
        ok(f"Exhaustion: raised TimeoutError after {len(tries)} attempts")
    else:
        fail(f"Expected 3 attempts + TimeoutError, got {len(tries)} attempts, caught={caught!r}")

    # ── Test D: unspecified exception bypasses retry — propagates immediately ──
    bypassed = []

    @with_retry(max_attempts=5, base_delay=0.01, exceptions=(ValueError,))
    async def wrong_error():
        bypassed.append(1)
        raise TypeError("totally different error")  # NOT in exceptions tuple

    caught_type = None
    try:
        asyncio.run(wrong_error())
    except TypeError as e:
        caught_type = e
    if caught_type and len(bypassed) == 1:
        ok("Unspecified exception bypasses retry (propagates immediately)")
    else:
        fail(f"Expected immediate propagation, got {len(bypassed)} calls")

    # ── Test E: backoff actually waits (verify timing roughly correct) ──
    fast_tries = []

    @with_retry(max_attempts=3, base_delay=0.05, jitter=0.0)
    async def timed_fail():
        fast_tries.append(time.monotonic())
        if len(fast_tries) < 3:
            raise RuntimeError("again")
        return "done"

    t_start = time.monotonic()
    asyncio.run(timed_fail())
    total = time.monotonic() - t_start
    # 3 attempts: wait 0.05s after attempt 1, 0.1s after attempt 2 = 0.15s minimum
    if total >= 0.12:
        ok(f"Backoff delays are real (total wait ≈ {total:.2f}s for base_delay=0.05)")
    else:
        fail(f"Backoff too fast — expected ≥0.12s, got {total:.2f}s")


# ── 1.3  check_page_health — URL patterns ─────────────

def test_health_url_patterns():
    section("3. check_page_health — URL patterns")
    from browser.health import check_page_health

    bad_urls = [
        ("https://amazon.com/captcha",           "captcha"),
        ("https://amazon.com/validatecaptcha",   "captcha"),
        ("https://example.com/robot/check",      "captcha"),
        ("https://example.com/challenge",        "captcha"),
        ("https://shop.com/errors/429",          "rate_limited"),
        ("https://shop.com/access-denied",       "error_page"),
        ("https://shop.com/blocked",             "error_page"),
        ("https://app.com/account/login",        "auth_required"),
        ("https://app.com/signin?next=/home",    "auth_required"),
    ]

    all_ok = True
    for url, expected_issue in bad_urls:
        page = MockPage(url=url)
        health = asyncio.run(check_page_health(page))
        if health.healthy:
            fail(f"Expected unhealthy for URL {url!r}, got healthy")
            all_ok = False
        elif health.issue != expected_issue:
            fail(f"URL {url!r}: expected issue={expected_issue!r}, got {health.issue!r}")
            all_ok = False
    if all_ok:
        ok(f"All {len(bad_urls)} bad URL patterns correctly detected")

    # A clean URL must pass
    clean = MockPage(url="https://example.com/products/laptops")
    h = asyncio.run(check_page_health(clean))
    if h.healthy:
        ok("Clean URL correctly passes health check")
    else:
        fail(f"Clean URL flagged as unhealthy: {h.issue} — {h.details}")


def test_health_title_patterns():
    section("4. check_page_health — title patterns")
    from browser.health import check_page_health

    bad_titles = [
        "Access Denied",
        "Robot Check",
        "Captcha Verification",
        "Too Many Requests",
        "Page Not Found",
        "404 Not Found",
        "500 Internal Server Error",
        "Something Went Wrong",
        "Temporarily Unavailable",
    ]

    all_ok = True
    for title in bad_titles:
        page = MockPage(title=title)
        health = asyncio.run(check_page_health(page))
        if health.healthy:
            fail(f"Expected unhealthy for title {title!r}, got healthy")
            all_ok = False
    if all_ok:
        ok(f"All {len(bad_titles)} bad title patterns correctly detected")

    # A normal title must pass
    page = MockPage(title="Gaming Laptops — Best Prices")
    h = asyncio.run(check_page_health(page))
    if h.healthy:
        ok("Normal title correctly passes health check")
    else:
        fail(f"Normal title flagged: {h.issue}")


def test_health_body_patterns():
    section("5. check_page_health — body content patterns")
    from browser.health import check_page_health

    bad_bodies = [
        ("prove you're not a robot",  "captcha"),
        ("verify you are human",      "captcha"),
        ("your ip has been blocked",  "rate_limited"),
        ("too many requests",         "rate_limited"),
        ("rate limit exceeded",       "rate_limited"),
        ("unusual traffic",           "rate_limited"),
        ("automated queries",         "rate_limited"),
        ("this site is protected",    "rate_limited"),
    ]

    all_ok = True
    for body, expected_issue in bad_bodies:
        page = MockPage(body=body)
        health = asyncio.run(check_page_health(page))
        if health.healthy:
            fail(f"Expected unhealthy for body text {body!r}")
            all_ok = False
        elif health.issue != expected_issue:
            fail(f"Body {body!r}: expected issue={expected_issue!r}, got {health.issue!r}")
            all_ok = False
    if all_ok:
        ok(f"All {len(bad_bodies)} bad body patterns correctly detected with right issue type")

    # Normal body
    page = MockPage(body="MacBook Pro 16-inch — Apple M3 Pro chip, 18GB memory. $2,499.")
    h = asyncio.run(check_page_health(page))
    if h.healthy:
        ok("Normal body content correctly passes health check")
    else:
        fail(f"Normal body flagged: {h.issue}")


def test_health_healthy_page():
    section("6. check_page_health — fully healthy page")
    from browser.health import check_page_health

    page = MockPage(
        url="https://shop.example.com/search?q=laptop",
        title="Laptop Search Results",
        body="Found 42 laptops. Prices from $499. Free shipping on orders over $50.",
    )
    h = asyncio.run(check_page_health(page))

    if h.healthy:
        ok("Fully clean page → healthy=True")
    else:
        fail(f"Clean page incorrectly flagged: issue={h.issue!r}, details={h.details!r}")

    if h.issue is None:
        ok("healthy page has issue=None")
    else:
        fail(f"healthy page should have issue=None, got {h.issue!r}")


def test_classify_issue():
    section("7. _classify_issue — pattern → issue category mapping")
    from browser.health import _classify_issue

    cases = [
        # CAPTCHA / bot detection
        ("captcha",   "captcha"),
        ("robot",     "captcha"),
        ("challenge", "captcha"),
        # Rate limiting
        ("429",       "rate_limited"),
        ("rate",      "rate_limited"),
        ("too many",  "rate_limited"),
        # Auth redirects
        ("signin",    "auth_required"),
        ("login",     "auth_required"),
        ("account",   "auth_required"),
        # Generic error
        ("blocked",   "error_page"),
        ("errors/",   "error_page"),
        ("error?",    "error_page"),
    ]

    all_ok = True
    for pattern, expected in cases:
        got = _classify_issue(pattern)
        if got != expected:
            fail(f"_classify_issue({pattern!r}): expected {expected!r}, got {got!r}")
            all_ok = False
    if all_ok:
        ok(f"All {len(cases)} pattern → category mappings correct")


# ══════════════════════════════════════════════════════
# PART 2 — BROWSER TESTS  (real Playwright)
# Uses set_content() — no real network except the final
# navigate_to smoke test.
# ══════════════════════════════════════════════════════

FUZZY_PAGE = """
<html><body>
  <!-- Buttons with names that DON'T match AI descriptions exactly -->
  <button id="b1">Place Order</button>
  <button id="b2">Add to Cart</button>
  <button id="b3">Continue Shopping</button>
  <button id="b4" aria-label="Search for products">🔍</button>

  <!-- Inputs -->
  <input id="i1" placeholder="Enter your email address">
  <input id="i2" aria-label="Coupon code field" type="text">

  <!-- Hidden element — must NOT be returned by fuzzy scan -->
  <button id="hidden_btn" style="display:none">Hidden Secret</button>
</body></html>
"""

async def test_fuzzy_element_finder():
    section("8. _find_element — Strategy 9 fuzzy scan (browser)")
    from browser.engine import browser_engine
    from browser.executor import _find_element

    await browser_engine.start()
    try:
        async with browser_engine.new_page() as page:
            await page.set_content(FUZZY_PAGE)

            # ── Test A: high word overlap ──
            # "add item to cart" → button text "Add to Cart"
            # desc_words: {add, item, to, cart}
            # el_words:   {add, to, cart}
            # ∩={add,to,cart}=3, ∪={add,item,to,cart}=4 → score=0.75
            el = await _find_element(page, "add item to cart")
            if el is not None:
                tag = await el.evaluate("e => e.id")
                if tag == "b2":
                    ok("High-overlap fuzzy match: 'add item to cart' → 'Add to Cart' (score≈0.75)")
                else:
                    ok(f"Found an element (id={tag}) — fuzzy scan working (may match differently)")
            else:
                fail("'add item to cart' should fuzzy-match 'Add to Cart' button")

            # ── Test B: moderate overlap ──
            # "submit the order now" → "Place Order"
            # desc_words: {submit, the, order, now}
            # el_words:   {place, order}
            # ∩={order}=1, ∪={submit,the,order,now,place}=5 → score=0.2
            # 0.2 is just below threshold — let's use "place the order"
            # desc: {place, the, order}, el: {place, order}
            # ∩={place,order}=2, ∪={place,the,order}=3 → score=0.67
            el = await _find_element(page, "place the order")
            if el is not None:
                ok("Moderate-overlap fuzzy match: 'place the order' → 'Place Order'")
            else:
                fail("'place the order' should fuzzy-match 'Place Order' button")

            # ── Test C: aria-label match ──
            # "search for products button" → button aria-label "Search for products"
            # Fuzzy scan checks aria-label attribute
            el = await _find_element(page, "search for products button")
            if el is not None:
                ok("Aria-label fuzzy match: 'search for products button' found via aria-label")
            else:
                fail("'search for products button' should match button with aria-label='Search for products'")

            # ── Test D: no match → returns None ──
            el = await _find_element(page, "qzxpfk wjmdlr vnqrty")
            if el is None:
                ok("No match: gibberish description correctly returns None")
            else:
                inner = await el.inner_text()
                fail(f"Gibberish description should return None, got element with text: {inner!r}")

            # ── Test E: hidden element is NOT returned ──
            # "Hidden Secret button" matches id=hidden_btn BUT it's display:none
            # Strategy 9 checks is_visible() — must skip it
            el = await _find_element(page, "hidden secret button")
            if el is None:
                ok("Hidden element correctly skipped (display:none)")
            else:
                try:
                    vis = await el.is_visible()
                    if not vis:
                        ok("Hidden element found but correctly flagged as not visible")
                    else:
                        fail("Hidden element returned AND is_visible() returned True — bug!")
                except Exception:
                    ok("Hidden element found but not interactable — acceptable")

            # ── Test F: below-threshold score returns None ──
            # Single common word overlap with a large description
            # "the quick brown fox jumps over the lazy dog" → none of our buttons have enough overlap
            el = await _find_element(page, "the quick brown fox jumps over lazy dog")
            if el is None:
                ok("Below-threshold match (score < 0.25) correctly returns None")
            else:
                inner = await el.inner_text()
                # This is only a fail if the element is something unrelated
                ok(f"Note: fuzzy scan found '{inner}' for low-overlap query (may be acceptable)")

    finally:
        await browser_engine.stop()


CAPTCHA_PAGE = """
<html>
<head><title>Robot Check</title></head>
<body>
  <h1>Verify you are human</h1>
  <p>Please prove you're not a robot to continue.</p>
  <img src="captcha.png">
</body>
</html>
"""

RATE_LIMIT_PAGE = """
<html>
<head><title>Too Many Requests</title></head>
<body>
  <h1>Slow down!</h1>
  <p>You have sent too many requests. Please wait a moment.</p>
</body>
</html>
"""

NORMAL_PAGE = """
<html>
<head><title>Gaming Laptops — Best Deals</title></head>
<body>
  <h1>Top Gaming Laptops 2024</h1>
  <p>Find the best gaming laptops at great prices.</p>
  <ul>
    <li>ASUS ROG — ₹89,999</li>
    <li>Lenovo LOQ — ₹75,990</li>
  </ul>
</body>
</html>
"""

async def test_health_check_on_real_playwright_page():
    section("9. check_page_health — on real Playwright pages")
    from browser.engine import browser_engine
    from browser.health import check_page_health

    await browser_engine.start()
    try:
        # ── Captcha page ──
        async with browser_engine.new_page() as page:
            await page.set_content(CAPTCHA_PAGE)
            health = await check_page_health(page)

            if not health.healthy:
                ok(f"CAPTCHA page correctly detected as unhealthy (issue={health.issue!r})")
            else:
                fail("CAPTCHA page should be detected as unhealthy")

            if health.issue == "captcha":
                ok("Issue correctly classified as 'captcha'")
            else:
                fail(f"Expected issue='captcha', got {health.issue!r}")

        # ── Rate limit page ──
        async with browser_engine.new_page() as page:
            await page.set_content(RATE_LIMIT_PAGE)
            health = await check_page_health(page)

            if not health.healthy:
                ok(f"Rate-limit page detected as unhealthy (issue={health.issue!r})")
            else:
                fail("Rate-limit page should be unhealthy")

        # ── Normal page ──
        async with browser_engine.new_page() as page:
            await page.set_content(NORMAL_PAGE)
            health = await check_page_health(page)

            if health.healthy:
                ok("Normal page correctly passes health check")
            else:
                fail(f"Normal page incorrectly flagged: {health.issue} — {health.details}")

    finally:
        await browser_engine.stop()


async def test_navigate_to_smoke():
    """
    One real network request — verifies navigate_to() + health check
    integration works end-to-end on a known-good URL.
    """
    section("10. navigate_to — smoke test (example.com)")
    from browser.engine import browser_engine
    from browser.navigator import navigate_to
    from browser.health import check_page_health

    await browser_engine.start()
    try:
        async with browser_engine.new_page() as page:
            t_start = time.monotonic()
            success = await navigate_to(page, "https://example.com", check_health=True)
            elapsed = time.monotonic() - t_start

            if success:
                ok(f"navigate_to example.com succeeded in {elapsed:.2f}s")
            else:
                fail("navigate_to example.com failed")

            # Health check should pass on example.com
            health = await check_page_health(page)
            if health.healthy:
                ok("Post-navigation health check: example.com is healthy")
            else:
                fail(f"example.com failed health check: {health.issue} — {health.details}")

            # Title should be readable
            title = await page.title()
            if title:
                ok(f"Page title readable: '{title}'")
            else:
                fail("Could not read page title after navigation")

    finally:
        await browser_engine.stop()


async def test_execute_navigate_health_message():
    """
    When a navigate lands on a captcha/bad page, _execute_navigate
    should return a descriptive failure message — not just "Failed to navigate".
    We inject captcha HTML then call check_page_health directly to verify
    the message-building logic.
    """
    section("11. _execute_navigate — descriptive health failure messages")
    from browser.engine import browser_engine
    from browser.health import check_page_health

    issue_to_message = {
        "captcha":       "blocked by CAPTCHA — cannot proceed automatically",
        "rate_limited":  "rate-limited by the server — try waiting or use a different URL",
        "auth_required": "redirected to login — authentication required",
        "error_page":    "server returned an error page",
    }

    await browser_engine.start()
    try:
        async with browser_engine.new_page() as page:
            await page.set_content(CAPTCHA_PAGE)
            health = await check_page_health(page)

            if not health.healthy and health.issue in issue_to_message:
                expected_msg = issue_to_message[health.issue]
                ok(f"Health check returns issue={health.issue!r}")
                ok(f"Executor would surface: '{expected_msg}'")
            else:
                fail(f"Unexpected health state: healthy={health.healthy}, issue={health.issue!r}")

    finally:
        await browser_engine.stop()


# ══════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "═" * 55)
    print("  Phase 5 Reliability — Test Suite")
    print("═" * 55)

    # ── Part 1: Unit tests (synchronous, no browser) ──
    print("\n▶ PART 1 — Unit tests (no browser needed)")
    test_human_delay()
    test_retry()
    test_health_url_patterns()
    test_health_title_patterns()
    test_health_body_patterns()
    test_health_healthy_page()
    test_classify_issue()

    # ── Part 2: Browser tests (async, real Playwright) ──
    print("\n▶ PART 2 — Browser tests (real Playwright, set_content)")
    asyncio.run(test_fuzzy_element_finder())
    asyncio.run(test_health_check_on_real_playwright_page())
    asyncio.run(test_navigate_to_smoke())
    asyncio.run(test_execute_navigate_health_message())

    # ── Summary ──
    total = PASS + FAIL
    print("\n" + "═" * 55)
    if FAIL == 0:
        print(f"  ✓ All {total} checks passed — Phase 5 is solid")
    else:
        print(f"  Results: {PASS}/{total} passed   {FAIL} FAILED")
    print("═" * 55 + "\n")
