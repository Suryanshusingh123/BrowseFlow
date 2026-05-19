"""
End-to-end agent test — the real thing.

Run: python test_agent.py

The agent will:
1. Open a browser
2. Navigate to Amazon India
3. Search for gaming laptops
4. Extract product data
5. Return structured JSON

No hardcoded selectors. No Amazon-specific code.
The AI figures it all out from the page content.
"""
import asyncio
import json
from browser.engine import browser_engine
from agent.loop import run_agent_loop


async def main():
    print("\n" + "="*60)
    print("AI BROWSER AGENT — End-to-End Test")
    print("="*60)

    await browser_engine.start()

    try:
        async with browser_engine.new_page() as page:
            result = await run_agent_loop(
                goal=(
                    "Go to amazon.in and search for 'gaming laptop'. "
                    "Once the search results page loads, extract the first 5 products visible on the page. "
                    "For each product extract: title, price, rating, and product link. "
                    "Do NOT try to apply any filters. Just extract what is already visible on the results page."
                ),
                page=page,
                max_steps=10,
            )

        print("\n" + "="*60)
        print(f"SUCCESS: {result['success']}")
        print(f"SUMMARY: {result['summary']}")
        print(f"STEPS:   {result['steps_taken']}")
        print("="*60)

        if result["result"]:
            print("\nEXTRACTED DATA:")
            print(json.dumps(result["result"], indent=2, ensure_ascii=False))

        print("\nSTEP-BY-STEP HISTORY:")
        for step in result.get("history", []):
            status = "✓" if step["success"] else "✗"
            print(f"  {status} Step {step['step']}: [{step['action']}] {step['outcome'][:80]}")

    finally:
        await browser_engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
