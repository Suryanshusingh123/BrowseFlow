"""
All actions the AI agent can take, defined as Pydantic models.

Why a fixed action set?
  The AI cannot invent arbitrary actions. It must choose from this list.
  This is the "safe execution" principle: the AI decides WHAT, Python
  decides HOW. By constraining the action space, we prevent the AI from
  attempting things our executor doesn't know how to handle safely.

Discriminated union:
  Python needs to know which model to parse AI output into.
  The `action` field (a Literal type) is the discriminator —
  Pydantic reads `action: "click"` and knows to use ClickAction.
"""

from pydantic import BaseModel, Field
from typing import Literal, Union, Annotated


class NavigateAction(BaseModel):
    """Go to a specific URL."""
    action: Literal["navigate"]
    url: str
    reason: str = ""    # AI explains WHY it chose this action (useful for debugging)


class ClickAction(BaseModel):
    """Click an element described in natural language."""
    action: Literal["click"]
    element_description: str   # e.g. "the search button", "the first product title link"
    reason: str = ""


class TypeAction(BaseModel):
    """Focus an input and type text into it."""
    action: Literal["type"]
    element_description: str   # e.g. "search box", "email input field"
    text: str                  # text to type
    press_enter: bool = False  # whether to press Enter after typing
    reason: str = ""


class ScrollAction(BaseModel):
    """Scroll the page."""
    action: Literal["scroll"]
    direction: Literal["down", "up"] = "down"
    reason: str = ""


class ExtractAction(BaseModel):
    """
    Extract structured data from the current page.

    The AI describes WHAT to extract in natural language.
    The executor then sends the page content to AI again for extraction.

    This is a two-AI-call pattern:
      Call 1 (planner): "what action next?" → "extract product data"
      Call 2 (extractor): "extract product data from this HTML" → structured JSON
    """
    action: Literal["extract"]
    what: str     # e.g. "product titles, prices, ratings, and product links"
    reason: str = ""


class SelectAction(BaseModel):
    """
    Choose an option from a <select> dropdown.

    Why separate from ClickAction?
    Dropdowns need page.select_option() — not a click.
    Clicking a <select> opens it but doesn't choose a value.
    select_option() sets the value directly, which is more reliable.
    """
    action: Literal["select"]
    element_description: str   # e.g. "the country dropdown", "delivery time select"
    option: str                # the option label or value to choose, e.g. "India", "18:45-19:45"
    reason: str = ""


class CheckAction(BaseModel):
    """
    Check or uncheck a checkbox, or select a radio button.

    Why separate from ClickAction?
    Checkboxes and radios need state awareness — clicking a checkbox
    that's already checked would uncheck it (wrong). We check current
    state first, then act only if needed.

    Also, radio buttons are found by their label text, not their value
    attribute — the AI knows "Large" not "large" (the HTML value).
    """
    action: Literal["check"]
    element_description: str  # e.g. "the Large radio button", "the cheese topping checkbox"
    check: bool = True        # True = check/select it, False = uncheck it
    reason: str = ""


class WaitAction(BaseModel):
    """Wait for something to appear on the page."""
    action: Literal["wait"]
    for_what: str = "page to load"   # natural language: "search results to load"
    timeout_ms: int = 3000
    reason: str = ""


class DoneAction(BaseModel):
    """
    The agent signals it has completed the task.

    The `result` field contains the final structured output.
    `summary` is a human-readable explanation of what was accomplished.
    """
    action: Literal["done"]
    result: dict = Field(default_factory=dict)
    summary: str = ""


# Discriminated union — Pydantic uses the `action` field to pick the right model
AgentAction = Annotated[
    Union[
        NavigateAction,
        ClickAction,
        TypeAction,
        SelectAction,
        CheckAction,
        ScrollAction,
        ExtractAction,
        WaitAction,
        DoneAction,
    ],
    Field(discriminator="action")
]


# Human-readable descriptions of each action (used in prompts)
ACTION_DESCRIPTIONS = {
    "navigate": "Go to a URL. Use this to open a website or a specific page.",
    "click":    "Click a button, link, or any element. Describe it in plain English.",
    "type":     "Type text into a text input, email field, textarea, or time picker.",
    "select":   "Choose an option from a <select> dropdown by its visible label.",
    "check":    "Check or select a checkbox or radio button by its label.",
    "scroll":   "Scroll the page up or down to reveal more content.",
    "extract":  "Extract structured data from the current page content.",
    "wait":     "Wait for content to load before proceeding.",
    "done":     "Task is complete. Return the final result.",
}
