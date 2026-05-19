"""
Cross-site AI comparison — Phase 6.

Takes per-site extraction results (from browser/compare.py) and produces
a structured comparison: which site wins on price, rating, and overall value.

Architecture:
  compute_per_site_stats()  ← pure Python, reuses summarizer.compute_stats()
  compare_sites()           ← assembles prompt, calls Gemini, parses result
"""

import asyncio
import json
import re

from ai.summarizer import compute_stats
from ai.client import get_extraction_model
from ai.prompts import build_comparison_prompt


async def compare_sites(query: str, site_results: dict[str, dict]) -> dict:
    """
    Generate a cross-site comparison using AI.

    Args:
        query:        The original search query (e.g. "gaming laptops")
        site_results: Output of browser/compare.run_comparison() —
                      keyed by site name, values are agent loop results.

    Returns a dict with:
        price_winner, rating_winner, value_winner, recommendation, key_differences
    """
    # Build per-site data: stats + top items for each site
    sites_data = []
    for site, loop_result in site_results.items():
        items = loop_result.get("result", {}).get("items", [])
        stats = compute_stats(items)
        stats["total"] = len(items)
        sites_data.append({
            "site": site,
            "items": items,
            "stats": stats,
        })

    # If fewer than 2 sites have data, comparison isn't meaningful
    sites_with_data = [sd for sd in sites_data if sd["stats"]["total"] > 0]
    if len(sites_with_data) < 2:
        available = sites_with_data[0]["site"] if sites_with_data else "none"
        return {
            "price_winner": None,
            "rating_winner": None,
            "value_winner": available if sites_with_data else None,
            "recommendation": "Only one site returned results — comparison not available.",
            "key_differences": [],
        }

    prompt = build_comparison_prompt(query=query, sites_data=sites_data)

    model = get_extraction_model()

    def _call():
        response = model.generate_content(prompt)
        return response.text

    raw = await asyncio.to_thread(_call)
    return _parse_comparison(raw)


def _parse_comparison(raw: str) -> dict:
    """Parse Gemini's comparison response, handling markdown fences."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

    return {
        "price_winner": None,
        "rating_winner": None,
        "value_winner": None,
        "recommendation": "Comparison analysis unavailable.",
        "key_differences": [],
    }
