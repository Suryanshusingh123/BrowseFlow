"""
Phase 2 validation: Test extraction pipeline end-to-end without FastAPI.

Run: python test_extraction.py

Tests the full chain:
  orchestrator → browser engine → amazon extractor → Product models
"""
import asyncio
import json
from browser.engine import browser_engine
from agent.orchestrator import run_search
from models.schemas import SearchRequest


async def test_amazon_extraction():
    print("\n=== Phase 2 Extraction Test ===\n")

    await browser_engine.start()

    try:
        request = SearchRequest(
            query="gaming laptop under 90000",
            site="amazon",
            max_results=5
        )

        print(f"Searching: '{request.query}' on {request.site}...")
        response = await run_search(request)

        if not response.success:
            print(f"✗ Search failed: {response.error}")
            return

        print(f"\n✓ Success! Found {response.data.total_found} products\n")
        print("=" * 60)

        for i, product in enumerate(response.data.products, 1):
            print(f"\nProduct {i}:")
            print(f"  Title  : {product.title[:70]}...")
            print(f"  Price  : {product.price}")
            print(f"  Rating : {product.rating}")
            print(f"  Reviews: {product.num_reviews}")
            print(f"  Link   : {product.link}")

        print("\n" + "=" * 60)
        print("\nFull JSON response (what the API will return):")
        print(json.dumps(response.model_dump(), indent=2, ensure_ascii=False)[:2000])

    finally:
        await browser_engine.stop()


if __name__ == "__main__":
    asyncio.run(test_amazon_extraction())
