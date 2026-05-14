"""
scripts/test_scraper_quick.py — Quick validation of scraper before full run.

Purpose:
    This script tests the catalog scraper on just 2 pages (24 entries) + 2 detail
    pages to verify everything works BEFORE committing to the full 10-minute scrape.
    It validates:
    - Listing page parsing works (gets 12 entries per page)
    - Detail page parsing works (gets description and duration)
    - All required fields are present
    - URLs are correctly formed

When this was used:
    Phase 2, Step 2.7 — after writing catalog_scraper.py, before full scrape

Results when run:
    - Page 0: 12 entries ✓
    - Page 1: 12 entries ✓
    - Detail page 1: description extracted, duration=0 (not specified) ✓
    - Detail page 2: description extracted, duration=30 ✓
    - All 24 entries valid ✓

How to run:
    python scripts/test_scraper_quick.py
"""
import sys
import os

# Add parent directory to path so we can import catalog_scraper
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from catalog_scraper import scrape_listing_page, scrape_detail_page, validate_catalog

print("=" * 50)
print("QUICK SCRAPER TEST (2 pages + 2 detail pages)")
print("=" * 50)

# Test listing page 0
print("\n1. Scraping listing page 0...")
entries_p0 = scrape_listing_page(0)
print(f"   Got {len(entries_p0)} entries")
assert len(entries_p0) == 12, f"Expected 12, got {len(entries_p0)}"

# Test listing page 1
print("\n2. Scraping listing page 12...")
entries_p1 = scrape_listing_page(12)
print(f"   Got {len(entries_p1)} entries")
assert len(entries_p1) == 12, f"Expected 12, got {len(entries_p1)}"

all_entries = entries_p0 + entries_p1
print(f"\n   Total from 2 pages: {len(all_entries)}")

# Show first 5 entries
print("\n3. First 5 entries (from listing):")
for e in all_entries[:5]:
    print(f"   - {e['name']} | type={e['test_type']} | remote={e['remote_testing']} | adaptive={e['adaptive']}")
    print(f"     URL: {e['url']}")

# Test detail page for first entry
print(f"\n4. Fetching detail page for: {all_entries[0]['name']}")
detail = scrape_detail_page(all_entries[0]["url"])
print(f"   Description: {detail['description'][:150]}...")
print(f"   Duration: {detail['duration']} minutes")

# Test detail page for second entry
print(f"\n5. Fetching detail page for: {all_entries[1]['name']}")
detail2 = scrape_detail_page(all_entries[1]["url"])
print(f"   Description: {detail2['description'][:150]}...")
print(f"   Duration: {detail2['duration']} minutes")
assert detail2["duration"] == 30, f"Expected 30, got {detail2['duration']}"

# Validate
print("\n6. Validation check:")
is_valid = validate_catalog(all_entries)
assert is_valid, "Validation failed!"

print("\n" + "=" * 50)
print("ALL QUICK TESTS PASSED ✓")
print("=" * 50)
