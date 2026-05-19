"""
Page Health Checker.

The core insight: HTTP 200 doesn't mean the page loaded correctly.

A CAPTCHA page returns 200.
An Amazon bot-detection page returns 200.
A Cloudflare challenge returns 200.
A "temporarily unavailable" page returns 200.
A JavaScript error that silently killed the page returns 200.

To know if a page is usable, you must inspect its content — not its status code.

We check three signals in order of speed:
  1. URL patterns    — fastest, no DOM parsing needed
  2. Page title      — slightly slower, title is always in the DOM
  3. Content checks  — slower, scans visible text
"""

from playwright.async_api import Page


# Known bad URL patterns across major platforms
BAD_URL_PATTERNS = [
    "captcha",
    "validatecaptcha",
    "robot",
    "challenge",
    "access-denied",
    "blocked",
    "429",
    "errors/",
    "error?",
    "signin?",          # unexpectedly redirected to login
    "account/login",
]

# Title patterns that indicate an unusable page
BAD_TITLE_PATTERNS = [
    "access denied",
    "robot check",
    "captcha",
    "too many requests",
    "rate limit",
    "page not found",
    "404",
    "500",
    "503",
    "server error",
    "something went wrong",
    "temporarily unavailable",
    "cloudflare",
    "ddos",
]

# Text patterns in the visible body that indicate problems
BAD_CONTENT_PATTERNS = [
    "prove you're not a robot",
    "verify you are human",
    "your ip has been blocked",
    "too many requests",
    "rate limit exceeded",
    "access denied",
    "unusual traffic",         # Google's rate limit message
    "automated queries",       # Google
    "this site is protected",  # hCaptcha/reCaptcha
]


class PageHealth:
    """Result of a health check."""
    def __init__(self, healthy: bool, issue: str | None = None, details: str = ""):
        self.healthy = healthy
        self.issue = issue      # "captcha" | "rate_limited" | "error_page" | "redirect" | None
        self.details = details  # human-readable description

    def __repr__(self):
        if self.healthy:
            return "PageHealth(healthy)"
        return f"PageHealth(issue={self.issue!r}, details={self.details!r})"


async def check_page_health(page: Page) -> PageHealth:
    """
    Run a full health check on the current page.

    Fast path: URL check (no DOM access needed).
    Medium path: title check (minimal DOM access).
    Slow path: body text scan (only if needed).
    """
    url = page.url.lower()

    # Fast path: URL patterns
    for pattern in BAD_URL_PATTERNS:
        if pattern in url:
            return PageHealth(
                healthy=False,
                issue=_classify_issue(pattern),
                details=f"Bad URL pattern '{pattern}' in: {page.url}"
            )

    # Medium path: page title
    try:
        title = (await page.title()).lower()
        for pattern in BAD_TITLE_PATTERNS:
            if pattern in title:
                return PageHealth(
                    healthy=False,
                    issue=_classify_issue(pattern),
                    details=f"Bad title pattern '{pattern}' in: '{await page.title()}'"
                )
    except Exception:
        pass  # Can't read title — don't fail the health check

    # Slow path: sample body text (first 1000 chars only)
    try:
        body_text = await page.evaluate(
            "() => document.body?.innerText?.slice(0, 1000)?.toLowerCase() || ''"
        )
        for pattern in BAD_CONTENT_PATTERNS:
            if pattern in body_text:
                return PageHealth(
                    healthy=False,
                    issue="captcha" if "robot" in pattern or "human" in pattern else "rate_limited",
                    details=f"Content pattern '{pattern}' found on page"
                )
    except Exception:
        pass

    return PageHealth(healthy=True)


def _classify_issue(pattern: str) -> str:
    """Map a detected pattern to an issue category."""
    if any(w in pattern for w in ["captcha", "robot", "human", "challenge"]):
        return "captcha"
    if any(w in pattern for w in ["429", "rate", "too many"]):
        return "rate_limited"
    if any(w in pattern for w in ["login", "signin", "account"]):
        return "auth_required"
    return "error_page"
