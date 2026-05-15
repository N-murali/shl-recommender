"""
retriever.py — FAISS vector store with pre-computed embeddings + HF API for queries.

What this file does:
    Loads pre-computed catalog embeddings from data/embeddings.npy (generated
    offline by scripts/precompute_embeddings.py), builds a FAISS index, and
    provides search() that embeds queries via Hugging Face Inference API.

Why these decisions:
    - Pre-computed embeddings: Avoids loading PyTorch + sentence-transformers
      on the server (~400MB RAM saved). Critical for Render free tier (512MB).
    - HF Inference API for queries: Same model (all-MiniLM-L6-v2), same vectors,
      runs on HF's servers. Adds ~200ms latency but saves 400MB RAM.
    - FAISS IndexFlatIP: Exact search on normalized vectors = cosine similarity.
      Catalog is small (377 entries) so brute force is fast.

What breaks if this file is wrong:
    - Missing embeddings.npy → FileNotFoundError at startup → service won't start.
    - HF API down → query embedding fails → search returns empty → no recommendations.
    - Embeddings/catalog mismatch (different order) → wrong results returned.
"""

import json
import os
import time
from typing import Optional

import faiss
import numpy as np
import requests

import config


class Retriever:
    """
    Semantic search over the SHL assessment catalog using FAISS + pre-computed embeddings.

    Catalog embeddings are loaded from disk (pre-computed offline).
    Query embeddings are generated via Hugging Face Inference API.

    Attributes:
        catalog: List of catalog entry dicts loaded from JSON.
        index: FAISS index for similarity search.
    """

    def __init__(self, catalog_path: Optional[str] = None, embeddings_path: Optional[str] = None):
        """
        Initialize the retriever: load catalog, load embeddings, build FAISS index.

        Args:
            catalog_path: Path to catalog JSON file. Defaults to config.CATALOG_PATH.
            embeddings_path: Path to pre-computed embeddings .npy file. Defaults to config.EMBEDDINGS_PATH.

        Raises:
            FileNotFoundError: If catalog or embeddings file doesn't exist.
            ValueError: If catalog JSON is invalid or embeddings shape doesn't match.
        """
        start_time = time.time()

        self.catalog_path = catalog_path or config.CATALOG_PATH
        self.embeddings_path = embeddings_path or config.EMBEDDINGS_PATH

        # Step 1: Load catalog
        self.catalog = self._load_catalog()
        print(f"  Retriever: Loaded {len(self.catalog)} catalog entries.")

        # Step 2: Load pre-computed embeddings
        self.embeddings = self._load_embeddings()
        print(f"  Retriever: Loaded embeddings ({self.embeddings.shape[0]} x {self.embeddings.shape[1]}).")

        # Step 3: Validate embeddings match catalog
        if self.embeddings.shape[0] != len(self.catalog):
            raise ValueError(
                f"Embeddings count ({self.embeddings.shape[0]}) doesn't match "
                f"catalog count ({len(self.catalog)}). Re-run scripts/precompute_embeddings.py"
            )

        # Step 4: Build FAISS index
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
            FileNotFoundError: If file doesn't exist.
            ValueError: If JSON is invalid or entries missing required fields.
        """
        if not os.path.exists(self.catalog_path):
            raise FileNotFoundError(
                f"Catalog file not found: {self.catalog_path}. "
                f"Run 'python catalog_scraper.py' first."
            )

        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                catalog = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in catalog file: {e}") from e

        if not isinstance(catalog, list) or len(catalog) == 0:
            raise ValueError("Catalog must be a non-empty JSON array.")

        # Validate required fields
        for i, entry in enumerate(catalog):
            for field in ["name", "url", "test_type"]:
                if field not in entry or not entry[field]:
                    raise ValueError(f"Catalog entry {i} missing '{field}'")

        return catalog

    def _load_embeddings(self) -> np.ndarray:
        """
        Load pre-computed embeddings from .npy file.

        Returns:
            numpy array of shape (N, 384) with L2-normalized embeddings.

        Raises:
            FileNotFoundError: If embeddings file doesn't exist.
            ValueError: If file is corrupted or wrong dimensions.
        """
        if not os.path.exists(self.embeddings_path):
            raise FileNotFoundError(
                f"Embeddings file not found: {self.embeddings_path}. "
                f"Run 'python scripts/precompute_embeddings.py' first."
            )

        try:
            embeddings = np.load(self.embeddings_path)
        except Exception as e:
            raise ValueError(f"Failed to load embeddings: {e}") from e

        if embeddings.ndim != 2 or embeddings.shape[1] != config.EMBEDDING_DIM:
            raise ValueError(
                f"Embeddings have wrong shape: {embeddings.shape}. "
                f"Expected (N, {config.EMBEDDING_DIM})."
            )

        return embeddings.astype(np.float32)

    def _embed_query(self, query: str) -> np.ndarray:
        """
        Embed a query string using Hugging Face Inference API.

        Calls the same model (all-MiniLM-L6-v2) that was used to pre-compute
        catalog embeddings, ensuring vectors are in the same space.

        Args:
            query: Natural language search string.

        Returns:
            numpy array of shape (1, 384) — L2-normalized query embedding.

        Raises:
            RuntimeError: If HF API call fails.
        """
        if not config.HF_API_TOKEN:
            raise RuntimeError("HF_API_TOKEN not set. Add it to .env file.")

        headers = {"Authorization": f"Bearer {config.HF_API_TOKEN}"}
        payload = {"inputs": query, "options": {"wait_for_model": True}}

        try:
            response = requests.post(
                config.HF_API_URL,
                headers=headers,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise RuntimeError("HF Inference API timed out (10s)")
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"HF Inference API error: {e.response.status_code} {e.response.text[:200]}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"HF Inference API request failed: {e}")

        # Parse response — returns a list of floats (384 dimensions)
        embedding = response.json()

        # Handle nested list format [[0.1, 0.2, ...]]
        if isinstance(embedding, list) and len(embedding) > 0:
            if isinstance(embedding[0], list):
                embedding = embedding[0]

        embedding = np.array(embedding, dtype=np.float32).reshape(1, -1)

        # L2 normalize for cosine similarity
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        Search the catalog for entries most similar to the query.

        Args:
            query: Natural language search string.
            top_k: Number of results to return (1-10, default 10).

        Returns:
            List of catalog entry dicts ordered by descending cosine similarity.
            Each dict includes all catalog fields plus a 'score' field.
        """
        top_k = max(1, min(top_k, config.MAX_RECOMMENDATIONS, len(self.catalog)))

        try:
            query_vector = self._embed_query(query)
        except RuntimeError as e:
            # If HF API fails, return empty results (agent will handle gracefully)
            print(f"  WARNING: Query embedding failed: {e}")
            return []

        # Search FAISS index
        scores, indices = self.index.search(query_vector, top_k)

        # Build results list
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.catalog):
                continue
            entry = self.catalog[idx].copy()
            entry["score"] = float(score)
            results.append(entry)

        return results

    def get_all_entries(self) -> list[dict]:
        """
        Return the full catalog for provenance validation.

        Returns:
            List of all catalog entry dicts (without scores).
        """
        return self.catalog


# ============================================================
# Module-level instance — initialized once at startup
# ============================================================
_instance: Optional[Retriever] = None


def get_retriever() -> Retriever:
    """
    Get the global Retriever instance.

    Raises:
        RuntimeError: If retriever hasn't been initialized yet.
    """
    if _instance is None:
        raise RuntimeError("Retriever not initialized. Call initialize_retriever() first.")
    return _instance


def initialize_retriever(catalog_path: Optional[str] = None, embeddings_path: Optional[str] = None) -> Retriever:
    """
    Initialize the global Retriever instance. Called once during FastAPI startup.

    Args:
        catalog_path: Optional override for catalog file path.
        embeddings_path: Optional override for embeddings file path.

    Returns:
        The initialized Retriever instance.
    """
    global _instance
    _instance = Retriever(catalog_path=catalog_path, embeddings_path=embeddings_path)
    return _instance
