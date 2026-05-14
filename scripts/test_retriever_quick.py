"""
scripts/test_retriever_quick.py — Quick verification of retriever functionality.

Purpose:
    Tests that the retriever initializes correctly, builds the FAISS index,
    and returns relevant results for sample queries.

When this was used:
    Phase 3, Step 3.3 — after writing retriever.py

How to run:
    python scripts/test_retriever_quick.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retriever import Retriever

print("=" * 60)
print("RETRIEVER QUICK TEST")
print("=" * 60)

# Test 1: Initialize retriever
print("\n1. Initializing retriever...")
start = time.time()
retriever = Retriever(catalog_path="data/catalog.json")
init_time = time.time() - start
print(f"   Init time: {init_time:.1f}s")
assert init_time < 120, f"Init too slow: {init_time:.1f}s (max 120s)"

# Test 2: Search for Java developer
print("\n2. Search: 'java developer programming test'")
start = time.time()
results = retriever.search("java developer programming test", top_k=5)
search_time = time.time() - start
print(f"   Search time: {search_time*1000:.0f}ms")
print(f"   Results ({len(results)}):")
for r in results:
    print(f"     - {r['name']} | type={r['test_type']} | score={r['score']:.3f}")
assert len(results) == 5, f"Expected 5 results, got {len(results)}"
assert search_time < 5, f"Search too slow: {search_time:.1f}s (max 5s)"

# Test 3: Search for personality assessment
print("\n3. Search: 'personality assessment leadership'")
results = retriever.search("personality assessment leadership", top_k=5)
print(f"   Results ({len(results)}):")
for r in results:
    print(f"     - {r['name']} | type={r['test_type']} | score={r['score']:.3f}")

# Test 4: Search for numerical reasoning
print("\n4. Search: 'numerical reasoning data analysis'")
results = retriever.search("numerical reasoning data analysis", top_k=5)
print(f"   Results ({len(results)}):")
for r in results:
    print(f"     - {r['name']} | type={r['test_type']} | score={r['score']:.3f}")

# Test 5: Search for customer service
print("\n5. Search: 'customer service communication skills'")
results = retriever.search("customer service communication skills", top_k=5)
print(f"   Results ({len(results)}):")
for r in results:
    print(f"     - {r['name']} | type={r['test_type']} | score={r['score']:.3f}")

# Test 6: get_all_entries
print("\n6. get_all_entries()")
all_entries = retriever.get_all_entries()
print(f"   Total entries: {len(all_entries)}")
assert len(all_entries) == 377, f"Expected 377, got {len(all_entries)}"

# Test 7: Results ordered by score
print("\n7. Verifying results are ordered by descending score...")
results = retriever.search("SQL database", top_k=10)
scores = [r["score"] for r in results]
assert scores == sorted(scores, reverse=True), "Results not ordered by score!"
print(f"   Scores: {[f'{s:.3f}' for s in scores]}")
print("   Ordered correctly ✓")

print("\n" + "=" * 60)
print("ALL RETRIEVER TESTS PASSED ✓")
print("=" * 60)
