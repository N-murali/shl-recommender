"""
tests/test_retriever.py — Retrieval system tests.

What this file does:
    Tests the Retriever class: initialization, search quality, error handling,
    and performance. Uses the real catalog.json for integration tests.

Why these decisions:
    - Tests with real catalog data (not mocked) to verify actual retrieval quality.
    - Tests error cases with temporary files (missing, invalid JSON).
    - Performance tests ensure search stays within budget.
"""

import json
import os
import tempfile
import time

import pytest

from retriever import Retriever


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(scope="module")
def retriever():
    """Create a Retriever instance with real catalog (shared across tests in module)."""
    catalog_path = "data/catalog.json"
    if not os.path.exists(catalog_path):
        pytest.skip("data/catalog.json not found — run catalog_scraper.py first")
    return Retriever(catalog_path=catalog_path)


@pytest.fixture
def small_catalog_path():
    """Create a temporary small catalog for isolated tests."""
    catalog = [
        {
            "name": "Java 8 (New)",
            "url": "https://www.shl.com/products/product-catalog/view/java-8-new/",
            "test_type": "K",
            "description": "Java programming knowledge test for experienced developers.",
            "duration": 30,
            "remote_testing": True,
            "adaptive": False,
            "competencies": [],
        },
        {
            "name": "OPQ32r",
            "url": "https://www.shl.com/products/product-catalog/view/opq32r/",
            "test_type": "P",
            "description": "Occupational personality questionnaire measuring workplace behavior.",
            "duration": 25,
            "remote_testing": True,
            "adaptive": False,
            "competencies": [],
        },
        {
            "name": "Verify - Numerical Ability",
            "url": "https://www.shl.com/products/product-catalog/view/verify-numerical-ability/",
            "test_type": "A",
            "description": "Numerical reasoning ability test measuring data interpretation.",
            "duration": 17,
            "remote_testing": True,
            "adaptive": True,
            "competencies": [],
        },
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(catalog, f)
        path = f.name
    yield path
    os.unlink(path)


# ============================================================
# Initialization tests
# ============================================================


class TestRetrieverInit:
    """Tests for Retriever initialization."""

    def test_init_with_real_catalog(self, retriever):
        """Retriever should initialize with real catalog."""
        assert retriever is not None
        assert len(retriever.catalog) > 0

    def test_init_with_small_catalog(self, small_catalog_path):
        """Retriever should initialize with a small test catalog."""
        r = Retriever(catalog_path=small_catalog_path)
        assert len(r.catalog) == 3
        assert r.index.ntotal == 3

    def test_missing_catalog_raises_error(self):
        """Missing catalog file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            Retriever(catalog_path="/nonexistent/path/catalog.json")

    def test_invalid_json_raises_error(self):
        """Invalid JSON should raise ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("this is not json{{{")
            path = f.name
        try:
            with pytest.raises(ValueError):
                Retriever(catalog_path=path)
        finally:
            os.unlink(path)

    def test_empty_catalog_raises_error(self):
        """Empty catalog should raise ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([], f)
            path = f.name
        try:
            with pytest.raises(ValueError):
                Retriever(catalog_path=path)
        finally:
            os.unlink(path)

    def test_missing_required_field_raises_error(self):
        """Catalog entry missing 'name' should raise ValueError."""
        catalog = [{"url": "https://shl.com/test/", "test_type": "K"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(catalog, f)
            path = f.name
        try:
            with pytest.raises(ValueError):
                Retriever(catalog_path=path)
        finally:
            os.unlink(path)


# ============================================================
# Search tests
# ============================================================


class TestRetrieverSearch:
    """Tests for Retriever.search() method."""

    def test_search_returns_results(self, retriever):
        """Search should return a non-empty list."""
        results = retriever.search("java developer")
        assert len(results) > 0

    def test_search_respects_top_k(self, retriever):
        """Search should return at most top_k results."""
        results = retriever.search("programming", top_k=5)
        assert len(results) == 5

    def test_search_top_k_1(self, retriever):
        """Search with top_k=1 should return exactly 1 result."""
        results = retriever.search("java", top_k=1)
        assert len(results) == 1

    def test_search_results_have_score(self, retriever):
        """Each result should have a 'score' field."""
        results = retriever.search("numerical reasoning", top_k=3)
        for r in results:
            assert "score" in r
            assert isinstance(r["score"], float)

    def test_search_results_ordered_by_score(self, retriever):
        """Results should be ordered by descending score."""
        results = retriever.search("customer service", top_k=10)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_results_have_required_fields(self, retriever):
        """Each result should have name, url, test_type."""
        results = retriever.search("personality", top_k=5)
        for r in results:
            assert "name" in r
            assert "url" in r
            assert "test_type" in r
            assert r["url"].startswith("https://")

    def test_search_java_returns_java_tests(self, retriever):
        """Searching 'java' should return Java-related assessments."""
        results = retriever.search("java programming developer", top_k=5)
        java_names = [r["name"] for r in results if "java" in r["name"].lower()]
        assert len(java_names) >= 1, f"Expected Java tests, got: {[r['name'] for r in results]}"

    def test_search_personality_returns_p_type(self, retriever):
        """Searching 'personality' should return P-type assessments."""
        results = retriever.search("personality questionnaire workplace behavior", top_k=5)
        p_types = [r for r in results if "P" in r["test_type"]]
        assert len(p_types) >= 1, f"Expected P-type, got: {[(r['name'], r['test_type']) for r in results]}"

    def test_search_empty_query(self, retriever):
        """Empty query should not crash (returns some results)."""
        results = retriever.search("", top_k=5)
        assert isinstance(results, list)

    def test_search_performance(self, retriever):
        """Search should complete within 5 seconds."""
        start = time.time()
        retriever.search("senior data analyst numerical reasoning", top_k=10)
        elapsed = time.time() - start
        assert elapsed < 5, f"Search took {elapsed:.2f}s (max 5s)"


# ============================================================
# get_all_entries tests
# ============================================================


class TestGetAllEntries:
    """Tests for Retriever.get_all_entries() method."""

    def test_returns_full_catalog(self, retriever):
        """get_all_entries should return all catalog entries."""
        entries = retriever.get_all_entries()
        assert len(entries) == len(retriever.catalog)

    def test_entries_have_required_fields(self, retriever):
        """All entries should have name, url, test_type."""
        entries = retriever.get_all_entries()
        for entry in entries:
            assert "name" in entry
            assert "url" in entry
            assert "test_type" in entry

    def test_small_catalog_returns_all(self, small_catalog_path):
        """Small catalog should return exactly 3 entries."""
        r = Retriever(catalog_path=small_catalog_path)
        entries = r.get_all_entries()
        assert len(entries) == 3
