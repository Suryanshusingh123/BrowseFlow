import asyncio
import re
from uuid import uuid4
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException

from browser.engine import browser_engine
from browser.navigator import navigate_to, take_screenshot
from browser.compare import run_comparison
from agent.loop import run_agent_loop
from ai.summarizer import summarize
from ai.compare import compare_sites
from memory.agent_memory import agent_memory
from memory.run_sessions import run_sessions
from models.schemas import AgentRequest, AgentResponse, PreferencesUpdate, CompareRequest, CompareResponse, SiteResult
from config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting AI Browser Agent...")
    await browser_engine.start()
    yield
    print("Shutting down...")
    await browser_engine.stop()


app = FastAPI(
    title="AI Browser Agent",
    description="A general-purpose AI browser agent — give it any web task in plain English",
    version="0.3.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {"status": "running", "version": "0.3.0"}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "browser": "running",
        "ai_provider": settings.ai_provider,
    }


@app.post("/screenshot")
async def screenshot_url(url: str, filename: str = "debug.png"):
    """Dev tool: navigate to any URL and take a screenshot."""
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    async with browser_engine.new_page() as page:
        success = await navigate_to(page, url)
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to navigate to {url}")
        path = await take_screenshot(page, filename)
        return {"success": True, "screenshot": path, "url": url}


@app.post("/run", response_model=AgentResponse)
async def run_agent(request: AgentRequest):
    """
    Run the AI browser agent with a natural language goal.

    Memory options:
      session="amazon.in"   — load/save browser cookies for this domain
      use_cache=true         — return cached result if fresh (skips browser)
      cache_ttl_hours=2.0    — how old cached results can be (default 1h)

    Preferences (set via POST /memory/preferences) act as defaults:
      - max_steps defaults to preferences.max_steps if not set in request
      - summarize defaults to preferences.summarize_by_default if not set

    Examples:
      {"goal": "Search Amazon for gaming laptops", "use_cache": true}
      {"goal": "Log in to site.com", "session": "site.com"}
      {"goal": "Extract HN top 10", "use_cache": true, "cache_ttl_hours": 0.5}
    """
    # ── Apply preference defaults ──────────────────────────────
    # Preferences fill in only if the request uses the field's default value.
    # We can't distinguish "user explicitly passed 15" from "default was 15",
    # so we check whether the value equals the schema default.
    prefs = agent_memory.preferences

    max_steps = request.max_steps
    if max_steps == 15:  # schema default → check preference
        max_steps = prefs.get("max_steps", 15)

    should_summarize = request.summarize
    if not should_summarize:  # False → check preference
        should_summarize = prefs.get("summarize_by_default", False)

    cache_ttl = request.cache_ttl_hours
    if cache_ttl == 1.0:  # schema default → check preference
        cache_ttl = prefs.get("cache_ttl_hours", 1.0)

    # Resolve session: explicit request > preference default
    session_domain = request.session or prefs.get("default_session")

    # ── Cache check (skip browser entirely on hit) ─────────────
    if request.use_cache:
        cached = agent_memory.results.get(request.goal, max_age_hours=cache_ttl)
        if cached:
            return AgentResponse(
                success=True,
                result=cached,
                summary="Returned from cache (no browser run needed)",
                steps_taken=0,
                from_cache=True,
            )

    # ── Run with browser ───────────────────────────────────────
    # Try to extract a domain from the goal (e.g. "Search amazon.in for...")
    # so the loop can load and save site knowledge for that domain.
    domain_match = re.search(
        r'\b([a-zA-Z0-9-]+\.[a-zA-Z]{2,3}(?:\.[a-zA-Z]{2,3})?)\b',
        request.goal,
    )
    site_domain = domain_match.group(1).lower() if domain_match else None

    async with browser_engine.new_page(session_domain=session_domain) as page:
        loop_result = await run_agent_loop(
            goal=request.goal,
            page=page,
            max_steps=max_steps,
            site_domain=site_domain,
        )

    result = loop_result.get("result")

    # ── AI summarization (Phase 4) ─────────────────────────────
    if should_summarize and result and result.get("items"):
        print(f"[Summarizer] Analysing {len(result['items'])} items...")
        result = await summarize(goal=request.goal, items=result["items"])
        print("[Summarizer] Done.")

    # ── Save to results cache ──────────────────────────────────
    # We always save successful runs so future use_cache=True calls benefit.
    if loop_result["success"] and result:
        agent_memory.results.save(request.goal, result)

    return AgentResponse(
        success=loop_result["success"],
        result=result,
        summary=loop_result.get("summary"),
        steps_taken=loop_result.get("steps_taken"),
        history=loop_result.get("history") if settings.debug else None,
        error=None if loop_result["success"] else loop_result.get("summary"),
        from_cache=False,
    )


# ══════════════════════════════════════════════════════════════
# Human-in-the-loop: async run with approval gates
# ══════════════════════════════════════════════════════════════

@app.post("/run-async")
async def run_async(request: AgentRequest):
    """
    Start an agent run in the background and return immediately.

    The agent runs concurrently. When it reaches a risky action
    (buy, confirm, delete, pay, etc.) it pauses and waits for approval.

    Workflow:
      1. POST /run-async  → get run_id
      2. GET  /run-async/{run_id}  → poll for status
      3. When status == "awaiting_approval": review pending_action
      4. POST /run-async/{run_id}/approve  OR  /run-async/{run_id}/deny
      5. Poll again until status == "done"
    """
    run_id = str(uuid4())[:8]   # short ID — easy to type in terminal
    session = run_sessions.create(run_id)

    domain_match = re.search(
        r'\b([a-zA-Z0-9-]+\.[a-zA-Z]{2,3}(?:\.[a-zA-Z]{2,3})?)\b',
        request.goal,
    )
    site_domain = domain_match.group(1).lower() if domain_match else None

    # Launch the agent as a background coroutine.
    # create_task() schedules it on the event loop and returns immediately —
    # this endpoint responds while the agent is still running.
    asyncio.create_task(
        _run_agent_background(run_id, request, site_domain, session)
    )

    return {
        "run_id":  run_id,
        "status":  "running",
        "message": f"Agent started. Poll GET /run-async/{run_id} for status.",
    }


async def _run_agent_background(run_id, request, site_domain, session):
    """
    The actual agent run — executes in the background after /run-async returns.

    Writes status/result/error back to the session object so the
    polling endpoint can read them.
    """
    import asyncio as _asyncio
    try:
        prefs = agent_memory.preferences
        max_steps = request.max_steps if request.max_steps != 15 else prefs.get("max_steps", 15)

        async with browser_engine.new_page() as page:
            loop_result = await run_agent_loop(
                goal=request.goal,
                page=page,
                max_steps=max_steps,
                site_domain=site_domain,
                approval_session=session,
            )

        session.result = loop_result
        session.status = "done"
        print(f"[Run {run_id}] Done — success={loop_result['success']}")

    except Exception as e:
        session.error = str(e)
        session.status = "error"
        print(f"[Run {run_id}] Error — {e}")


@app.get("/run-async/{run_id}")
async def get_run_status(run_id: str):
    """
    Poll the status of a background run.

    Status values:
      running           — agent is executing steps
      awaiting_approval — agent paused; inspect pending_action and approve/deny
      done              — agent finished; result is in the response
      error             — agent crashed; error message in the response
    """
    session = run_sessions.get(run_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    response = {"run_id": run_id, "status": session.status}

    if session.status == "awaiting_approval":
        response["pending_action"] = session.pending_action
        response["instructions"] = (
            f"POST /run-async/{run_id}/approve  — execute this action\n"
            f"POST /run-async/{run_id}/deny     — skip it, agent will try differently"
        )

    elif session.status == "done":
        response["result"] = session.result

    elif session.status == "error":
        response["error"] = session.error

    return response


@app.post("/run-async/{run_id}/approve")
async def approve_action(run_id: str):
    """
    Approve the pending action — agent will execute it and continue.
    """
    session = run_sessions.get(run_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if session.status != "awaiting_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Run is not awaiting approval (current status: '{session.status}')"
        )

    session.approved = True
    session.approval_event.set()   # wake the waiting coroutine
    return {"success": True, "message": "Action approved — agent continuing"}


@app.post("/run-async/{run_id}/deny")
async def deny_action(run_id: str):
    """
    Deny the pending action — agent skips it and the AI will try a different approach.

    The denial is recorded in the agent's history so it knows not to
    repeat the same action. The agent continues from the next step.
    """
    session = run_sessions.get(run_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if session.status != "awaiting_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Run is not awaiting approval (current status: '{session.status}')"
        )

    session.approved = False
    session.approval_event.set()   # wake the waiting coroutine
    return {"success": True, "message": "Action denied — agent will try a different approach"}


# ══════════════════════════════════════════════════════════════
# Phase 6: Multi-site comparison
# ══════════════════════════════════════════════════════════════

@app.post("/compare", response_model=CompareResponse)
async def compare(request: CompareRequest):
    """
    Search multiple sites in parallel and compare results.

    Runs one agent loop per site simultaneously — total time is the
    slowest site, not the sum of all sites.

    After extraction, if summarize=True (the default), an AI cross-analysis
    is run to determine which site wins on price, rating, and overall value.

    Example:
      {"query": "gaming laptops under 80000", "sites": ["amazon.in", "flipkart.com"]}
    """
    print(f"\n[Compare] Query: '{request.query}' across {request.sites}")

    # ── Run all sites in parallel ──────────────────────────────
    site_results = await run_comparison(
        query=request.query,
        sites=request.sites,
        max_steps=request.max_steps,
    )

    # ── Build per-site SiteResult objects ─────────────────────
    results: dict[str, SiteResult] = {}
    any_success = False

    for site in request.sites:
        loop = site_results.get(site, {})
        extracted = loop.get("result", {})
        items = extracted.get("items", [])
        success = loop.get("success", False)
        if success:
            any_success = True

        results[site] = SiteResult(
            success=success,
            items=items,
            total=len(items),
            steps_taken=loop.get("steps_taken", 0),
            error=None if success else loop.get("summary"),
        )

    # ── Cross-site AI comparison ───────────────────────────────
    comparison = None
    if request.summarize and any_success:
        print(f"[Compare] Running cross-site AI analysis...")
        comparison = await compare_sites(
            query=request.query,
            site_results=site_results,
        )
        print(f"[Compare] Analysis done. Value winner: {comparison.get('value_winner')}")

    return CompareResponse(
        success=any_success,
        query=request.query,
        sites=request.sites,
        results=results,
        comparison=comparison,
    )


# ══════════════════════════════════════════════════════════════
# Memory endpoints
# ══════════════════════════════════════════════════════════════

# ── Sessions ──────────────────────────────────────────────────

@app.get("/memory/sessions")
async def list_sessions():
    """List all saved browser sessions (domain + cookie count + save time)."""
    return {"sessions": agent_memory.sessions.list_all()}


@app.delete("/memory/sessions/{domain}")
async def delete_session(domain: str):
    """
    Delete the saved session for a domain.

    Use this when:
    - A session has expired (site shows login page despite saved cookies)
    - You want to test a fresh login flow
    - You've logged out of a site and want to clear stale cookies
    """
    existed = agent_memory.sessions.delete(domain)
    if not existed:
        raise HTTPException(status_code=404, detail=f"No session found for '{domain}'")
    return {"success": True, "message": f"Session for '{domain}' deleted"}


# ── Results cache ──────────────────────────────────────────────

@app.get("/memory/results")
async def list_results():
    """
    List all cached results.

    Shows: goal text, when it was saved, item count, age in hours.
    """
    return {"results": agent_memory.results.list_all()}


@app.delete("/memory/results")
async def clear_results(goal: str | None = None, max_age_hours: float | None = None):
    """
    Clear cached results.

    - ?goal=<text>         → delete the specific cached result for this goal
    - ?max_age_hours=2.0   → delete all results older than 2 hours
    - no params            → delete ALL cached results
    """
    if goal:
        existed = agent_memory.results.delete(goal)
        if not existed:
            raise HTTPException(status_code=404, detail=f"No cached result for that goal")
        return {"success": True, "message": "Cached result deleted"}

    if max_age_hours is not None:
        deleted = agent_memory.results.clear_stale(max_age_hours)
        return {"success": True, "deleted": deleted, "message": f"Cleared {deleted} stale result(s)"}

    # Full clear — delete all result files
    deleted = agent_memory.results.clear_stale(max_age_hours=0.0)
    return {"success": True, "deleted": deleted, "message": f"Cleared all {deleted} cached result(s)"}


# ── Site knowledge ────────────────────────────────────────────

@app.get("/memory/site-knowledge")
async def list_site_knowledge():
    """List all domains the agent has learned about, with fact counts."""
    return {"sites": agent_memory.site_knowledge.list_all()}


@app.get("/memory/site-knowledge/{domain}")
async def get_site_knowledge(domain: str):
    """Get the full knowledge the agent has stored for a specific domain."""
    data = agent_memory.site_knowledge.get(domain)
    if not data:
        raise HTTPException(status_code=404, detail=f"No knowledge found for '{domain}'")
    return data


@app.delete("/memory/site-knowledge/{domain}")
async def delete_site_knowledge(domain: str):
    """
    Delete all stored knowledge for a domain.

    Use this when a site has changed its layout and the stored
    knowledge is now outdated or causing the agent to behave incorrectly.
    """
    existed = agent_memory.site_knowledge.delete(domain)
    if not existed:
        raise HTTPException(status_code=404, detail=f"No knowledge found for '{domain}'")
    return {"success": True, "message": f"Knowledge for '{domain}' deleted"}


# ── Preferences ────────────────────────────────────────────────

@app.get("/memory/preferences")
async def get_preferences():
    """
    Get all current preferences (stored values merged with defaults).

    These act as request defaults — any request field that isn't explicitly
    set will use the corresponding preference value.
    """
    return agent_memory.preferences.get_all()


@app.post("/memory/preferences")
async def set_preferences(updates: PreferencesUpdate):
    """
    Set one or more preferences.

    Only fields you include are updated. Omitted fields keep their current value.

    Example:
      {"max_steps": 20, "summarize_by_default": true}
      → future /run requests will use max_steps=20 by default
    """
    # Convert to dict, strip None values (omitted fields)
    changes = {k: v for k, v in updates.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(status_code=400, detail="No preferences provided")
    agent_memory.preferences.set_many(changes)
    return {"success": True, "updated": changes, "all": agent_memory.preferences.get_all()}


@app.delete("/memory/preferences")
async def reset_preferences(key: str | None = None):
    """
    Reset preferences to defaults.

    - ?key=max_steps  → reset only that key
    - no params       → reset ALL preferences
    """
    agent_memory.preferences.reset(key)
    return {"success": True, "preferences": agent_memory.preferences.get_all()}
