"""
AI Summarizer — Phase 4.

Takes cleaned extraction results and produces:
  - A narrative summary of what was found
  - A top recommendation with justification
  - Best value and top-rated picks
  - Key findings (bullet points)
  - Statistical insights (computed in Python, not AI)

Architecture:
  compute_stats()     ← pure Python, deterministic, fast
  summarize()         ← calls Gemini with the stats + items
  build_response()    ← merges stats + AI output into final dict

Why compute stats in Python rather than asking the AI?
  - "average of [76990, 65990, 219990]" is exact in Python, approximate with AI
  - Python stats are instant, AI stats cost tokens + latency
  - We show Python stats to the AI in its prompt — it uses them as context
    rather than recalculating them (preventing hallucination)
"""

import asyncio
from ai.prompts import build_summarization_prompt
from ai.client import get_extraction_model
import json
import re


# ─────────────────────────────────────────────
# Statistical insights — pure Python
# ─────────────────────────────────────────────

def compute_stats(items: list[dict]) -> dict:
    """
    Compute quantitative statistics from cleaned items.
    These are deterministic facts, not AI guesses.
    """
    prices = []
    currency = None
    for item in items:
        price = item.get("price")
        if isinstance(price, dict) and price.get("amount") is not None:
            prices.append(price["amount"])
            if not currency and price.get("currency"):
                currency = price["currency"]

    ratings = [
        item["rating"]
        for item in items
        if isinstance(item.get("rating"), (int, float))
    ]

    price_range = None
    if prices:
        price_range = {
            "min": min(prices),
            "max": max(prices),
            "avg": round(sum(prices) / len(prices), 2),
            "currency": currency,
        }

    return {
        "total": len(items),
        "price_range": price_range,
        "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "rated_count": len(ratings),
        "sponsored_count": sum(1 for i in items if i.get("sponsored")),
        "with_links": sum(1 for i in items if i.get("link")),
    }


# ─────────────────────────────────────────────
# AI qualitative analysis
# ─────────────────────────────────────────────

async def summarize(goal: str, items: list[dict]) -> dict:
    """
    Generate qualitative analysis: summary, recommendation, key findings.

    Returns the full enriched result dict combining:
      - original items (unchanged)
      - Python-computed stats
      - AI-generated insights
    """
    if not items:
        return {
            "items": [],
            "summary": "No items were extracted to summarize.",
            "recommendation": None,
            "best_value": None,
            "top_rated": None,
            "key_findings": [],
            "insights": {},
        }

    stats = compute_stats(items)
    prompt = build_summarization_prompt(goal=goal, items=items, stats=stats)

    # Use the clean extraction model (no agent system prompt)
    # — same reason as extraction: we don't want the "return action JSON" instruction
    model = get_extraction_model()

    def _call():
        response = model.generate_content(prompt)
        return response.text

    raw = await asyncio.to_thread(_call)
    ai_analysis = _parse_analysis(raw)

    # Merge everything into one response object
    return {
        "items": items,
        "total": stats["total"],
        # AI-generated qualitative analysis
        "summary": ai_analysis.get("summary", ""),
        "recommendation": ai_analysis.get("recommendation"),
        "best_value": ai_analysis.get("best_value"),
        "top_rated": ai_analysis.get("top_rated"),
        "key_findings": ai_analysis.get("key_findings", []),
        # Python-computed quantitative stats
        "insights": stats,
    }


def _parse_analysis(raw: str) -> dict:
    """
    Parse AI response into a structured dict.
    Handles markdown code fences and stray text.
    """
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Find the JSON object in the response
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

    # If parsing fails entirely, return a minimal safe response
    return {
        "summary": raw[:300] if raw else "Summary unavailable.",
        "recommendation": None,
        "best_value": None,
        "top_rated": None,
        "key_findings": [],
    }
