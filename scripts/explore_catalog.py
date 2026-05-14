"""
scripts/explore_catalog.py — HTML structure exploration for SHL catalog.

Purpose:
    This script was used during development to investigate the HTML structure
    of the SHL product catalog page BEFORE writing the scraper. It helped us
    discover:
    - The page has 2 tables: Pre-packaged Job Solutions (type=2) and
      Individual Test Solutions (type=1)
    - Remote testing is indicated by <span class="catalogue__circle -yes">
    - Adaptive/IRT uses the same span indicator
    - Test types are concatenated letter codes in the text cell
    - Assessment names are links with href="/products/product-catalog/view/{slug}/"
    - Plain requests get 403 (CloudFront) — need browser User-Agent header

When this was used:
    Phase 2, Step 2.4 — before writing catalog_scraper.py

How to run:
    python scripts/explore_catalog.py
"""
import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# Check multiple pages to find entries with remote testing / adaptive checkmarks
for page_start in [0, 12, 24]:
    url = f"https://www.shl.com/solutions/products/product-catalog/?start={page_start}&type=1"
    r = requests.get(url, headers=headers, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")

    tables = soup.find_all("table")
    if len(tables) < 2:
        continue

    # Table 1 = Individual Test Solutions
    table = tables[1]
    rows = table.find_all("tr")[1:]  # Skip header

    print(f"\n--- Page start={page_start} ({len(rows)} rows) ---")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 4:
            name_cell = cells[0]
            remote_cell = cells[1]
            adaptive_cell = cells[2]
            type_cell = cells[3]

            link = name_cell.find("a")
            name = name_cell.get_text(strip=True)
            href = link.get("href", "") if link else ""

            # Check for any content in remote/adaptive cells
            remote_html = str(remote_cell)[:200]
            adaptive_html = str(adaptive_cell)[:200]
            remote_text = remote_cell.get_text(strip=True)
            adaptive_text = adaptive_cell.get_text(strip=True)
            has_remote_span = remote_cell.find("span") is not None
            has_adaptive_span = adaptive_cell.find("span") is not None

            test_type = type_cell.get_text(strip=True)

            # Print all rows with their indicators
            if has_remote_span or has_adaptive_span or remote_text or adaptive_text:
                print(f"  '{name}' | remote={remote_text!r} span={has_remote_span} | adaptive={adaptive_text!r} span={has_adaptive_span} | type={test_type}")
                print(f"    remote_html: {remote_html}")
                print(f"    adaptive_html: {adaptive_html}")
            else:
                print(f"  '{name}' | remote=NO | adaptive=NO | type={test_type}")
