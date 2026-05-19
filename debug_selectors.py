"""
Selector discovery script.

Run this to see what Amazon's current DOM actually looks like.
This is how you build extractors — inspect first, code second.
"""
import asyncio
from browser.engine import browser_engine
from browser.navigator import navigate_to, take_screenshot


async def discover_amazon_selectors():
    await browser_engine.start()

    try:
        async with browser_engine.new_page() as page:
            print("Navigating to Amazon search...")
            url = "https://www.amazon.in/s?k=gaming+laptop"
            await navigate_to(page, url)

            # Give JS time to render
            await page.wait_for_timeout(3000)

            # Save screenshot so we can see what loaded
            await take_screenshot(page, "amazon_search.png")

            # Check which selectors are present
            selectors_to_test = {
                "product cards":      '[data-component-type="s-search-result"]',
                "title (option A)":   'h2.a-size-mini span',
                "title (option B)":   'h2 a span.a-text-normal',
                "price offscreen":    '.a-price .a-offscreen',
                "price whole":        '.a-price-whole',
                "rating":             '.a-icon-alt',
                "review count":       '.s-underline-text',
                "product link":       'h2 a[href]',
            }

            print("\n--- Selector Availability ---")
            for name, selector in selectors_to_test.items():
                count = await page.locator(selector).count()
                status = f"✓ {count} found" if count > 0 else "✗ NOT FOUND"
                print(f"  {name:25s}: {status}   [{selector}]")

            # Print the raw text of first product card to understand structure
            print("\n--- First Product Card HTML (truncated) ---")
            first_card = page.locator('[data-component-type="s-search-result"]').first
            card_count = await page.locator('[data-component-type="s-search-result"]').count()
            if card_count > 0:
                text = await first_card.inner_text()
                print(text[:500])

    finally:
        await browser_engine.stop()


if __name__ == "__main__":
    asyncio.run(discover_amazon_selectors())
