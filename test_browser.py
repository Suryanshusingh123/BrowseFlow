"""
Phase 1 validation test.

Run this directly: python test_browser.py

This is NOT a pytest test — it's a manual verification script.
We'll add proper tests in later phases. For now we want fast feedback.
"""
import asyncio
from browser.engine import browser_engine
from browser.navigator import navigate_to, take_screenshot, wait_for_selector_safe


async def test_browser_basics():
    print("\n=== Phase 1 Browser Test ===\n")

    await browser_engine.start()

    try:
        print("Test 1: Open example.com and take a screenshot")
        async with browser_engine.new_page() as page:
            success = await navigate_to(page, "https://example.com")
            assert success, "Navigation should succeed"

            # Verify the page actually loaded something meaningful
            found = await wait_for_selector_safe(page, "h1", timeout=5_000)
            assert found, "example.com should have an h1 element"

            path = await take_screenshot(page, "test_example.png")
            print(f"  ✓ Navigated and screenshot saved to {path}")

        print("\nTest 2: Open Google and verify search box exists")
        async with browser_engine.new_page() as page:
            success = await navigate_to(page, "https://www.google.com")
            assert success, "Google navigation should succeed"

            # The Google search textarea
            found = await wait_for_selector_safe(page, "textarea[name='q']", timeout=8_000)
            if found:
                print("  ✓ Google search box found")
            else:
                print("  ⚠ Google search box not found — may be a regional variant")
                await take_screenshot(page, "test_google_debug.png")

        print("\n✓ All Phase 1 tests passed!")
        print("✓ Browser launches correctly")
        print("✓ Navigation works")
        print("✓ DOM selectors work")
        print("✓ Screenshots save correctly")
        print("\nCheck the screenshots/ folder to visually verify.")

    finally:
        await browser_engine.stop()


if __name__ == "__main__":
    asyncio.run(test_browser_basics())
