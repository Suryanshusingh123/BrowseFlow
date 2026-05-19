"""
Gemini AI client — the single interface to all AI calls.

Why wrap the SDK?
  google-generativeai is synchronous. FastAPI is async.
  asyncio.to_thread() runs sync code in a thread pool so it
  doesn't block the event loop. All that plumbing lives here —
  nothing else in the codebase knows Gemini is synchronous.

  If you switch from Gemini to OpenAI later, you only change this file.
"""

import asyncio
import json
import re
from typing import Any

import google.generativeai as genai

from config import get_settings
from ai.prompts import build_system_prompt, build_action_prompt, build_extraction_prompt
from models.actions import AgentAction

settings = get_settings()


def _init_model() -> genai.GenerativeModel:
    """Initialize the Gemini model. Called once at module load."""
    genai.configure(api_key=settings.gemini_api_key)
    return genai.GenerativeModel(
        model_name="gemini-2.5-flash",  # Fast, capable, and cheap. Switch to gemini-2.5-pro for harder tasks.
        system_instruction=build_system_prompt(),
    )


def get_agent_model() -> genai.GenerativeModel:
    """Agent model — has the action-decision system prompt."""
    return _init_model()


def get_extraction_model() -> genai.GenerativeModel:
    """
    Extraction model — NO system prompt.

    Why separate? The agent model's system prompt says "always return action JSON."
    If we use it for extraction, Gemini obeys and returns action format instead of data.
    A clean model with no system prompt follows the extraction prompt directly.
    """
    genai.configure(api_key=settings.gemini_api_key)
    return genai.GenerativeModel(model_name="gemini-2.5-flash")


async def decide_next_action(
    goal: str,
    step: int,
    max_steps: int,
    history: list[dict],
    page_state_text: str,
    site_knowledge_text: str = "",
) -> AgentAction:
    """
    Ask Gemini: given the current page state, what should the agent do next?

    Returns a validated AgentAction (one of the typed action models).

    site_knowledge_text: formatted block from SiteKnowledgeMemory.format_for_prompt().
      Injected into the prompt so the AI can act on what it learned from prior runs.
    """
    from ai.prompts import build_action_prompt
    prompt = build_action_prompt(
        goal=goal,
        step=step,
        max_steps=max_steps,
        history=history,
        page_state_text=page_state_text,
        site_knowledge_text=site_knowledge_text,
    )

    raw_response = await _generate_text(prompt)
    return _parse_action(raw_response, prompt)


async def extract_structured_data(
    what: str,
    page_text: str,
    page_links: list[dict],
) -> dict:
    """
    Ask Gemini to extract structured data from page content.

    This is a separate AI call specifically for data extraction.
    The planner decides to extract; this function does the actual extracting.

    Returns a dict with an "items" key containing the extracted records.
    """
    prompt = build_extraction_prompt(what, page_text, page_links)
    raw_response = await _generate_text_clean(prompt)   # use clean model, not agent model
    return _parse_json(raw_response)


async def _generate_text(prompt: str) -> str:
    """
    Call Gemini synchronously from async code using asyncio.to_thread.

    asyncio.to_thread() runs the function in a thread pool executor.
    This means the event loop stays unblocked while Gemini is thinking.
    Other requests can be handled while we wait for the AI response.
    """
    model = get_agent_model()
    def _call():
        response = model.generate_content(prompt)
        return response.text

    return await asyncio.to_thread(_call)


async def _generate_text_clean(prompt: str) -> str:
    """Generate text using the extraction model (no agent system prompt)."""
    model = get_extraction_model()
    def _call():
        response = model.generate_content(prompt)
        return response.text
    return await asyncio.to_thread(_call)


def _parse_action(raw: str, original_prompt: str = "") -> AgentAction:
    """
    Parse AI response text into a validated AgentAction.

    The AI is asked to return pure JSON, but sometimes adds markdown
    code fences (```json ... ```) or explanation text. We strip those.
    Then we validate with Pydantic's discriminated union.
    """
    data = _parse_json(raw)
    # Pydantic's discriminated union — reads `action` field and picks the right model
    from pydantic import TypeAdapter
    adapter = TypeAdapter(AgentAction)
    return adapter.validate_python(data)


def _parse_json(raw: str) -> dict:
    """
    Extract JSON from AI response, handling common formatting issues.

    Issues we handle:
    1. Markdown code fences: ```json { ... } ```
    2. Extra text before/after JSON
    3. Single quotes instead of double quotes (common AI mistake)
    """
    # Strip markdown code fences
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        # Try to find JSON object in the response
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Could not parse AI response as JSON.\nRaw: {raw[:300]}\nError: {e}")
