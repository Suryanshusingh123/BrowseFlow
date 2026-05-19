"""
Form filling test — covers all major HTML input types.

The test form at httpbin.org/forms/post has:
  - text input     (customer name)
  - tel input      (phone number)
  - email input    (email address)
  - radio buttons  (pizza size: small / medium / large)
  - checkboxes     (toppings: bacon / cheese / onion / mushroom)
  - time input     (delivery time)
  - textarea       (special instructions)
  - submit button

After submit, httpbin echoes back exactly what was submitted as JSON.
We extract that JSON as proof the form was filled correctly.

Run: python test_form.py
"""
import asyncio
import json
from browser.engine import browser_engine
from agent.loop import run_agent_loop


async def main():
    print("\n" + "=" * 60)
    print("FORM FILLING TEST — httpbin.org pizza order form")
    print("=" * 60)

    await browser_engine.start()

    try:
        async with browser_engine.new_page() as page:
            result = await run_agent_loop(
                goal=(
                    "Go to https://httpbin.org/forms/post and fill out the pizza order form "
                    "with these details:\n"
                    "- Customer name: Suryanshu\n"
                    "- Phone: 9876543210\n"
                    "- Email: suryanshu@test.com\n"
                    "- Pizza size: Large (radio button)\n"
                    "- Topping: Cheese (checkbox)\n"
                    "- Delivery time: 19:00 (time input)\n"
                    "- Special instructions: Please ring the doorbell\n"
                    "After filling all fields, click the submit button. "
                    "Then extract the full response shown on the page (it will be JSON showing what was submitted)."
                ),
                page=page,
                max_steps=20,
            )

        print(f"\nSUCCESS: {result['success']}")
        print(f"SUMMARY: {result['summary']}")
        print(f"STEPS:   {result['steps_taken']}")

        print("\n--- STEP TRACE ---")
        for step in result.get("history", []):
            if step.get("action") == "system":
                print(f"  ⚠ SYSTEM: {step['outcome'][:80]}")
            else:
                icon = "✓" if step["success"] else "✗"
                print(f"  {icon} [{step['action']:8s}] {step['outcome'][:70]}")

        if result["result"]:
            print("\n--- EXTRACTED RESULT (what the server received) ---")
            print(json.dumps(result["result"], indent=2, ensure_ascii=False))

    finally:
        await browser_engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
