"""
Multi-site comparison runner — Phase 6.

Runs the agent loop against multiple sites simultaneously using asyncio.gather().

How parallel execution works:
  - Each site gets its own coroutine: _run_one_site()
  - Each coroutine opens an independent browser context + page
  - asyncio.gather() runs all coroutines concurrently on the same event loop
  - Total time ≈ slowest site, not sum of all sites

Why this is safe:
  - Browser contexts are fully isolated (separate cookies, separate pages)
  - The agent loop and AI calls are already async — no blocking code
  - asyncio.gather() with return_exceptions=True means one site failing
    doesn't abort the others
"""

import asyncio
from browser.engine import browser_engine
from agent.loop import run_agent_loop


async def _run_one_site(query: str, site: str, max_steps: int) -> dict:
    """
    Run the full agent loop for one site and return its result.

    Goal construction: "Search {site} for: {query}"
    The agent sees the site name in the goal and navigates there first.

    This coroutine manages its own page lifecycle — opens a context,
    runs the loop, and closes the context when done (or on error).
    """
    goal = f"Search {site} for: {query}"
    print(f"[Compare] Starting site: {site}")
    try:
        async with browser_engine.new_page() as page:
            result = await run_agent_loop(goal=goal, page=page, max_steps=max_steps, site_domain=site)
            print(f"[Compare] Done with {site}: {'✓' if result['success'] else '✗'}")
            return {"site": site, **result}
    except Exception as e:
        print(f"[Compare] ✗ {site} crashed: {e}")
        return {
            "site": site,
            "success": False,
            "result": {},
            "summary": f"Site run failed: {e}",
            "steps_taken": 0,
            "history": [],
        }


async def run_comparison(
    query: str,
    sites: list[str],
    max_steps: int = 12,
) -> dict[str, dict]:
    """
    Run the agent loop against all sites in parallel.

    Returns a dict keyed by site name, each value being the loop result:
      {
        "amazon.in":    {"success": True, "result": {...}, "steps_taken": 4, ...},
        "flipkart.com": {"success": True, "result": {...}, "steps_taken": 3, ...},
      }

    Sites that fail (network error, bot block, extraction failure) are
    included with success=False and an error message — not dropped.
    This way the caller always gets a full picture.
    """
    tasks = [_run_one_site(query, site, max_steps) for site in sites]

    # return_exceptions=True: if a task raises an unhandled exception,
    # it comes back as the result value instead of propagating up.
    # We handle exceptions inside _run_one_site, so this is a safety net.
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    site_results = {}
    for i, raw in enumerate(raw_results):
        site = sites[i]
        if isinstance(raw, Exception):
            # Should not normally happen (we catch in _run_one_site), but just in case
            site_results[site] = {
                "success": False,
                "result": {},
                "summary": f"Unexpected error: {raw}",
                "steps_taken": 0,
            }
        else:
            site_results[site] = raw

    return site_results
