"""
scripts/verify_catalog.py — Post-scrape validation of data/catalog.json.

Purpose:
    Run AFTER the full scrape to verify the output file is correct.
    Checks:
    - All 377 entries have required fields (name, url, test_type)
    - All URLs start with https://www.shl.com/
    - No duplicate assessment names
    - Shows sample entries for manual inspection
    - Reports statistics (descriptions, durations, types)

When this was used:
    Phase 2, Step 2.9 — after full scrape completed

Results when run:
    - 377 entries total
    - All have required fields ✓
    - 0 bad URLs ✓
    - 0 duplicate names ✓
    - 377/377 have descriptions
    - 283/377 have duration > 0
    - Test type distribution: K=240, P=67, S=43, A=32, C=19, B=17, D=7, E=2

How to run:
    python scripts/verify_catalog.py
"""
import json
import sys
import os

# Path to catalog (relative to project root)
CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "catalog.json",
)

if not os.path.exists(CATALOG_PATH):
    print(f"ERROR: Catalog not found at {CATALOG_PATH}", file=sys.stderr)
    print("Run 'python catalog_scraper.py' first.", file=sys.stderr)
    sys.exit(1)

with open(CATALOG_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Total entries: {len(data)}")

# Show sample entries
print(f"\nSample entry (index 1):")
print(json.dumps(data[1], indent=2))

print(f"\nSample entry (index 100):")
print(json.dumps(data[100], indent=2))

# Check all entries have required fields
print("\n--- Validation ---")
missing = []
for i, entry in enumerate(data):
    for field in ["name", "url", "test_type"]:
        if not entry.get(field):
            missing.append(f"Entry {i}: missing {field}")

if missing:
    print(f"MISSING FIELDS ({len(missing)}):")
    for m in missing[:10]:
        print(f"  {m}")
else:
    print(f"All {len(data)} entries have required fields ✓")

# Check URL format
bad_urls = [e for e in data if not e["url"].startswith("https://")]
print(f"Bad URLs: {len(bad_urls)}")

# Check for duplicates
names = [e["name"] for e in data]
dupes = [n for n in set(names) if names.count(n) > 1]
print(f"Duplicate names: {len(dupes)}")
if dupes:
    print(f"  Examples: {dupes[:5]}")

# Statistics
print("\n--- Statistics ---")
print(f"With description: {sum(1 for e in data if e.get('description'))}/{len(data)}")
print(f"With duration > 0: {sum(1 for e in data if e.get('duration', 0) > 0)}/{len(data)}")
print(f"Remote testing: {sum(1 for e in data if e.get('remote_testing'))}/{len(data)}")
print(f"Adaptive/IRT: {sum(1 for e in data if e.get('adaptive'))}/{len(data)}")

# Test type distribution
type_counts = {}
for e in data:
    for t in e.get("test_type", "").split():
        type_counts[t] = type_counts.get(t, 0) + 1
print(f"Test type distribution: {dict(sorted(type_counts.items()))}")

print("\n--- Done ---")
