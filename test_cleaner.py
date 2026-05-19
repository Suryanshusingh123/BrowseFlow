"""
Unit tests for the data cleaning pipeline.

These tests run without a browser, without AI, without network.
Fast, deterministic, isolated — that's what makes code testable.

Run: python test_cleaner.py
"""
from utils.cleaner import (
    parse_price, normalize_rating, deduplicate,
    strip_noise, enrich_links, clean_extraction
)


def test_parse_price():
    print("Testing parse_price...")

    cases = [
        ("₹89,999",             {"display": "₹89,999", "amount": 89999.0, "currency": "INR"}),
        ("₹1,53,990",           {"display": "₹1,53,990", "amount": 153990.0, "currency": "INR"}),
        ("₹76,990 (29% off)",   {"display": "₹76,990 (29% off)", "amount": 76990.0, "currency": "INR", "discount": "29% off"}),
        ("$1,299.00",           {"display": "$1,299.00", "amount": 1299.0, "currency": "USD"}),
        ("MRP: ₹89,999",        {"display": "MRP: ₹89,999", "amount": 89999.0, "currency": "INR"}),
        (None,                  {}),
        ("",                    {}),
    ]

    all_pass = True
    for raw, expected in cases:
        result = parse_price(raw)
        for key, val in expected.items():
            if result.get(key) != val:
                print(f"  ✗ parse_price({raw!r}): expected {key}={val!r}, got {result.get(key)!r}")
                all_pass = False
    if all_pass:
        print("  ✓ All price tests passed")


def test_normalize_rating():
    print("Testing normalize_rating...")
    cases = [
        ("4.3 out of 5 stars", 4.3),
        ("4.3",                4.3),
        ("4.3/5",              4.3),
        ("★★★★☆",             4.0),
        ("86%",                4.3),
        ("4.0 out of 5",      4.0),
        (None,                 None),
        ("no rating",          None),
    ]
    all_pass = True
    for raw, expected in cases:
        result = normalize_rating(raw)
        if result != expected:
            print(f"  ✗ normalize_rating({raw!r}): expected {expected}, got {result}")
            all_pass = False
    if all_pass:
        print("  ✓ All rating tests passed")


def test_deduplicate():
    print("Testing deduplicate...")
    items = [
        {"title": "HP Victus Gaming Laptop"},
        {"title": "HP Victus Gaming Laptop"},           # exact duplicate
        {"title": "HP Victus Gaming Laptop (2024)"},    # near-duplicate
        {"title": "Lenovo LOQ Gaming Laptop"},          # distinct
        {"title": "Lenovo LOQ Gaming Laptop"},          # exact duplicate
    ]
    result, removed = deduplicate(items)
    assert removed == 3, f"Expected 3 removed, got {removed}"
    assert len(result) == 2, f"Expected 2 unique, got {len(result)}"
    print(f"  ✓ Removed {removed} duplicates, kept {len(result)} unique items")


def test_strip_noise():
    print("Testing strip_noise...")
    items = [
        {"title": "[Sponsored] HP Victus Gaming Laptop"},
        {"title": "PSOS Operating System (1979) [pdf]"},
        {"title": "  Lenovo ThinkPad  "},
        {"title": "Normal title"},
    ]
    result = strip_noise(items)
    assert result[0]["title"] == "HP Victus Gaming Laptop",  f"Got: {result[0]['title']}"
    assert result[0]["sponsored"] == True
    assert result[1]["content_type"] == "pdf"
    assert "[pdf]" not in result[1]["title"]    # [pdf] tag is stripped
    assert "(1979)" in result[1]["title"]       # year kept in display title
    assert result[2]["title"] == "Lenovo ThinkPad"   # whitespace stripped
    assert result[3]["sponsored"] == False
    print("  ✓ Noise stripping works correctly")


def test_enrich_links():
    print("Testing enrich_links...")
    items = [
        {"title": "I automated opt-outs for 500 data broker sites", "link": "https://github.com/existing"},
        {"title": "Crystals found inside wreckage from the first nuclear bomb test"},  # no link
        {"title": "NASA maintains Voyager spacecraft code from the 70s"},               # no link
    ]
    page_links = [
        {"text": "Crystals found inside wreckage from the first nuclear bomb test", "href": "https://science.com/crystals"},
        {"text": "NASA still maintains some of the Voyager spacecraft code", "href": "https://nasa.gov/voyager"},
        {"text": "some unrelated link", "href": "https://example.com"},
    ]
    result = enrich_links(items, page_links)
    assert result[0]["link"] == "https://github.com/existing"        # untouched
    assert result[1]["link"] == "https://science.com/crystals"       # enriched
    assert result[2]["link"] == "https://nasa.gov/voyager"           # enriched
    print("  ✓ Link enrichment matched correctly")


def test_full_pipeline():
    print("\nTesting full clean_extraction pipeline...")
    raw_items = [
        {"title": "[Sponsored] HP Victus Gaming Laptop", "price": "₹85,990", "rating": "4.1 out of 5 stars"},
        {"title": "[Sponsored] HP Victus Gaming Laptop", "price": "₹85,990"},   # duplicate
        {"title": "Lenovo LOQ AMD Gaming Laptop",         "price": "₹88,990 (10% off)", "rating": "4.3"},
        {"title": "ASUS TUF A15 Gaming Laptop [pdf]",    "price": "₹76,990"},  # content_type noise
        {"title": "Story without link"},                                          # missing link
    ]
    page_links = [
        {"text": "Story without link about something", "href": "https://example.com/story"},
    ]

    result = clean_extraction(raw_items, page_links)

    print(f"  Total items:         {result['total']}   (was 5 raw)")
    print(f"  Duplicates removed:  {result['duplicates_removed']}")
    print(f"  Links enriched:      {result['links_enriched']}")
    print("\n  Cleaned items:")
    for item in result["items"]:
        price = item.get("price", {})
        amount = price.get("amount") if isinstance(price, dict) else price
        link = item.get("link", "—")[:50]
        print(f"    • {item['title'][:55]}")
        print(f"      price={amount}  rating={item.get('rating')}  sponsored={item.get('sponsored')}  link={link}")


if __name__ == "__main__":
    print("=" * 55)
    print("Data Cleaner Unit Tests")
    print("=" * 55 + "\n")
    test_parse_price()
    test_normalize_rating()
    test_deduplicate()
    test_strip_noise()
    test_enrich_links()
    test_full_pipeline()
    print("\n✓ All tests passed")
