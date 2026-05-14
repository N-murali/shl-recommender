"""
retriever.py — FAISS vector store with sentence-transformers embeddings.

What this file does:
    Loads the scraped SHL catalog from data/catalog.json, generates embeddings
    for each entry using sentence-transformers (all-MiniLM-L6-v2), builds a
    FAISS index for cosine similarity search, and provides a search() method
    that returns the top-k most relevant catalog entries for a given query.

Why these decisions:
    - all-MiniLM-L6-v2: 384 dimensions, fast on CPU (~14ms per embedding),
      good semantic quality. Fits in Render free tier's 512MB memory.
    - FAISS IndexFlatIP: Exact search (no approximation). Catalog is small
      (~377 entries) so brute force is fast and accurate. Inner product on
      L2-normalized vectors = cosine similarity.
    - Text representation: "{name} | {test_type} | {description}" gives the
      embedding model rich context about what each assessment does.
    - No index persistence: Rebuilt from scratch at each startup. Avoids
      stale index issues and the catalog is small enough (~5 seconds to embed).

What breaks if this file is wrong:
    - Wrong embedding model → poor retrieval quality → bad recommendations.
    - Missing normalization → inner product ≠ cosine similarity → wrong ranking.
    - Wrong catalog path → FileNotFoundError at startup → service won't start.
    - Slow embedding → startup exceeds 120 seconds → Render kills the service.
"""

import json
import sys
import time
from typing import Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

import config


class Retriever:
    """
    Semantic search over the SHL assessment catalog using FAISS + sentence-transformers.

    Loads catalog at initialization, generates embeddings, builds FAISS index.
    Provides search() for top-k retrieval and get_all_entries() for provenance validation.

    Attributes:
        catalog: List of catalog entry dicts loaded from JSON.
        model: SentenceTransformer model instance.
        index: FAISS index for similarity search.
    """

    def __init__(self, catalog_path: Optional[str] = None):
        """
        Initialize the retriever: load catalog, generate embeddings, build FAISS index.

        Args:
            catalog_path: Path to catalog JSON file. Defaults to config.CATALOG_PATH.

        Raises:
            FileNotFoundError: If catalog file doesn't exist.
            ValueError: If catalog JSON is invalid or entries missing required fields.
            RuntimeError: If embedding model fails to load.

        Side effects:
            Downloads embedding model on first run (~90MB).
            Prints initialization timing to stdout.
        """
        start_time = time.time()

        # Resolve catalog path
        self.catalog_path = catalog_path or config.CATALOG_PATH

        # Step 1: Load catalog
        self.catalog = self._load_catalog()
        print(f"  Retriever: Loaded {len(self.catalog)} catalog entries.")

        # Step 2: Load embedding model
        try:
            self.model = SentenceTransformer(config.EMBEDDING_MODEL)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load embedding model '{config.EMBEDDING_MODEL}': {e}"
            ) from e
        print(f"  Retriever: Loaded embedding model '{config.EMBEDDING_MODEL}'.")

        # Step 3: Generate embeddings for all catalog entries
        texts = [self._entry_to_text(entry) for entry in self.catalog]
        embeddings = self.model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        self.embeddings = np.array(embeddings, dtype=np.float32)
        print(f"  Retriever: Generated {len(self.embeddings)} embeddings ({self.embeddings.shape[1]} dims).")

        # Step 4: Build FAISS index (IndexFlatIP for cosine similarity on normalized vectors)
        dimension = self.embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(self.embeddings)
        print(f"  Retriever: Built FAISS index with {self.index.ntotal} vectors.")

        elapsed = time.time() - start_time
        print(f"  Retriever: Initialization complete in {elapsed:.1f}s.")

    def _load_catalog(self) -> list[dict]:
        """
        Load and validate the catalog JSON file.

        Returns:
            List of catalog entry dicts.

        Raises:
            FileNotFoundError: If file doesn't exist at self.catalog_path.
            ValueError: If JSON is invalid or entries missing required fields.
        """
        import os

        if not os.path.exists(self.catalog_path):
            raise FileNotFoundError(
                f"Catalog file not found: {self.catalog_path}. "
                f"Run 'python catalog_scraper.py' first."
            )

        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                catalog = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON in catalog file {self.catalog_path}: {e}"
            ) from e

        if not isinstance(catalog, list):
            raise ValueError(
                f"Catalog must be a JSON array, got {type(catalog).__name__}"
            )

        if len(catalog) == 0:
            raise ValueError("Catalog is empty — no entries to index.")

        # Validate required fields
        required_fields = ["name", "url", "test_type"]
        for i, entry in enumerate(catalog):
            for field in required_fields:
                if field not in entry or not entry[field]:
                    raise ValueError(
                        f"Catalog entry {i} missing required field '{field}': "
                        f"{entry.get('name', 'UNKNOWN')}"
                    )

        return catalog

    def _entry_to_text(self, entry: dict) -> str:
        """
        Convert a catalog entry to a text string for embedding.

        Format: "{name} | {test_type} | {description}"
        This gives the embedding model context about the assessment's name,
        type, and what it measures.

        Args:
            entry: A catalog entry dict.

        Returns:
            Formatted text string for embedding.
        """
        name = entry.get("name", "")
        test_type = entry.get("test_type", "")
        description = entry.get("description", "")

        # Combine fields with pipe separator for clear semantic boundaries
        return f"{name} | {test_type} | {description}"

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        Search the catalog for entries most similar to the query.

        Args:
            query: Natural language search string (e.g., "java developer cognitive test").
            top_k: Number of results to return (1-10, default 10).

        Returns:
            List of catalog entry dicts, ordered by descending cosine similarity.
            Each dict includes all catalog fields plus a 'score' field (0.0-1.0).

        Notes:
            - Returns at most top_k results (may be fewer if catalog is smaller).
            - Empty query returns top_k entries by arbitrary order (not recommended).
            - Score is cosine similarity (1.0 = identical, 0.0 = orthogonal).
        """
        # Clamp top_k to valid range
        top_k = max(1, min(top_k, config.MAX_RECOMMENDATIONS, len(self.catalog)))

        # Embed the query (normalized for cosine similarity)
        query_embedding = self.model.encode(
            [query], show_progress_bar=False, normalize_embeddings=True
        )
        query_vector = np.array(query_embedding, dtype=np.float32)

        # Search FAISS index
        scores, indices = self.index.search(query_vector, top_k)

        # Build results list with scores
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.catalog):
                continue  # FAISS returns -1 for missing results
            entry = self.catalog[idx].copy()
            entry["score"] = float(score)
            results.append(entry)

        return results

    def get_all_entries(self) -> list[dict]:
        """
        Return the full catalog for provenance validation.

        Returns:
            List of all catalog entry dicts (without scores).

        Notes:
            Used by agent.py to validate that recommendations exist in the catalog.
        """
        return self.catalog


# ============================================================
# Module-level instance — initialized once at startup
# ============================================================
# This will be set by main.py during startup event.
# Other modules import this and use it for search.
_instance: Optional[Retriever] = None


def get_retriever() -> Retriever:
    """
    Get the global Retriever instance.

    Returns:
        The initialized Retriever instance.

    Raises:
        RuntimeError: If retriever hasn't been initialized yet.
    """
    if _instance is None:
        raise RuntimeError(
            "Retriever not initialized. Call initialize_retriever() first."
        )
    return _instance


def initialize_retriever(catalog_path: Optional[str] = None) -> Retriever:
    """
    Initialize the global Retriever instance.

    Called once during FastAPI startup event.

    Args:
        catalog_path: Optional override for catalog file path.

    Returns:
        The initialized Retriever instance.
    """
    global _instance
    _instance = Retriever(catalog_path=catalog_path)
    return _instance
