"""
Data Cleaning Pipeline — Phase 3.

Runs after AI extraction to produce reliable, structured output.

Why pure Python here (no AI)?
  - Deterministic: same input always gives same output
  - Fast: no network calls
  - Testable: every function can be unit tested
  - Debuggable: when a price parses wrong, you fix the regex — not a prompt

Pipeline stages (run in order):
  1. parse_prices    — string prices → structured {amount, currency, display}
  2. normalize_ratings — "4.3 out of 5 stars" → 4.3
  3. enrich_links    — match titles to page links for missing hrefs
  4. deduplicate     — remove items with near-identical titles
  5. strip_noise     — remove "[Sponsored]" prefixes, mark flag

Each stage is independent — you can run any subset or add new ones.
"""

import re
from difflib import SequenceMatcher


# ─────────────────────────────────────────────
# Price parsing
# ─────────────────────────────────────────────

# Currency symbols → ISO codes
CURRENCY_MAP = {
    "₹": "INR",
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
}


def parse_price(raw: str | None) -> dict:
    """
    Parse a raw price string into structured components.

    Handles formats:
      "₹89,999"          → {display: "₹89,999", amount: 89999.0, currency: "INR"}
      "₹1,53,990"        → {amount: 153990.0}   ← Indian lakh format
      "₹76,990 (29% off)" → {amount: 76990.0, discount: "29% off"}
      "$1,299.00"         → {amount: 1299.0, currency: "USD"}
      "MRP: ₹89,999"      → {amount: 89999.0}
      None or ""          → {}

    Why keep `display` alongside `amount`?
    The display string is what you show users. The amount is for
    sorting, filtering, and comparisons. You need both.
    """
    if not raw or not isinstance(raw, str):
        return {}

    raw = raw.strip()

    # Detect currency
    currency = None
    for symbol, code in CURRENCY_MAP.items():
        if symbol in raw:
            currency = code
            break

    # Extract discount percentage if present: "(29% off)" or "29% off"
    discount = None
    discount_match = re.search(r"(\d+)\s*%\s*off", raw, re.IGNORECASE)
    if discount_match:
        discount = f"{discount_match.group(1)}% off"

    # Extract the numeric amount
    # Remove currency symbols, letters, parentheses, percentage mentions
    # Keep digits, commas, dots
    numeric_str = re.sub(r"[₹$€£¥]", "", raw)
    numeric_str = re.sub(r"[a-zA-Z%()]", "", numeric_str)
    numeric_str = numeric_str.strip().rstrip(".,")

    # Handle multiple price values (e.g., "₹76,990 ₹85,000")
    # Take the first (lowest / sale price)
    prices_found = re.findall(r"[\d,]+\.?\d*", numeric_str)
    if not prices_found:
        return {"display": raw}

    first_price_str = prices_found[0]

    # Remove commas (both Western "1,299" and Indian "1,53,990")
    amount_str = first_price_str.replace(",", "")
    try:
        amount = float(amount_str)
    except ValueError:
        return {"display": raw}

    result = {"display": raw, "amount": amount}
    if currency:
        result["currency"] = currency
    if discount:
        result["discount"] = discount

    return result


# ─────────────────────────────────────────────
# Rating normalization
# ─────────────────────────────────────────────

def normalize_rating(raw: str | None) -> float | None:
    """
    Extract a numeric rating from various text formats.

    "4.3 out of 5 stars"  → 4.3
    "4.3/5"               → 4.3
    "4.3"                 → 4.3
    "★★★★☆"              → 4.0  (count filled stars)
    "86%"                 → 4.3  (convert percentage to /5 scale)
    None or garbage       → None
    """
    if not raw:
        return None

    raw = str(raw).strip()

    # "X out of Y stars" or "X/Y"
    match = re.search(r"(\d+\.?\d*)\s*(?:out of|/)\s*(\d+)", raw, re.IGNORECASE)
    if match:
        value = float(match.group(1))
        scale = float(match.group(2))
        # Normalize to /5 if on a different scale
        if scale != 5:
            value = (value / scale) * 5
        return round(value, 1)

    # Star emoji counting: ★★★★☆
    if "★" in raw or "☆" in raw:
        filled = raw.count("★")
        return float(filled)

    # Percentage: "86%" → map to /5
    pct_match = re.search(r"(\d+)\s*%", raw)
    if pct_match:
        pct = float(pct_match.group(1))
        return round((pct / 100) * 5, 1)

    # Plain number
    plain = re.search(r"^\d+\.?\d*$", raw)
    if plain:
        val = float(plain.group())
        if 0 <= val <= 5:
            return round(val, 1)

    return None


# ─────────────────────────────────────────────
# Link enrichment
# ─────────────────────────────────────────────

def enrich_links(items: list[dict], page_links: list[dict]) -> list[dict]:
    """
    Fill in missing links by fuzzy-matching item titles against page links.

    When the AI extraction misses links (e.g., HN self-posts), we look at
    all the links on the page and find the one whose anchor text best matches
    the item's title.

    Uses word-overlap (Jaccard similarity):
      title words ∩ link text words
      ─────────────────────────────  ≥ threshold → use this link
      title words ∪ link text words

    Why not Levenshtein distance?
    Titles are long. Two strings can share most words but differ in ordering.
    Jaccard on word sets is faster and works better for long text.

    Why threshold 0.3?
    30% word overlap catches partial matches ("I automated opt-outs for 500..."
    matching link text "I automated opt-outs...") without false positives.
    """
    if not page_links:
        return items

    enriched = []
    for item in items:
        if item.get("link"):
            enriched.append(item)
            continue

        title = item.get("title", "")
        if not title:
            enriched.append(item)
            continue

        best_link = _find_best_link(title, page_links)
        if best_link:
            item = {**item, "link": best_link}  # non-destructive copy

        enriched.append(item)
    return enriched


def _find_best_link(title: str, page_links: list[dict]) -> str | None:
    """Find the page link whose text best matches the given title."""
    title_words = set(_tokenize(title))
    if not title_words:
        return None

    best_href = None
    best_score = 0.0
    threshold = 0.3

    for link in page_links:
        link_text = link.get("text", "")
        href = link.get("href", "")

        if not link_text or not href:
            continue

        # Skip javascript: and anchor-only links
        if href.startswith("javascript:") or href.startswith("#"):
            continue

        link_words = set(_tokenize(link_text))
        if not link_words:
            continue

        # Jaccard similarity
        intersection = title_words & link_words
        union = title_words | link_words
        score = len(intersection) / len(union) if union else 0

        if score > best_score:
            best_score = score
            best_href = href

    return best_href if best_score >= threshold else None


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase words, removing punctuation and stop words."""
    stop_words = {"a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "is", "it"}
    words = re.findall(r"\b[a-z0-9]+\b", text.lower())
    return [w for w in words if w not in stop_words and len(w) > 1]


# ─────────────────────────────────────────────
# Deduplication
# ─────────────────────────────────────────────

def deduplicate(items: list[dict]) -> tuple[list[dict], int]:
    """
    Remove items with identical or near-identical titles.

    Returns (deduplicated_list, num_removed).

    Why return num_removed?
    Metadata about what was cleaned helps you understand the quality
    of the raw extraction and tune the extraction prompt if needed.

    Two-pass approach:
    1. Exact match (normalized): catches exact duplicates
    2. Similarity match (SequenceMatcher): catches "Product X" vs "Product X (Sponsored)"
    """
    if not items:
        return items, 0

    seen_normalized: set[str] = set()
    seen_titles: list[str] = []
    unique: list[dict] = []
    removed = 0

    for item in items:
        title = item.get("title", "")
        normalized = _normalize_title(title)

        # Pass 1: exact normalized match
        if normalized in seen_normalized:
            removed += 1
            continue

        # Pass 2: fuzzy match against all kept titles
        is_duplicate = False
        for kept_title in seen_titles:
            ratio = SequenceMatcher(None, normalized, _normalize_title(kept_title)).ratio()
            if ratio > 0.85:  # 85% similar = effectively the same item
                is_duplicate = True
                break

        if is_duplicate:
            removed += 1
            continue

        seen_normalized.add(normalized)
        seen_titles.append(title)
        unique.append(item)

    return unique, removed


def _normalize_title(title: str) -> str:
    """Lowercase, strip whitespace, remove punctuation for comparison."""
    title = title.lower().strip()
    title = re.sub(r"\[.*?\]", "", title)       # remove [Sponsored], [pdf], etc.
    title = re.sub(r"\(.*?\)", "", title)       # remove (2024), (29% off), etc.
    title = re.sub(r"[^\w\s]", " ", title)     # replace punctuation with space
    title = re.sub(r"\s+", " ", title).strip() # collapse spaces
    return title


# ─────────────────────────────────────────────
# Noise stripping
# ─────────────────────────────────────────────

def strip_noise(items: list[dict]) -> list[dict]:
    """
    Clean up common noise in item titles and fields.

    - "[Sponsored]" prefix → remove from title, set sponsored=True
    - "[pdf]", "[video]" → move to a `content_type` field
    - Excessive whitespace → strip
    - Trailing/leading punctuation → strip
    """
    cleaned = []
    for item in items:
        item = dict(item)  # shallow copy — don't mutate original

        title = item.get("title", "")

        # Sponsored flag
        if title.lower().startswith("[sponsored]"):
            item["sponsored"] = True
            title = title[len("[sponsored]"):].strip()
        else:
            item.setdefault("sponsored", False)

        # Content type tags: [pdf], [video], [github], etc.
        content_type_match = re.search(r"\[(pdf|video|audio|github|slides)\]", title, re.IGNORECASE)
        if content_type_match:
            item["content_type"] = content_type_match.group(1).lower()
            title = re.sub(r"\[(?:pdf|video|audio|github|slides)\]", "", title, flags=re.IGNORECASE)

        item["title"] = title.strip()
        cleaned.append(item)

    return cleaned


# ─────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────

def clean_extraction(
    raw_items: list[dict],
    page_links: list[dict] | None = None,
) -> dict:
    """
    Run the full cleaning pipeline on raw AI-extracted items.

    Args:
        raw_items:   list of dicts from the AI extractor
        page_links:  full link list from page_reader (for link enrichment)

    Returns:
        {
          "items":              cleaned list,
          "total":              final count,
          "duplicates_removed": int,
          "links_enriched":     int,
        }
    """
    if not raw_items:
        return {"items": [], "total": 0, "duplicates_removed": 0, "links_enriched": 0}

    items = list(raw_items)

    # Stage 1: Strip noise (do this first — affects deduplication)
    items = strip_noise(items)

    # Stage 2: Deduplicate
    items, duplicates_removed = deduplicate(items)

    # Stage 3: Enrich missing links
    links_before = sum(1 for item in items if item.get("link"))
    if page_links:
        items = enrich_links(items, page_links)
    links_after = sum(1 for item in items if item.get("link"))
    links_enriched = links_after - links_before

    # Stage 4: Parse prices in-place
    for item in items:
        if "price" in item and item["price"]:
            item["price"] = parse_price(item["price"])

    # Stage 5: Normalize ratings in-place
    for item in items:
        if "rating" in item and item["rating"]:
            normalized = normalize_rating(str(item["rating"]))
            if normalized is not None:
                item["rating"] = normalized

    return {
        "items": items,
        "total": len(items),
        "duplicates_removed": duplicates_removed,
        "links_enriched": links_enriched,
    }
