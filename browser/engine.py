import asyncio
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from config import get_settings
from memory.agent_memory import agent_memory

settings = get_settings()


class BrowserEngine:
    """
    Manages the Playwright browser lifecycle.

    One instance of this class is meant to live for the duration
    of the FastAPI application. We don't create a new browser
    per request — that's slow. We create one browser and
    reuse it by creating new contexts per request.
    """

    def __init__(self):
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def start(self) -> None:
        """Start Playwright and launch the browser. Called once at app startup."""
        self._playwright = await async_playwright().start()

        # We use Chromium. Alternatives: firefox, webkit.
        # Chromium is the most compatible with modern sites and
        # has the best DevTools Protocol support for Playwright.
        self._browser = await self._playwright.chromium.launch(
            headless=settings.browser_headless,
            slow_mo=settings.browser_slow_mo,  # slows each action by N ms — great for debugging
            args=[
                "--no-sandbox",              # required for some Linux environments
                "--disable-blink-features=AutomationControlled",  # hides automation signals
            ]
        )
        print(f"Browser started (headless={settings.browser_headless})")

    async def stop(self) -> None:
        """Cleanly shut down browser and Playwright. Called once at app shutdown."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        print("Browser stopped")

    @asynccontextmanager
    async def new_context(self, storage_state: str | None = None):
        """
        Creates an isolated browser context.

        Used directly for multi-tab workflows (Phase 6: parallel site scraping).
        For single-page work, prefer new_page() which handles routing setup too.

        storage_state: optional path to a Playwright storage_state file.
          Pass agent_memory.sessions.get_path("domain") to load saved cookies.
        """
        if not self._browser:
            raise RuntimeError("Browser not started. Call engine.start() first.")

        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            storage_state=storage_state,
            # Setting a real user agent is important — sites check this.
            # Playwright's default UA contains "HeadlessChrome" which many
            # anti-bot systems block immediately.
        )
        try:
            yield context
        finally:
            await context.close()

    @asynccontextmanager
    async def new_page(self, session_domain: str | None = None):
        """
        Creates a context + page in one step.

        session_domain: optional domain key (e.g. "amazon.in").
          - If provided AND a saved session exists, the browser context is
            initialised with those cookies/localStorage — agent starts logged in.
          - After the page block exits, the updated session state is saved back
            to disk so any new cookies (e.g. from this run's login) are persisted.
          - If no saved session exists yet, the context starts fresh. The first
            run that logs in will save the session for all future runs.

        Why save in finally?  The context must be saved BEFORE it's closed —
        once closed, all state is gone. The finally block runs before close().
        """
        # Load existing session if we have one
        storage_state = None
        if session_domain:
            storage_state = agent_memory.sessions.get_path(session_domain)
            if storage_state:
                print(f"[Memory] Loading session for '{session_domain}'")
            else:
                print(f"[Memory] No saved session for '{session_domain}' — starting fresh")

        if not self._browser:
            raise RuntimeError("Browser not started. Call engine.start() first.")

        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            storage_state=storage_state,   # None = fresh; path = load saved cookies
        )

        page = await context.new_page()

        # Block unnecessary resources to speed up page loads and
        # reduce bandwidth. Images and fonts don't help us extract text.
        await page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,ico}",
            lambda route: route.abort()
        )
        await page.route(
            "**/*.{woff,woff2,ttf,eot}",
            lambda route: route.abort()
        )

        try:
            yield page
        finally:
            # Save session state BEFORE closing the context
            if session_domain:
                try:
                    await agent_memory.sessions.save(context, session_domain)
                except Exception as e:
                    print(f"[Memory] Warning: could not save session for '{session_domain}': {e}")
            await context.close()


# Global singleton — one browser instance for the whole app
browser_engine = BrowserEngine()
