"""
Navigator — page navigation with retry logic and health checks.

Phase 5 upgrades:
  - navigate_to() now retries up to 3 times with exponential backoff
  - Health check after every successful navigation
  - Screenshot automatically saved on navigation failure
  - Human-like timing throughout
"""

import asyncio
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from pathlib import Path
from utils.retry import human_delay


async def navigate_to(
    page: Page,
    url: str,
    wait_until: str = "domcontentloaded",
    max_attempts: int = 3,
    check_health: bool = True,
) -> bool:
    """
    Navigate to a URL with retry and health checking.

    Phase 5 additions vs Phase 1:
      - Retries up to max_attempts times with exponential backoff
      - Runs a health check after landing (detects CAPTCHAs, error pages)
      - Auto-screenshots on failure for debugging
      - Human-like timing after successful navigation

    Why domcontentloaded as default (not networkidle)?
    Modern SPAs make continuous background requests. "networkidle" waits
    for 500ms of silence that never comes on Amazon/Google. We navigate
    to DOM ready, then wait for specific elements we actually need.
    """
    for attempt in range(max_attempts):
        try:
            response = await page.goto(
                url,
                wait_until=wait_until,
                timeout=30_000
            )

            if response is None:
                print(f"[Navigator] No response for {url} (attempt {attempt + 1})")
                await _wait_before_retry(attempt, max_attempts)
                continue

            if response.status >= 400:
                print(f"[Navigator] HTTP {response.status} for {url} (attempt {attempt + 1})")
                await _wait_before_retry(attempt, max_attempts)
                continue

            # Health check — HTTP 200 doesn't guarantee a usable page
            if check_health:
                from browser.health import check_page_health
                health = await check_page_health(page)
                if not health.healthy:
                    print(f"[Navigator] Unhealthy page ({health.issue}): {health.details}")
                    if health.issue == "captcha":
                        # CAPTCHA won't go away with a retry — fail immediately
                        await take_screenshot(page, f"captcha_{_safe_filename(url)}.png")
                        return False
                    await _wait_before_retry(attempt, max_attempts)
                    continue

            # Small human-like pause after landing
            await asyncio.sleep(human_delay(min_ms=100, max_ms=300))
            return True

        except PlaywrightTimeoutError:
            print(f"[Navigator] Timeout on {url} (attempt {attempt + 1}/{max_attempts})")
            await _wait_before_retry(attempt, max_attempts)
        except Exception as e:
            print(f"[Navigator] Error on {url}: {type(e).__name__}: {e} (attempt {attempt + 1})")
            await _wait_before_retry(attempt, max_attempts)

    # All attempts exhausted — take a failure screenshot
    try:
        await take_screenshot(page, f"nav_fail_{_safe_filename(url)}.png")
    except Exception:
        pass

    print(f"[Navigator] Failed to navigate to {url} after {max_attempts} attempts")
    return False


async def dismiss_popups_if_present(page: Page) -> bool:
    """
    Try to dismiss any overlay modal/popup that appeared after navigation.

    Runs automatically after every navigate action. If no popup exists,
    all strategies fail silently and we return False within ~1 second total.

    Why deterministic code instead of asking the AI?
    The AI sees the popup in the page state and might spend 2-3 steps
    trying different ways to close it. This resolves it in <1s, before
    the agent loop's first step even starts.

    Strategy order (most → least specific):
    1. ARIA role "button" named "close" — semantically correct
    2. aria-label="close" attribute — common on icon-only buttons
    3. Unicode × character — most sites use this as the close symbol
    4. Unicode ✕ character — alternative close symbol
    5. Any button inside a dialog / [role=dialog] — catches modal patterns
    6. Elements with 'close' anywhere in their class name — CSS fallback
    """
    # Wait briefly for any post-load modal to appear.
    # Most e-commerce popups render 300-600ms after DOMContentLoaded.
    await asyncio.sleep(0.7)

    strategies = [
        lambda: page.get_by_role("button", name="close", exact=False).first.click(timeout=1200),
        lambda: page.locator("[aria-label='close' i]").first.click(timeout=1200),
        lambda: page.get_by_text("×", exact=True).first.click(timeout=1200),
        lambda: page.get_by_text("✕", exact=True).first.click(timeout=1200),
        lambda: page.locator("dialog button, [role='dialog'] button").first.click(timeout=1200),
        lambda: page.locator("[class*='close' i]").first.click(timeout=1200),
    ]

    for strategy in strategies:
        try:
            await strategy()
            await asyncio.sleep(0.3)   # brief pause for the modal to animate out
            return True
        except Exception:
            continue   # try next strategy

    return False


async def wait_for_selector_safe(
    page: Page,
    selector: str,
    timeout: int = 10_000,
) -> bool:
    """
    Wait for a CSS selector, returning False instead of raising on timeout.

    Playwright throws TimeoutError if the selector doesn't appear.
    Returning False lets callers decide how to handle absence without
    try/except at every call site.
    """
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        return False
    except Exception:
        return False


async def take_screenshot(page: Page, filename: str) -> str:
    """
    Save a full-page screenshot for debugging.

    Screenshots are your primary debugging tool in headless mode.
    When a selector fails or the page looks wrong, the screenshot
    shows exactly what the browser saw at that moment.

    Auto-called on navigation failures in Phase 5.
    """
    screenshots_dir = Path("screenshots")
    screenshots_dir.mkdir(exist_ok=True)

    filepath = screenshots_dir / filename
    await page.screenshot(path=str(filepath), full_page=True)
    print(f"[Navigator] Screenshot saved: {filepath}")
    return str(filepath)


async def scroll_to_bottom(page: Page, pause_ms: int = 800) -> None:
    """
    Scroll the page gradually until no new content loads.
    Used for infinite-scroll pages.
    """
    previous_height = await page.evaluate("document.body.scrollHeight")

    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        # Use human-like pause rather than fixed sleep
        await asyncio.sleep(pause_ms / 1000 + human_delay(min_ms=0, max_ms=200))

        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == previous_height:
            break
        previous_height = new_height


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

async def _wait_before_retry(attempt: int, max_attempts: int) -> None:
    """Exponential backoff + jitter before the next navigation attempt."""
    import random
    if attempt < max_attempts - 1:
        delay = min(1.5 * (2 ** attempt), 8.0)  # 1.5s, 3s, 6s (capped at 8s)
        delay += random.uniform(-0.3, 0.5)
        delay = max(0.5, delay)
        print(f"[Navigator] Waiting {delay:.1f}s before retry...")
        await asyncio.sleep(delay)


def _safe_filename(url: str) -> str:
    """Convert URL to a safe filename for screenshots."""
    import re
    name = re.sub(r"https?://", "", url)
    name = re.sub(r"[^\w]", "_", name)
    return name[:40]
