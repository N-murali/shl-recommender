# scripts/ — Development Utilities

These scripts were used during development to explore, test, and verify
the catalog scraper. They are NOT part of the main application but serve
as proof-of-work showing the methodical development process.

## Files

| Script | Phase | Purpose |
|--------|-------|---------|
| `explore_catalog.py` | Phase 2, Step 2.4 | Investigated SHL page HTML structure before writing scraper |
| `test_scraper_quick.py` | Phase 2, Step 2.7 | Quick 2-page test before committing to full 10-min scrape |
| `verify_catalog.py` | Phase 2, Step 2.9 | Post-scrape validation of data/catalog.json |

## Why These Exist

1. **explore_catalog.py** — We needed to understand the HTML structure before
   writing selectors. This script discovered: table layout, CSS classes for
   checkmarks (`catalogue__circle -yes`), link patterns, and that CloudFront
   blocks plain requests (need browser User-Agent).

2. **test_scraper_quick.py** — The full scrape takes ~10 minutes. This script
   tests on just 2 pages (24 entries) to catch bugs early. It verified:
   listing parsing, detail page parsing, field extraction, and validation.

3. **verify_catalog.py** — After the full scrape, this confirms the output
   is correct: all required fields present, valid URLs, no duplicates,
   reasonable statistics.

## How to Run

```bash
# From project root:
python scripts/explore_catalog.py
python scripts/test_scraper_quick.py
python scripts/verify_catalog.py
```
