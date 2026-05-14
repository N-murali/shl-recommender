"""
catalog_scraper.py — Scrapes SHL product catalog and saves to data/catalog.json.

What this file does:
    Extracts all Individual Test Solutions from the SHL product catalog website.
    For each assessment, it collects: name, URL, test_type, description,
    duration, remote_testing, and adaptive flags from both the listing pages
    and individual detail pages.

Why these decisions:
    - Two-pass approach: first scrape listing pages (fast, gets name/url/type/flags),
      then scrape detail pages (slower, gets description/duration).
    - Browser-like User-Agent header required — SHL uses CloudFront which blocks
      plain requests (returns 403).
    - Rate limiting (1 second between requests) to be respectful to the server.
    - Pagination follows ?start=N&type=1 pattern (12 items per page, type=1 = Individual Tests).
    - Skips entries with missing required fields (name, url, test_type) with a warning.

What breaks if this file is wrong:
    - Wrong URL pattern → misses pages → incomplete catalog → poor recommendations.
    - Wrong HTML selectors → fails to parse entries → empty catalog.
    - No User-Agent → 403 from CloudFront → no data at all.
    - Wrong test_type parsing → incorrect type codes → evaluator marks as wrong.
"""

import json
import os
import re
import sys
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ============================================================
# Constants
# ============================================================

BASE_URL = "https://www.shl.com"
CATALOG_URL = f"{BASE_URL}/solutions/products/product-catalog/"
CATALOG_LISTING_URL = f"{BASE_URL}/solutions/products/product-catalog/"
OUTPUT_PATH = "data/catalog.json"

# Browser-like headers to bypass CloudFront blocking
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Delay between requests to be respectful to the server
REQUEST_DELAY = 1.0  # seconds

# HTTP timeout for each request
REQUEST_TIMEOUT = 30  # seconds

# Items per page on the SHL catalog
ITEMS_PER_PAGE = 12


def fetch_page(url: str) -> Optional[BeautifulSoup]:
    """
    Fetch a URL and return parsed BeautifulSoup object.

    Args:
        url: The URL to fetch.

    Returns:
        BeautifulSoup object if successful, None if request fails.

    Side effects:
        Logs errors to stderr on failure.
        Sleeps REQUEST_DELAY seconds after each request.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return BeautifulSoup(response.text, "html.parser")
    except requests.exceptions.Timeout:
        print(f"ERROR: Timeout fetching {url}", file=sys.stderr)
        return None
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP {e.response.status_code} fetching {url}", file=sys.stderr)
        return None
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Request failed for {url}: {e}", file=sys.stderr)
        return None


def scrape_listing_page(page_start: int) -> list[dict]:
    """
    Scrape a single listing page of Individual Test Solutions.

    Args:
        page_start: The pagination offset (0, 12, 24, ...).

    Returns:
        List of partial catalog entries (name, url, test_type, remote_testing, adaptive).
        Returns empty list if page fetch fails.

    Notes:
        The catalog page has two tables:
        - Table 0: Pre-packaged Job Solutions (IGNORED)
        - Table 1: Individual Test Solutions (what we want)
    """
    url = f"{CATALOG_LISTING_URL}?start={page_start}&type=1"
    print(f"  Scraping listing page: start={page_start}")

    soup = fetch_page(url)
    if soup is None:
        return []

    # Find all tables on the page
    tables = soup.find_all("table")

    # We need at least 2 tables (Pre-packaged + Individual)
    # The Individual Test Solutions table is the second one (index 1)
    # But on paginated pages with type=1, it might be the only table or second
    individual_table = None
    for table in tables:
        header_row = table.find("tr")
        if header_row:
            header_text = header_row.get_text(strip=True)
            if "Individual Test Solutions" in header_text:
                individual_table = table
                break

    if individual_table is None:
        print(f"  WARNING: No Individual Test Solutions table found on page start={page_start}", file=sys.stderr)
        return []

    entries = []
    rows = individual_table.find_all("tr")[1:]  # Skip header row

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        entry = parse_listing_row(cells)
        if entry is not None:
            entries.append(entry)

    return entries


def parse_listing_row(cells: list) -> Optional[dict]:
    """
    Parse a single row from the Individual Test Solutions table.

    Args:
        cells: List of <td> elements from the row (4 cells expected).

    Returns:
        Dict with name, url, test_type, remote_testing, adaptive.
        Returns None if required fields (name, url, test_type) are missing.

    Notes:
        Cell layout:
        - cells[0]: Name (with <a> link)
        - cells[1]: Remote Testing (has <span class="catalogue__circle -yes"> if yes)
        - cells[2]: Adaptive/IRT (has <span class="catalogue__circle -yes"> if yes)
        - cells[3]: Test Type (letter codes like "K", "AEBCDP")
    """
    # Cell 0: Name and URL
    name_cell = cells[0]
    link = name_cell.find("a")
    if link is None:
        print(f"  WARNING: No link found in name cell, skipping row", file=sys.stderr)
        return None

    name = name_cell.get_text(strip=True)
    href = link.get("href", "")

    if not name:
        print(f"  WARNING: Empty name, skipping row", file=sys.stderr)
        return None

    # Build absolute URL
    if href.startswith("/"):
        url = BASE_URL + href
    elif href.startswith("http"):
        url = href
    else:
        print(f"  WARNING: Invalid href '{href}' for '{name}', skipping", file=sys.stderr)
        return None

    # Cell 1: Remote Testing
    remote_cell = cells[1]
    remote_testing = remote_cell.find("span", class_="catalogue__circle") is not None

    # Cell 2: Adaptive/IRT
    adaptive_cell = cells[2]
    adaptive = adaptive_cell.find("span", class_="catalogue__circle") is not None

    # Cell 3: Test Type (letter codes)
    type_cell = cells[3]
    test_type_raw = type_cell.get_text(strip=True)

    if not test_type_raw:
        print(f"  WARNING: Empty test_type for '{name}', skipping", file=sys.stderr)
        return None

    # Split concatenated type codes into space-separated format
    # e.g., "AEBCDP" → "A E B C D P", "K" → "K"
    test_type = " ".join(list(test_type_raw))

    return {
        "name": name,
        "url": url,
        "test_type": test_type,
        "remote_testing": remote_testing,
        "adaptive": adaptive,
    }


def scrape_detail_page(url: str) -> dict:
    """
    Scrape an individual assessment's detail page for description and duration.

    Args:
        url: The full URL of the assessment detail page.

    Returns:
        Dict with description (str) and duration (int, minutes).
        Returns defaults if page fetch fails or fields not found.

    Notes:
        Detail page structure:
        - Description: in a section after "Description" heading
        - Duration: text like "Approximate Completion Time in minutes = 30"
        - Job levels: in a section after "Job levels" heading
    """
    soup = fetch_page(url)
    if soup is None:
        return {"description": "", "duration": 0}

    description = ""
    duration = 0

    # Extract description — look for the Description section
    # The page has h4 headings for sections
    desc_heading = soup.find("h4", string=re.compile(r"Description", re.IGNORECASE))
    if desc_heading:
        # Get the next sibling paragraph(s)
        desc_parts = []
        sibling = desc_heading.find_next_sibling()
        while sibling and sibling.name not in ["h4", "h3", "h2", "h1"]:
            text = sibling.get_text(strip=True)
            if text:
                desc_parts.append(text)
            sibling = sibling.find_next_sibling()
        description = " ".join(desc_parts)

    # Truncate description to 2000 chars as per spec
    if len(description) > 2000:
        description = description[:2000]

    # Extract duration — look for "Approximate Completion Time in minutes"
    page_text = soup.get_text()
    duration_match = re.search(
        r"Approximate Completion Time in minutes\s*=\s*(\d+)", page_text
    )
    if duration_match:
        duration = int(duration_match.group(1))

    return {"description": description, "duration": duration}


def scrape_catalog() -> list[dict]:
    """
    Scrape the entire SHL Individual Test Solutions catalog.

    Returns:
        List of complete catalog entry dicts with all fields:
        name, url, test_type, description, competencies, duration,
        remote_testing, adaptive.

    Side effects:
        Prints progress to stdout.
        Prints warnings/errors to stderr.

    Notes:
        Two-pass approach:
        1. Scrape all listing pages to get basic info (name, url, type, flags)
        2. Scrape each detail page to get description and duration
    """
    print("=" * 60)
    print("SHL Catalog Scraper — Individual Test Solutions")
    print("=" * 60)

    # Pass 1: Scrape all listing pages
    print("\nPass 1: Scraping listing pages...")
    all_entries = []
    page_start = 0
    consecutive_empty = 0

    while True:
        entries = scrape_listing_page(page_start)

        if not entries:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                # Two consecutive empty pages means we've gone past the end
                print(f"  No more entries found. Stopping pagination.")
                break
        else:
            consecutive_empty = 0
            all_entries.extend(entries)

        page_start += ITEMS_PER_PAGE

        # Safety limit — the catalog has ~32 pages (384 entries)
        if page_start > 500:
            print(f"  Safety limit reached at start={page_start}. Stopping.")
            break

    print(f"\n  Found {len(all_entries)} entries from listing pages.")

    # Pass 2: Scrape detail pages for description and duration
    print(f"\nPass 2: Scraping {len(all_entries)} detail pages...")
    for i, entry in enumerate(all_entries):
        print(f"  [{i + 1}/{len(all_entries)}] {entry['name']}")
        detail = scrape_detail_page(entry["url"])
        entry["description"] = detail["description"]
        entry["duration"] = detail["duration"]
        # Competencies are not explicitly listed on the page as a separate field,
        # so we leave as empty list. The description contains relevant info
        # that the retriever will use for semantic matching.
        entry["competencies"] = []

    print(f"\nScraping complete. Total entries: {len(all_entries)}")
    return all_entries


def save_catalog(entries: list[dict], path: str = OUTPUT_PATH) -> None:
    """
    Save catalog entries to a JSON file.

    Args:
        entries: List of catalog entry dicts.
        path: Output file path (default: data/catalog.json).

    Side effects:
        Creates the output directory if it doesn't exist.
        Overwrites any existing file at the path.
    """
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(entries)} entries to {path}")
    print(f"File size: {os.path.getsize(path) / 1024:.1f} KB")


def validate_catalog(entries: list[dict]) -> bool:
    """
    Validate that scraped catalog entries have required fields.

    Args:
        entries: List of catalog entry dicts.

    Returns:
        True if all entries are valid, False otherwise.

    Side effects:
        Prints validation results to stdout.
    """
    print("\nValidating catalog...")
    required_fields = ["name", "url", "test_type"]
    issues = 0

    for i, entry in enumerate(entries):
        for field in required_fields:
            if field not in entry or not entry[field]:
                print(f"  ERROR: Entry {i} missing required field '{field}': {entry.get('name', 'UNKNOWN')}", file=sys.stderr)
                issues += 1

        # Validate URL format
        if not entry.get("url", "").startswith("https://"):
            print(f"  ERROR: Entry {i} has invalid URL: {entry.get('url', '')}", file=sys.stderr)
            issues += 1

    if issues == 0:
        print(f"  All {len(entries)} entries valid. ✓")
        return True
    else:
        print(f"  Found {issues} issues.", file=sys.stderr)
        return False


# ============================================================
# Main entry point — run scraper directly
# ============================================================

if __name__ == "__main__":
    try:
        entries = scrape_catalog()

        if not entries:
            print("ERROR: No entries scraped. Check network and selectors.", file=sys.stderr)
            sys.exit(1)

        # Validate before saving
        is_valid = validate_catalog(entries)

        # Save even if some entries have issues (partial catalog is better than none)
        save_catalog(entries)

        # Print summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total entries: {len(entries)}")
        print(f"With description: {sum(1 for e in entries if e.get('description'))}")
        print(f"With duration: {sum(1 for e in entries if e.get('duration', 0) > 0)}")
        print(f"Remote testing enabled: {sum(1 for e in entries if e.get('remote_testing'))}")
        print(f"Adaptive/IRT: {sum(1 for e in entries if e.get('adaptive'))}")

        # Show test_type distribution
        type_counts = {}
        for e in entries:
            for t in e.get("test_type", "").split():
                type_counts[t] = type_counts.get(t, 0) + 1
        print(f"Test type distribution: {dict(sorted(type_counts.items()))}")

        if not is_valid:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nScraping interrupted by user.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"FATAL ERROR: {e}", file=sys.stderr)
        sys.exit(1)
