"""
All AI prompts in one place.

Why centralize prompts?
  Prompts are essentially configuration. They're not logic.
  When you need to tune the agent's behavior, you come here — not
  to agent/planner.py or agent/loop.py. This keeps logic and
  configuration clearly separated.

Prompt engineering principles used here:
  1. Role clarity: Tell the AI exactly what it is and what it controls
  2. Constraint framing: Tell it what it CANNOT do (prevents hallucination)
  3. Output format: Explicit JSON schema in the prompt
  4. Few-shot examples: Show what good output looks like
  5. Reasoning chain: Ask for "thought" before "action" (improves accuracy)
"""

from models.actions import ACTION_DESCRIPTIONS


AGENT_SYSTEM_PROMPT = """You are a browser automation agent. You control a real web browser to complete tasks for users.

You work in a loop:
1. You receive the current page state (URL, visible text, interactive elements, links)
2. You decide ONE action to take next
3. The system executes it and shows you the updated page
4. Repeat until the task is complete

AVAILABLE ACTIONS — copy the exact JSON format shown, fill in the values:

Navigate to a URL:
{{"action": "navigate", "url": "https://example.com", "reason": "why"}}

Click a button, link, or any element:
{{"action": "click", "element_description": "submit button", "reason": "why"}}

Type into a text input, email, textarea, or time field:
{{"action": "type", "element_description": "email input", "text": "user@example.com", "press_enter": false, "reason": "why"}}

Choose from a <select> dropdown:
{{"action": "select", "element_description": "country dropdown", "option": "India", "reason": "why"}}

Check/select a checkbox or radio button (use check: false to uncheck):
{{"action": "check", "element_description": "Large pizza size", "check": true, "reason": "why"}}

Scroll the page:
{{"action": "scroll", "direction": "down", "reason": "why"}}

Extract structured data from page:
{{"action": "extract", "what": "all product titles, prices and links", "reason": "why"}}

Wait for content to load:
{{"action": "wait", "for_what": "form to submit", "reason": "why"}}

Signal task complete:
{{"action": "done", "result": {{}}, "summary": "what was accomplished", "reason": "why"}}

FORM FILLING RULES:
- For radio buttons: use "check" action, describe it as "the [Label] radio button" e.g. "the Large radio button"
- For checkboxes: use "check" action, describe it as "the [Label] checkbox" e.g. "the cheese checkbox"
- For <select> dropdowns: use "select" action with the visible option text
- For text/email/tel/textarea: use "type" action
- For time inputs: use "type" with format "HH:MM" e.g. "19:00"
- After filling all fields, click the submit button
- After submitting, extract the result or confirmation

CRITICAL RULES:
- Return ONLY raw JSON — no markdown, no ```json fences, no text outside the JSON
- Every action MUST include ALL fields from its example above (including "reason")
- One action per response — never combine multiple actions
- Use "done" immediately when the task is fully complete
"""

AGENT_ACTION_PROMPT = """TASK: {goal}

STEP {step} of maximum {max_steps}

{site_knowledge_section}
HISTORY OF PREVIOUS STEPS:
{history}

{page_state}

What is your next action? Return a single JSON object.
Remember: If the task is complete, use {{"action": "done", "result": {{...}}, "summary": "..."}}.
"""

EXTRACTION_PROMPT = """You are a data extraction assistant. Extract structured information from this web page.

EXTRACT: {what}

PAGE CONTENT:
{page_text}

PAGE LINKS (use these for URLs/hrefs):
{page_links}

Return a JSON object with the key "items" containing a list of extracted records.
Each record should have clear field names based on what was requested.
Only include data that is actually present on the page — do not hallucinate values.
If a field is missing for a record, omit it rather than guessing.

Example for "product titles, prices, and links":
{{
  "items": [
    {{"title": "Product Name", "price": "₹89,999", "link": "https://..."}},
    ...
  ]
}}
"""


def build_system_prompt() -> str:
    descriptions = "\n".join(
        f"  {name}: {desc}"
        for name, desc in ACTION_DESCRIPTIONS.items()
    )
    return AGENT_SYSTEM_PROMPT.format(action_descriptions=descriptions)


def build_action_prompt(
    goal: str,
    step: int,
    max_steps: int,
    history: list[dict],
    page_state_text: str,
    site_knowledge_text: str = "",
) -> str:
    # Format history compactly — the AI needs context but not full page states
    if history:
        history_text = "\n".join(
            f"  Step {h['step']}: [{h['action']}] {h.get('reason', '')} → {h['outcome']}"
            for h in history
        )
    else:
        history_text = "  (no previous steps — this is the first action)"

    # Include site knowledge only when it exists — adds a trailing blank line
    # so the prompt section spacing stays clean whether knowledge is present or not
    site_knowledge_section = (site_knowledge_text + "\n\n") if site_knowledge_text else ""

    return AGENT_ACTION_PROMPT.format(
        goal=goal,
        step=step + 1,
        max_steps=max_steps,
        history=history_text,
        page_state=page_state_text,
        site_knowledge_section=site_knowledge_section,
    )


SUMMARIZATION_PROMPT = """You are a research analyst. A browser agent extracted the following items from the web.

ORIGINAL GOAL: {goal}

EXTRACTED ITEMS ({count} total):
{items_text}

STATISTICAL CONTEXT (computed from the data):
{stats_text}

Your task: Analyse these items in the context of the original goal and return a JSON object with exactly these keys:

{{
  "summary": "2-3 sentence paragraph describing what was found and the overall picture",
  "recommendation": {{
    "title": "exact title of the best overall pick",
    "reason": "1-2 sentences explaining why this is the best choice for the goal"
  }},
  "best_value": {{
    "title": "exact title of the best price-to-quality option",
    "reason": "1 sentence on why this is best value"
  }},
  "top_rated": {{
    "title": "exact title of the highest rated item (if ratings available)",
    "reason": "1 sentence"
  }},
  "key_findings": ["finding 1", "finding 2", "finding 3"]
}}

RULES:
- Only reference items that actually appear in the extracted list
- If ratings are not available, set top_rated to null
- If fewer than 2 items, set best_value to null
- key_findings should be concrete observations (price ranges, standout specs, patterns)
- Return ONLY raw JSON — no markdown, no explanation outside the JSON
"""


def build_summarization_prompt(goal: str, items: list[dict], stats: dict) -> str:
    """Format items for the summarization prompt."""
    lines = []
    for i, item in enumerate(items, 1):
        parts = [f"{i}. {item.get('title', 'Unknown')}"]

        price = item.get("price")
        if isinstance(price, dict):
            display = price.get("display", "")
            discount = price.get("discount", "")
            parts.append(f"   Price: {display}" + (f" ({discount})" if discount else ""))
        elif price:
            parts.append(f"   Price: {price}")

        rating = item.get("rating")
        if rating is not None:
            parts.append(f"   Rating: {rating}/5")

        link = item.get("link")
        if link:
            parts.append(f"   Link: {link}")

        sponsored = item.get("sponsored", False)
        if sponsored:
            parts.append("   [Sponsored listing]")

        lines.append("\n".join(parts))

    items_text = "\n\n".join(lines)

    stats_lines = []
    price_range = stats.get("price_range")
    if price_range and price_range.get("min") is not None:
        currency = price_range.get("currency", "")
        stats_lines.append(
            f"- Price range: {currency} {price_range['min']:,.0f} – {price_range['max']:,.0f}"
            f" (avg: {price_range['avg']:,.0f})"
        )
    avg_rating = stats.get("avg_rating")
    if avg_rating:
        stats_lines.append(f"- Average rating: {avg_rating}/5")
    sponsored = stats.get("sponsored_count", 0)
    if sponsored:
        stats_lines.append(f"- {sponsored} of {stats.get('total', '?')} results are sponsored listings")

    stats_text = "\n".join(stats_lines) if stats_lines else "No statistical data available."

    return SUMMARIZATION_PROMPT.format(
        goal=goal,
        count=len(items),
        items_text=items_text,
        stats_text=stats_text,
    )


COMPARISON_PROMPT = """You are a shopping analyst comparing search results across multiple e-commerce sites.

QUERY: {query}

RESULTS BY SITE:
{sites_data}

Your task: Compare the results and return a JSON object with exactly these keys:

{{
  "price_winner": "site name with lower average prices, or null if comparable",
  "rating_winner": "site name with better average ratings, or null if comparable",
  "value_winner": "site offering the best overall value (price + quality combined)",
  "recommendation": "1-2 sentences: where to buy and specifically why",
  "key_differences": [
    "specific difference 1 (be quantitative where possible)",
    "specific difference 2",
    "specific difference 3"
  ]
}}

RULES:
- price_winner and rating_winner must be exact site names from the list, or null
- value_winner must be an exact site name
- recommendation must reference specific prices, ratings, or item names
- key_differences must be concrete observations — not vague ("prices vary")
- Return ONLY raw JSON — no markdown, no explanation text outside the JSON
"""


LEARNINGS_PROMPT = """A browser agent just completed a task on {domain}.

GOAL: {goal}

WHAT HAPPENED (step by step):
{history_text}

Based on this run, what should future agents know specifically about {domain}?

Return a JSON object with exactly these keys:
{{
  "successful_patterns": ["what worked — be specific, include element labels/descriptions used"],
  "failed_patterns": ["what failed and what to do instead — be concrete"],
  "known_obstacles": ["obstacles on this site — popups, redirects, login walls, bot checks"],
  "extraction_hints": ["how data is structured on this site — where products appear, how prices are labeled"]
}}

RULES:
- Only include facts specific to {domain}, not general browser knowledge
- Concrete beats vague: "Search bar label is 'Search Amazon'" not "search bar exists"
- Max 3-4 items per category — quality over quantity
- Return ONLY raw JSON
"""


def build_learnings_prompt(domain: str, goal: str, history: list[dict]) -> str:
    """Format run history for the post-run learning call."""
    lines = []
    for h in history:
        if h.get("action") == "system":
            continue
        status = "✓" if h.get("success") else "✗"
        lines.append(
            f"  Step {h['step']}: [{h['action']}] {h.get('reason', '')[:60]}"
            f" → {status} {h.get('outcome', '')[:80]}"
        )
    history_text = "\n".join(lines) if lines else "  (no steps recorded)"

    return LEARNINGS_PROMPT.format(
        domain=domain,
        goal=goal,
        history_text=history_text,
    )


def build_comparison_prompt(query: str, sites_data: list[dict]) -> str:
    """
    Format per-site data for the comparison prompt.

    sites_data is a list of dicts, one per site:
      {
        "site": "amazon.in",
        "items": [...],   # top N items with title, price, rating
        "stats": {...},   # Python-computed: avg price, avg rating, etc.
      }
    """
    sections = []
    for sd in sites_data:
        site = sd["site"]
        stats = sd.get("stats", {})
        items = sd.get("items", [])

        lines = [f"── {site} ──"]

        # Stats block
        price_range = stats.get("price_range")
        if price_range and price_range.get("avg") is not None:
            currency = price_range.get("currency", "")
            lines.append(
                f"  Price: avg {currency}{price_range['avg']:,.0f}"
                f" (range: {price_range['min']:,.0f}–{price_range['max']:,.0f})"
            )
        avg_rating = stats.get("avg_rating")
        if avg_rating:
            lines.append(f"  Avg rating: {avg_rating}/5 ({stats.get('rated_count', 0)} rated)")
        lines.append(f"  Items extracted: {stats.get('total', len(items))}")

        # Top items (up to 5)
        lines.append("  Top items:")
        for i, item in enumerate(items[:5], 1):
            title = item.get("title", "Unknown")[:60]
            price = item.get("price", {})
            price_str = price.get("display", "") if isinstance(price, dict) else str(price)
            rating = item.get("rating", "")
            rating_str = f" | ★{rating}" if rating else ""
            lines.append(f"    {i}. {title} | {price_str}{rating_str}")

        sections.append("\n".join(lines))

    return COMPARISON_PROMPT.format(
        query=query,
        sites_data="\n\n".join(sections),
    )


def build_extraction_prompt(what: str, page_text: str, page_links: list[dict]) -> str:
    links_text = "\n".join(
        f"  \"{link['text']}\" → {link['href']}"
        for link in page_links[:30]
    )
    return EXTRACTION_PROMPT.format(
        what=what,
        page_text=page_text[:5000],
        page_links=links_text,
    )
