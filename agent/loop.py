"""
The Agent Loop — the core of the browser agent.

This is the loop that runs until the task is done or max steps reached:

  while steps < max_steps:
    1. Read page state
    2. Ask AI: what next?
    3. Execute action
    4. If action == "done": return result
    5. Add to history, go to step 1

The loop is deliberately simple. Complexity lives in:
  - page_reader.py (what AI sees)
  - ai/client.py (how AI decides)
  - executor.py (how actions run)

This separation means you can improve each layer independently.
"""

import asyncio
import re

from playwright.async_api import Page

from browser.page_reader import get_page_state, format_page_state_for_prompt
from browser.executor import execute_action
from ai.client import decide_next_action
from ai.learner import extract_learnings_passive
from memory.agent_memory import agent_memory
from memory.run_sessions import RunSession
from models.actions import DoneAction

# Actions the human must approve before execution.
# Matched against element_description (for click) and text (for type).
_HIGH_RISK_KEYWORDS = {
    "buy", "purchase", "order", "checkout", "pay", "payment",
    "confirm", "place order", "buy now", "proceed to pay",
    "delete", "remove", "cancel", "send", "submit",
}


def _needs_human_approval(action) -> bool:
    """
    Return True if this action should be held for human approval.

    Only click and type actions on high-risk elements require approval.
    Navigate, scroll, extract, read — never require approval.
    """
    if action.action not in ("click", "type"):
        return False

    # Check element_description and text only — NOT reason.
    # The reason is the agent's internal thinking and will mention risky keywords
    # even for innocent actions ("I need to find the Buy Now button").
    text_to_check = " ".join([
        getattr(action, "element_description", ""),
        getattr(action, "text", ""),
    ]).lower()

    # Use word boundaries so "buy" doesn't match "buying", "payment" doesn't
    # match "display", etc. Multi-word keywords like "buy now" still match correctly.
    return any(
        re.search(r'\b' + re.escape(kw) + r'\b', text_to_check)
        for kw in _HIGH_RISK_KEYWORDS
    )

# Safety limits
DEFAULT_MAX_STEPS = 15   # prevent infinite loops
DEFAULT_TIMEOUT_PER_STEP = 30  # seconds per AI call (not enforced here, but good to know)


async def run_agent_loop(
    goal: str,
    page: Page,
    max_steps: int = DEFAULT_MAX_STEPS,
    site_domain: str | None = None,
    approval_session: RunSession | None = None,
) -> dict:
    """
    Run the agent loop until done or max steps reached.

    Args:
        goal: Natural language task description
        page: Playwright page (already set up)
        max_steps: Safety cap on iterations

    Returns:
        {
          "success": bool,
          "result": dict,          # the extracted/completed data
          "summary": str,          # human-readable outcome description
          "steps_taken": int,
          "history": list[dict],   # full step-by-step trace for debugging
        }
    """
    history = []
    print(f"\n[Agent] Starting task: '{goal}'")
    print(f"[Agent] Max steps: {max_steps}\n")

    # ── Load site knowledge ────────────────────────────────────
    site_knowledge_text = ""
    if site_domain:
        site_knowledge_text = agent_memory.site_knowledge.format_for_prompt(site_domain)
        if site_knowledge_text:
            facts = site_knowledge_text.count("•")
            print(f"[Agent] Loaded {facts} facts for '{site_domain}' from memory")

    for step in range(max_steps):
        print(f"[Agent] ── Step {step + 1}/{max_steps} ──")

        # ── 1. Read current page state ──
        # Retry once on failure — the page may still be mid-navigation
        # (e.g. Amazon's redirect chain on first load).
        try:
            page_state = await get_page_state(page)
            page_state_text = format_page_state_for_prompt(page_state)
        except Exception as first_err:
            print(f"[Agent] Page read failed, retrying in 2s: {first_err}")
            await asyncio.sleep(2)
            try:
                page_state = await get_page_state(page)
                page_state_text = format_page_state_for_prompt(page_state)
            except Exception as e:
                print(f"[Agent] Page read failed again: {e}")
                _save_knowledge(site_domain, history)
                return _error_result(f"Could not read page: {e}", history, step)

        # ── 2. Ask AI: what's the next action? ──
        try:
            action = await decide_next_action(
                goal=goal,
                step=step,
                max_steps=max_steps,
                history=history,
                page_state_text=page_state_text,
                site_knowledge_text=site_knowledge_text,
            )
        except Exception as e:
            print(f"[Agent] AI decision failed: {e}")
            _save_knowledge(site_domain, history)
            return _error_result(f"AI failed to decide next action: {e}", history, step)

        reason = getattr(action, "reason", "")[:80]
        print(f"[Agent] AI decided: {action.action.upper()} — {reason}")

        # ── 3. If done, return immediately ──
        if isinstance(action, DoneAction):
            print(f"[Agent] Task complete after {step + 1} steps")
            _save_knowledge(site_domain, history)
            return {
                "success": True,
                "result": action.result,
                "summary": action.summary,
                "steps_taken": step + 1,
                "history": history,
            }

        # ── 4. Human approval gate ────────────────────────────────
        # If this run has an attached session and the action is risky,
        # pause here and wait for explicit human approval before proceeding.
        if approval_session and _needs_human_approval(action):
            desc = getattr(action, "element_description", "") or getattr(action, "text", "")
            print(f"[Agent] ⏸  Approval required: {action.action} → '{desc}'")

            approval_session.pending_action = {
                "action":              action.action,
                "element_description": getattr(action, "element_description", ""),
                "text":                getattr(action, "text", ""),
                "reason":              action.reason,
                "step":                step + 1,
            }
            approval_session.status = "awaiting_approval"
            approval_session.approval_event.clear()

            # Suspend this coroutine until approve or deny is called.
            # The event loop stays unblocked — other HTTP requests are handled normally.
            await approval_session.approval_event.wait()

            approval_session.status = "running"
            approval_session.pending_action = None

            if not approval_session.approved:
                print(f"[Agent] ✗ Action denied by human")
                history.append({
                    "step":    step + 1,
                    "action":  action.action,
                    "reason":  action.reason,
                    "outcome": "Action denied by human. Find a different way to complete the task, or use 'done' if it cannot be completed without this action.",
                    "success": False,
                })
                # Skip execution — loop continues, AI will see the denial
                continue

            print(f"[Agent] ✓ Action approved by human")

        # ── 5. Execute the action ──
        execution_result = await execute_action(page, action)

        # ── 6. Record step in history ──
        step_record = {
            "step": step + 1,
            "action": action.action,
            "reason": action.reason,
            "outcome": execution_result.get("outcome", ""),
            "success": execution_result.get("success", False),
        }

        # If this was a successful extract action, store data AND auto-complete
        if action.action == "extract" and "extracted_data" in execution_result:
            step_record["extracted_data"] = execution_result["extracted_data"]
            extracted = execution_result["extracted_data"]
            item_count = extracted.get("total", len(extracted.get("items", [])))
            if item_count > 0:
                # Append the extract step to history BEFORE returning
                history.append(step_record)
                dupes = extracted.get("duplicates_removed", 0)
                enriched = extracted.get("links_enriched", 0)
                meta = f" (removed {dupes} dupes, enriched {enriched} links)" if dupes or enriched else ""
                print(f"[Agent] ✓ Extraction complete — {item_count} items{meta}. Task done.")
                _save_knowledge(site_domain, history)
                return {
                    "success": True,
                    "result": extracted,
                    "summary": f"Extracted {item_count} items{meta}",
                    "steps_taken": step + 1,
                    "history": history,
                }

        history.append(step_record)

        print(f"[Agent] Result: {'✓' if execution_result['success'] else '✗'} {execution_result.get('outcome', '')[:100]}")

        # If execution failed, the AI will see this in the next step's history
        # and can adapt (try a different selector, navigate differently, etc.)

        # ── Anti-loop detection ──
        # Only trigger if the SAME action has FAILED 3+ times in a row.
        # Succeeding at the same action repeatedly (e.g., filling multiple text fields)
        # is normal — we should never interrupt that. Only failed repetition = stuck.
        if _is_stuck(history):
            print("[Agent] ⚠ Loop detected — injecting recovery hint")
            history.append({
                "step": step + 2,
                "action": "system",
                "reason": "",
                "outcome": "WARNING: You have failed the same action 3 times in a row. "
                           "Change your approach — use a different element description, "
                           "scroll to find the element, or use 'done' if the task is complete.",
                "success": False,
            })

    # ── Max steps reached without "done" ──
    print(f"[Agent] Max steps ({max_steps}) reached without completing task")

    # Check if we extracted anything useful along the way
    extracted = _collect_extracted_data(history)
    if extracted:
        _save_knowledge(site_domain, history)
        return {
            "success": True,
            "result": extracted,
            "summary": f"Reached max steps but collected data along the way",
            "steps_taken": max_steps,
            "history": history,
        }

    _save_knowledge(site_domain, history)
    return _error_result(
        f"Task not completed within {max_steps} steps. The website may require more interaction.",
        history,
        max_steps
    )


def _is_stuck(history: list[dict], repeat_threshold: int = 3) -> bool:
    """
    Detect if the agent is stuck by checking for repeated FAILURES.

    Key distinction:
    - 3 successful type actions in a row = filling a form = NORMAL, don't interrupt
    - 3 failed click actions in a row = can't find the button = STUCK, intervene

    We only flag as stuck if the recent repeated actions all failed.
    A mix of success and failure, or all success = not stuck.
    """
    if len(history) < repeat_threshold:
        return False

    # Filter out system messages
    real_steps = [h for h in history if h.get("action") != "system"]
    if len(real_steps) < repeat_threshold:
        return False

    recent = real_steps[-repeat_threshold:]
    actions = [h["action"] for h in recent]
    successes = [h["success"] for h in recent]

    # Same action type repeated AND all failed = stuck
    all_same_action = len(set(actions)) == 1
    all_failed = not any(successes)

    return all_same_action and all_failed


def _collect_extracted_data(history: list[dict]) -> dict:
    """Pull together any extracted_data from extract steps."""
    for step in reversed(history):  # prefer most recent extraction
        if "extracted_data" in step:
            return step["extracted_data"]
    return {}


def _save_knowledge(site_domain: str | None, history: list[dict]) -> None:
    """
    Extract passive learnings from history and persist to site knowledge store.

    Called on every exit path — successes and failures alike.
    Failed runs are especially valuable: they contain real failed_patterns and
    known_obstacles that future runs need to avoid.
    """
    if not site_domain or not history:
        return
    # Skip if we have too little signal — a single step isn't worth saving.
    real_steps = [h for h in history if h.get("action") != "system"]
    if len(real_steps) < 2:
        return
    learnings = extract_learnings_passive(history)
    total = sum(len(v) for v in learnings.values())
    if total:
        agent_memory.site_knowledge.update(site_domain, learnings)
        print(f"[Agent] Saved {total} new facts for '{site_domain}'")


def _error_result(message: str, history: list, steps: int) -> dict:
    return {
        "success": False,
        "result": {},
        "summary": message,
        "steps_taken": steps,
        "history": history,
    }
