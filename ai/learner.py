"""
Site knowledge learner — extracts learnings from completed run history.

Two modes:
  Passive  — pure Python, always runs, zero cost, catches clear-cut patterns
  Active   — one extra Gemini call, opt-in, catches nuanced site-specific observations

Both return the same dict shape so they can be merged by the caller:
  {
    "successful_patterns": [...],
    "failed_patterns":     [...],
    "known_obstacles":     [...],
    "extraction_hints":    [...],
  }
"""

import asyncio
import json
import re


# ─────────────────────────────────────────────────────────────
# Passive learning — deterministic Python
# ─────────────────────────────────────────────────────────────

_OBSTACLE_SIGNALS = (
    "captcha", "bot check", "blocked", "rate-limited", "rate limited",
    "login required", "auth required", "redirected to login", "access denied",
    "error page",
)


def extract_learnings_passive(history: list[dict]) -> dict:
    """
    Parse a completed run's history and extract learnings without any AI call.

    What we detect:
      ✓ type/click actions that succeeded → record as successful patterns
      ✗ type/click actions that failed → record as failed patterns
      ⚠ navigation failures with known signals → record as known obstacles
      ↗ extract actions that returned data → record as extraction hints

    Pattern text comes from `outcome` (what the executor did) rather than
    `reason` (the AI's internal thinking) — outcomes are factual and reusable.

    All patterns are tagged source="executor_failure" or source="executor_success"
    to distinguish them from AI-inferred learnings. The memory layer uses source
    to set decay rates and resolve conflicts between sources.
    """
    successful_patterns: list[str] = []
    failed_patterns:     list[str] = []
    known_obstacles:     list[str] = []
    extraction_hints:    list[str] = []

    for step in history:
        if step.get("action") == "system":
            continue

        action  = step.get("action", "")
        success = step.get("success", False)
        outcome = step.get("outcome", "").strip()

        if action in ("type", "click") and success and outcome:
            successful_patterns.append(outcome)

        elif action in ("type", "click") and not success and outcome:
            failed_patterns.append(outcome)

        elif action == "navigate" and not success and outcome:
            outcome_lower = outcome.lower()
            if any(sig in outcome_lower for sig in _OBSTACLE_SIGNALS):
                known_obstacles.append(outcome)
            else:
                failed_patterns.append(outcome)

        elif action == "extract" and success:
            data = step.get("extracted_data", {})
            total = data.get("total", len(data.get("items", [])))
            if total > 0 and outcome:
                extraction_hints.append(outcome)

    def _tag(patterns: list[str]) -> list[dict]:
        return [{"pattern": p, "source": "executor_failure"} for p in _dedup(patterns)]

    return {
        "successful_patterns": _tag(successful_patterns)[:5],
        "failed_patterns":     _tag(failed_patterns)[:5],
        "known_obstacles":     _tag(known_obstacles)[:3],
        "extraction_hints":    _tag(extraction_hints)[:3],
    }


# ─────────────────────────────────────────────────────────────
# Active learning — one Gemini call for richer insights
# ─────────────────────────────────────────────────────────────

async def extract_learnings_ai(
    domain: str,
    goal: str,
    history: list[dict],
) -> dict:
    """
    Ask Gemini to read the full run history and produce site-specific insights.

    Better than passive for detecting:
      - Popups and obstacles that appeared mid-run
      - Site-specific navigation patterns
      - Why something failed (not just that it did)

    Costs one extra API call. Use when you want richer knowledge building.
    """
    from ai.prompts import build_learnings_prompt
    from ai.client import get_extraction_model

    prompt = build_learnings_prompt(domain=domain, goal=goal, history=history)
    model = get_extraction_model()

    def _call():
        return model.generate_content(prompt).text

    raw = await asyncio.to_thread(_call)
    return _parse_learnings(raw)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _dedup(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        key = item.lower().strip()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _parse_learnings(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return _empty()
        else:
            return _empty()

    result = {}
    for key in ["successful_patterns", "failed_patterns", "known_obstacles", "extraction_hints"]:
        val = data.get(key, [])
        if not isinstance(val, list):
            result[key] = []
            continue
        # Accept either plain strings or pre-tagged dicts from the AI response.
        items = []
        for v in val:
            if isinstance(v, dict) and v.get("pattern"):
                items.append({"pattern": str(v["pattern"]), "source": "ai_derived"})
            elif v:
                items.append({"pattern": str(v), "source": "ai_derived"})
        result[key] = items[:5]
    return result


def _empty() -> dict:
    return {k: [] for k in ["successful_patterns", "failed_patterns", "known_obstacles", "extraction_hints"]}
