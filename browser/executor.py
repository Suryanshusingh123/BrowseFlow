"""
Action Executor — safely runs AI-decided actions in the browser.

The AI outputs actions as JSON. This module takes those validated
action objects and executes them against a real Playwright page.

Key principle: Every execution is wrapped in try/except.
If an action fails, we return a clear failure result so the AI can
adapt its strategy — not crash the whole agent.

The hardest problem: "click the search button" → finding the right element.
We use a multi-strategy approach with Playwright's semantic locators.
"""

import asyncio
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
from models.actions import (
    NavigateAction, ClickAction, TypeAction,
    SelectAction, CheckAction,
    ScrollAction, ExtractAction, WaitAction, DoneAction, AgentAction
)
from browser.navigator import navigate_to, take_screenshot, dismiss_popups_if_present
from browser.page_reader import get_page_state
from ai.client import extract_structured_data
from utils.cleaner import clean_extraction
from utils.retry import human_delay


async def execute_action(page: Page, action: AgentAction) -> dict:
    """
    Dispatch an action to the right handler.
    Returns a result dict: {"success": bool, "outcome": str, ...}
    """
    action_type = action.action

    handlers = {
        "navigate": _execute_navigate,
        "click":    _execute_click,
        "type":     _execute_type,
        "select":   _execute_select,
        "check":    _execute_check,
        "scroll":   _execute_scroll,
        "extract":  _execute_extract,
        "wait":     _execute_wait,
        "done":     _execute_done,
    }

    handler = handlers.get(action_type)
    if not handler:
        return {"success": False, "outcome": f"Unknown action: {action_type}"}

    try:
        return await handler(page, action)
    except Exception as e:
        return {"success": False, "outcome": f"Action '{action_type}' failed: {str(e)}"}


# ─────────────────────────────────────────────
# Individual action handlers
# ─────────────────────────────────────────────

async def _execute_navigate(page: Page, action: NavigateAction) -> dict:
    url = action.url
    # Ensure absolute URL
    if not url.startswith("http"):
        url = "https://" + url

    success = await navigate_to(page, url)
    if success:
        dismissed = await dismiss_popups_if_present(page)
        if dismissed:
            print(f"[Executor] Auto-dismissed popup on {url}")
        return {"success": True, "outcome": f"Navigated to {url}"}

    # Navigation failed — run a health check on whatever page we ended up on.
    # This tells the AI WHY it failed (captcha? rate-limited? error page?),
    # rather than just "failed", so it can decide whether to retry or give up.
    try:
        from browser.health import check_page_health
        health = await check_page_health(page)
        if not health.healthy:
            issue_map = {
                "captcha":      "blocked by CAPTCHA — cannot proceed automatically",
                "rate_limited": "rate-limited by the server — try waiting or use a different URL",
                "auth_required": "redirected to login — authentication required",
                "error_page":   "server returned an error page",
            }
            reason = issue_map.get(health.issue, health.details)
            return {"success": False, "outcome": f"Navigation to {url} failed: {reason}"}
    except Exception:
        pass

    return {"success": False, "outcome": f"Failed to navigate to {url} after multiple attempts"}


async def _execute_click(page: Page, action: ClickAction) -> dict:
    """
    Click an element described in natural language.

    Strategy waterfall (most → least specific):
    1. Role-based: page.get_by_role("button", name=...)
    2. Text-based: page.get_by_text(...)
    3. Label-based: page.get_by_label(...)
    4. Placeholder: page.get_by_placeholder(...)
    5. Title attribute: page.get_by_title(...)

    We try each strategy and use the first one that finds a visible element.
    """
    desc = action.element_description
    element = await _find_element(page, desc)

    if element is None:
        return {
            "success": False,
            "outcome": f"Could not find element matching: '{desc}'. Try a different description."
        }

    try:
        await element.scroll_into_view_if_needed()
        await asyncio.sleep(human_delay())     # human-like pause before click
        await element.click(timeout=5000)
        await asyncio.sleep(human_delay())     # human-like pause after click
        return {"success": True, "outcome": f"Clicked '{desc}'"}
    except PlaywrightTimeout:
        await take_screenshot(page, f"click_fail_{desc[:20].replace(' ','_')}.png")
        return {"success": False, "outcome": f"Click timed out on '{desc}'"}


async def _execute_type(page: Page, action: TypeAction) -> dict:
    """
    Find an input element and type text into it.

    For search boxes: we clear existing text first, then type.
    press_enter: True automatically submits the form (useful for searches).
    """
    desc = action.element_description
    element = await _find_element(page, desc, prefer_input=True)

    if element is None:
        return {
            "success": False,
            "outcome": f"Could not find input element matching: '{desc}'"
        }

    try:
        await element.scroll_into_view_if_needed()
        await asyncio.sleep(human_delay())     # human-like pause before interacting
        await element.click()
        # Triple-click selects all text, then typing replaces it
        await element.press("Control+a")
        await element.fill(action.text)  # fill() is more reliable than type() for inputs
        await asyncio.sleep(human_delay())     # human-like pause after typing

        if action.press_enter:
            await element.press("Enter")
            await page.wait_for_timeout(1500)  # wait for search results

        outcome = f"Typed '{action.text}' into '{desc}'"
        if action.press_enter:
            outcome += " and pressed Enter"
        return {"success": True, "outcome": outcome}

    except PlaywrightTimeout:
        return {"success": False, "outcome": f"Type action timed out on '{desc}'"}


async def _execute_select(page: Page, action: SelectAction) -> dict:
    """
    Choose an option from a <select> dropdown.

    Playwright's select_option() can match by:
      - label (visible text): select_option(label="India")   ← we use this
      - value (HTML attribute): select_option(value="in")
      - index: select_option(index=2)

    We try label first (what the user sees), then value (what the HTML says).
    The AI describes what it sees on screen, so label is almost always right.
    """
    desc = action.element_description
    option = action.option

    # Find the <select> element itself
    select_el = await _find_select(page, desc)
    if select_el is None:
        return {
            "success": False,
            "outcome": f"Could not find dropdown matching: '{desc}'"
        }

    try:
        await select_el.scroll_into_view_if_needed()

        # Try matching by visible label text first
        try:
            await select_el.select_option(label=option)
            return {"success": True, "outcome": f"Selected '{option}' in '{desc}'"}
        except Exception:
            pass

        # Fallback: match by value attribute (case-insensitive)
        try:
            await select_el.select_option(value=option.lower())
            return {"success": True, "outcome": f"Selected '{option}' (by value) in '{desc}'"}
        except Exception:
            pass

        # Last resort: find the option whose text contains our string
        options = await select_el.locator("option").all()
        for opt in options:
            opt_text = (await opt.inner_text()).strip()
            if option.lower() in opt_text.lower():
                opt_val = await opt.get_attribute("value")
                await select_el.select_option(value=opt_val)
                return {"success": True, "outcome": f"Selected '{opt_text}' in '{desc}'"}

        return {"success": False, "outcome": f"Option '{option}' not found in dropdown '{desc}'"}

    except PlaywrightTimeout:
        return {"success": False, "outcome": f"Select timed out on '{desc}'"}


async def _execute_check(page: Page, action: CheckAction) -> dict:
    """
    Check/uncheck a checkbox or select a radio button.

    Key insight: radio buttons and checkboxes are found by their
    associated label text, not their HTML value attribute.

    The label text is what the user sees: "Large", "Cheese", "Yes"
    The value attribute is what HTML uses: "large", "cheese", "yes"

    We use Playwright's role-based locators which match against labels:
      page.get_by_role("radio", name="Large") — finds the radio next to "Large"
      page.get_by_role("checkbox", name="Cheese") — finds the checkbox next to "Cheese"

    State awareness: we check the current state before acting.
    Clicking an already-checked checkbox would uncheck it — wrong!
    """
    desc = action.element_description
    should_check = action.check
    desc_lower = desc.lower()

    # Determine element type from description
    is_radio = any(w in desc_lower for w in ["radio", "option", "size", "type"])
    roles_to_try = ["radio", "checkbox"] if is_radio else ["checkbox", "radio"]

    element = None
    for role in roles_to_try:
        try:
            # Extract the label text — remove "radio button" / "checkbox" from the description
            # e.g. "the Large radio button" → "Large"
            clean_desc = (desc
                .lower()
                .replace("radio button", "").replace("radio", "")
                .replace("checkbox", "").replace("check box", "")
                .replace("the ", "").replace(" option", "")
                .strip())

            # Try with cleaned description first, then full description
            for name in [clean_desc, desc]:
                locator = page.get_by_role(role, name=name, exact=False)
                if await locator.count() > 0:
                    element = locator.first
                    break
            if element:
                break
        except Exception:
            pass

    # Fallback: try get_by_label
    if element is None:
        try:
            locator = page.get_by_label(desc, exact=False)
            if await locator.count() > 0:
                element = locator.first
        except Exception:
            pass

    if element is None:
        return {
            "success": False,
            "outcome": f"Could not find checkbox/radio matching: '{desc}'"
        }

    try:
        await element.scroll_into_view_if_needed()

        # Check current state before acting — don't click if already in desired state
        is_checked = await element.is_checked()

        if is_checked == should_check:
            # Already in the right state — nothing to do
            state = "checked" if should_check else "unchecked"
            return {"success": True, "outcome": f"'{desc}' already {state} — no change needed"}

        await element.click()
        await page.wait_for_timeout(200)

        state = "checked" if should_check else "unchecked"
        return {"success": True, "outcome": f"'{desc}' is now {state}"}

    except PlaywrightTimeout:
        return {"success": False, "outcome": f"Check action timed out on '{desc}'"}


async def _find_select(page: Page, description: str):
    """
    Find a <select> element by its associated label or nearby text.

    <select> elements don't have role="listbox" in most browsers until opened,
    so get_by_role() is unreliable. We use get_by_label() instead, which
    matches <select> elements linked to a <label> via 'for' attribute or wrapping.
    """
    # Strategy 1: label association (most forms use <label for="id">)
    try:
        locator = page.get_by_label(description, exact=False)
        if await locator.count() > 0:
            # Make sure it's actually a select element
            tag = await locator.first.evaluate("el => el.tagName")
            if tag == "SELECT":
                return locator.first
    except Exception:
        pass

    # Strategy 2: find any <select> near text matching the description
    try:
        # Look for a select whose surrounding text matches
        all_selects = page.locator("select")
        count = await all_selects.count()
        for i in range(count):
            sel = all_selects.nth(i)
            # Check the select's own options for a match
            options_text = await sel.evaluate(
                "el => Array.from(el.options).map(o => o.text).join(' ')"
            )
            if description.lower() in options_text.lower():
                return sel
    except Exception:
        pass

    return None


async def _execute_scroll(page: Page, action: ScrollAction) -> dict:
    pixels = 600 if action.direction == "down" else -600
    await page.evaluate(f"window.scrollBy(0, {pixels})")
    await page.wait_for_timeout(500)
    return {"success": True, "outcome": f"Scrolled {action.direction}"}


async def _execute_extract(page: Page, action: ExtractAction) -> dict:
    """
    Extract structured data from the page using AI, then clean it.

    Flow:
    1. Get page state (text + links)
    2. AI extracts raw items from page text
    3. DataCleaner pipeline cleans the raw items:
       - strips noise ([Sponsored], [pdf] tags)
       - removes duplicates
       - enriches missing links via page_links
       - parses prices into {amount, currency, display}
       - normalises ratings to float

    The page_links are passed to BOTH:
    - The AI extractor (so it can include links in its output)
    - The cleaner (so it can fill in any links the AI missed)
    """
    state = await get_page_state(page)

    # Step 1: AI extraction (raw, messy)
    raw_extracted = await extract_structured_data(
        what=action.what,
        page_text=state["text"],
        page_links=state["links"],
    )

    raw_items = raw_extracted.get("items", [])

    # Step 2: Clean the raw items
    cleaned = clean_extraction(raw_items, page_links=state["links"])

    item_count = cleaned["total"]
    meta = f"(removed {cleaned['duplicates_removed']} dupes, enriched {cleaned['links_enriched']} links)"

    return {
        "success": True,
        "outcome": f"Extracted {item_count} items: {action.what} {meta}",
        "extracted_data": cleaned,   # now contains items + metadata
    }


async def _execute_wait(page: Page, action: WaitAction) -> dict:
    """
    Wait for content to load.

    We don't do fixed sleeps — we wait for the load state to settle.
    The `for_what` description is logged but not used for selector matching
    (that would require another AI call). Simple timeout is enough here.
    """
    await page.wait_for_load_state("domcontentloaded", timeout=action.timeout_ms)
    await page.wait_for_timeout(500)
    return {"success": True, "outcome": f"Waited for: {action.for_what}"}


async def _execute_done(page: Page, action: DoneAction) -> dict:
    return {
        "success": True,
        "outcome": "Task completed",
        "final_result": action.result,
        "summary": action.summary,
    }


# ─────────────────────────────────────────────
# Element finder — the hardest part
# ─────────────────────────────────────────────

async def _find_element(page: Page, description: str, prefer_input: bool = False):
    """
    Find a page element using natural language description.

    Tries multiple Playwright locator strategies in order of reliability.
    Returns the first visible, enabled element found, or None.

    Why this order?
    - Role + name: Most semantic, least likely to match wrong element
    - Text match: Good for buttons/links with visible labels
    - Placeholder: Best for input fields (search boxes say "Search...")
    - Label: Good for form fields with <label> elements
    - Title: Fallback for elements with title attributes

    We check `is_visible()` to avoid matching hidden/offscreen duplicates.
    """
    desc_lower = description.lower()

    # Strategy 1: Role-based (most reliable for interactive elements)
    role_attempts = []
    if prefer_input or any(w in desc_lower for w in ["input", "field", "box", "search", "textarea"]):
        role_attempts = ["textbox", "searchbox", "combobox"]
    elif any(w in desc_lower for w in ["button", "submit", "click", "btn"]):
        role_attempts = ["button", "link"]
    else:
        role_attempts = ["button", "link", "textbox"]

    for role in role_attempts:
        try:
            locator = page.get_by_role(role, name=description, exact=False)
            if await locator.count() > 0 and await locator.first.is_visible():
                return locator.first
        except Exception:
            pass

    # Strategy 2: Placeholder text (great for search inputs)
    try:
        locator = page.get_by_placeholder(description, exact=False)
        if await locator.count() > 0 and await locator.first.is_visible():
            return locator.first
    except Exception:
        pass

    # Strategy 3: Exact text match
    try:
        locator = page.get_by_text(description, exact=True)
        if await locator.count() > 0 and await locator.first.is_visible():
            return locator.first
    except Exception:
        pass

    # Strategy 4: Partial text match (broader, more likely to find something)
    try:
        # Use the first 3 words of the description for partial matching
        short_desc = " ".join(description.split()[:3])
        locator = page.get_by_text(short_desc, exact=False)
        if await locator.count() > 0 and await locator.first.is_visible():
            return locator.first
    except Exception:
        pass

    # Strategy 5: Label
    try:
        locator = page.get_by_label(description, exact=False)
        if await locator.count() > 0 and await locator.first.is_visible():
            return locator.first
    except Exception:
        pass

    # Strategy 6: Title attribute
    try:
        locator = page.get_by_title(description, exact=False)
        if await locator.count() > 0 and await locator.first.is_visible():
            return locator.first
    except Exception:
        pass

    # Strategy 7: HTML name attribute (e.g. AI says "comments" matching name="comments")
    try:
        locator = page.locator(f'[name="{description}"]')
        if await locator.count() > 0 and await locator.first.is_visible():
            return locator.first
    except Exception:
        pass

    # Strategy 8: textarea tag directly (AI sometimes says "textarea" or "text area")
    if any(w in desc_lower for w in ["textarea", "text area", "instructions", "comments", "message", "note"]):
        try:
            locator = page.locator("textarea")
            if await locator.count() > 0 and await locator.first.is_visible():
                return locator.first
        except Exception:
            pass

    # Strategy 9: Fuzzy scan — last resort
    # Scan all visible interactive elements and fuzzy-match their text against the description.
    # Why this matters: the AI says "Submit order button" but the actual button text is "Place Order".
    # Semantic strategies fail because the names don't match exactly.
    # A word-overlap scan finds it immediately.
    #
    # We score by Jaccard similarity of word sets:
    #   desc words ∩ element words  /  desc words ∪ element words
    # Threshold 0.25 catches partial matches while avoiding false positives.
    try:
        desc_words = set(desc_lower.split())
        best_element = None
        best_score = 0.0

        # Scan buttons, links, inputs, and textareas
        candidate_selector = "button, a, input, textarea, [role='button'], [role='link']"
        candidates = page.locator(candidate_selector)
        count = await candidates.count()

        for i in range(min(count, 60)):   # cap at 60 to avoid very slow pages
            el = candidates.nth(i)
            try:
                if not await el.is_visible():
                    continue

                # Gather all text signals for this element
                signals = []
                inner = (await el.inner_text()).strip().lower()
                if inner:
                    signals.append(inner)
                for attr in ["aria-label", "placeholder", "title", "value", "name"]:
                    val = await el.get_attribute(attr)
                    if val:
                        signals.append(val.strip().lower())

                # Score each signal and keep the best
                for signal in signals:
                    signal_words = set(signal.split())
                    if not signal_words:
                        continue
                    intersection = desc_words & signal_words
                    union = desc_words | signal_words
                    score = len(intersection) / len(union) if union else 0
                    if score > best_score:
                        best_score = score
                        best_element = el

            except Exception:
                continue

        if best_element is not None and best_score >= 0.25:
            print(f"[Executor] Fuzzy match found element for '{description}' (score={best_score:.2f})")
            return best_element

    except Exception:
        pass

    return None  # All strategies exhausted
