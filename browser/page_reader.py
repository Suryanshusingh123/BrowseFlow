"""
Page Reader — extracts page state for the AI to reason about.

The AI agent needs to understand:
  1. Where am I? (URL, title)
  2. What can I see? (visible text)
  3. What can I interact with? (buttons, inputs, links)
  4. What links exist? (for navigation and extraction)

We extract all of this and package it as a clean dict.
The AI reads this dict and decides its next action.
"""

from playwright.async_api import Page


# Max characters of body text to send to AI.
# More text = better understanding BUT higher token cost.
# 4000 chars ≈ ~1000 tokens — a reasonable balance for most pages.
MAX_TEXT_LENGTH = 8000

# Max number of interactive elements to list
MAX_INTERACTIVE = 40

# Max number of links to list — 60 covers HN (9 nav + ~5 links per story × 10 stories)
MAX_LINKS = 60


async def get_page_state(page: Page) -> dict:
    """
    Extract everything the AI needs to understand the current page.

    Returns a dict with:
      - url: current URL
      - title: page title
      - text: visible page text (truncated)
      - interactive: buttons, inputs, links with their labels
      - links: href + surrounding text for all important links
    """
    # Wait for the DOM to be ready before reading anything.
    # Prevents "Execution context was destroyed" errors caused by
    # in-flight JavaScript redirects (common on Amazon, Flipkart).
    # wait_for_load_state returns immediately if the page is already stable.
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10_000)
    except Exception:
        pass  # Timed out or already loaded — proceed anyway

    url = page.url
    title = await page.title()

    # Extract visible text — strip scripts, styles, hidden elements
    # We run this as JavaScript in the browser for efficiency
    text = await page.evaluate("""
        () => {
            const clone = document.body.cloneNode(true);
            // Remove non-visible noise
            clone.querySelectorAll(
                'script, style, noscript, svg, [aria-hidden="true"], .visually-hidden'
            ).forEach(el => el.remove());
            const raw = clone.innerText || clone.textContent || '';
            // Collapse excess whitespace
            return raw.replace(/\\s+/g, ' ').trim();
        }
    """)

    # Truncate to stay within token budget
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "... [truncated]"

    # Extract interactive elements — include associated label text so AI uses readable names
    interactive = await page.evaluate(f"""
        () => {{
            const elements = [];
            const seen = new Set();

            // Build a map of input id → label text for <label for="id"> associations
            const labelMap = {{}};
            document.querySelectorAll('label').forEach(label => {{
                const forAttr = label.getAttribute('for');
                if (forAttr) labelMap[forAttr] = label.innerText.trim();
            }});

            document.querySelectorAll(
                'button, input:not([type="hidden"]), textarea, select, a[href], [role="button"]'
            ).forEach(el => {{
                // Priority: associated label > placeholder > aria-label > visible text > name attribute
                const associatedLabel = (el.id && labelMap[el.id]) ? labelMap[el.id] : '';
                const label = (
                    associatedLabel ||
                    el.placeholder ||
                    el.getAttribute('aria-label') ||
                    el.getAttribute('title') ||
                    el.innerText ||
                    el.getAttribute('name') ||
                    ''
                ).trim().slice(0, 80);

                if (!label || seen.has(label)) return;
                seen.add(label);

                const tagName = el.tagName.toLowerCase();
                const type = el.getAttribute('type') || tagName;
                const name = el.getAttribute('name') || '';
                elements.push({{ type, label, name }});
            }});
            return elements.slice(0, {MAX_INTERACTIVE});
        }}
    """)

    # Extract links — resolve relative hrefs to absolute so the cleaner can use them
    base_url = page.url
    links = await page.evaluate(f"""
        (baseUrl) => {{
            const links = [];
            const base = new URL(baseUrl);
            document.querySelectorAll('a[href]').forEach(el => {{
                const rawHref = el.getAttribute('href');
                const text = el.innerText.trim().slice(0, 100);
                if (!rawHref || !text || rawHref.startsWith('javascript:')) return;

                // Resolve relative URLs to absolute
                let href;
                try {{
                    href = new URL(rawHref, base).href;
                }} catch(e) {{
                    href = rawHref;
                }}

                links.push({{ text, href }});
            }});
            // Deduplicate by href
            const seen = new Set();
            return links.filter(l => {{
                if (seen.has(l.href)) return false;
                seen.add(l.href);
                return true;
            }}).slice(0, {MAX_LINKS});
        }}
    """, base_url)

    return {
        "url": url,
        "title": title,
        "text": text,
        "interactive_elements": interactive,
        "links": links,
    }


def format_page_state_for_prompt(state: dict) -> str:
    """
    Convert the page state dict into a clean text block for the AI prompt.

    Why a separate formatting function?
    The prompt structure might change (e.g., we add screenshots later).
    By isolating formatting here, we don't touch the prompt logic.
    """
    interactive_text = "\n".join(
        f"  - [{el['type']}] \"{el['label']}\"" + (f"  (name={el['name']})" if el.get('name') else "")
        for el in state.get("interactive_elements", [])
    )

    links_text = "\n".join(
        f"  - \"{link['text']}\" → {link['href']}"
        for link in state.get("links", [])[:40]  # show top 40 in prompt
    )

    return f"""=== CURRENT PAGE STATE ===
URL: {state['url']}
Title: {state['title']}

--- Visible Text (first {MAX_TEXT_LENGTH} chars) ---
{state['text']}

--- Interactive Elements ---
{interactive_text or '(none found)'}

--- Links on Page ---
{links_text or '(no links found)'}
=== END PAGE STATE ==="""
