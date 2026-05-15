"""
scripts/precompute_embeddings.py — Generate embeddings offline and save to disk.

Purpose:
    Generates embeddings for all catalog entries using sentence-transformers
    and saves them as a numpy .npy file. This allows the server to load
    pre-computed embeddings at startup WITHOUT needing sentence-transformers
    or PyTorch installed — saving ~400MB of RAM on Render free tier.

How to run:
    python scripts/precompute_embeddings.py
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from sentence_transformers import SentenceTransformer

CATALOG_PATH = "data/catalog.json"
EMBEDDINGS_PATH = "data/embeddings.npy"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


def entry_to_text(entry: dict) -> str:
    """Convert catalog entry to text for embedding (same logic as retriever.py)."""
    name = entry.get("name", "")
    test_type = entry.get("test_type", "")
    description = entry.get("description", "")
    return f"{name} | {test_type} | {description}"


def main():
    print("=" * 60)
    print("Pre-computing embeddings for Render deployment")
    print("=" * 60)

    print(f"\n1. Loading catalog from {CATALOG_PATH}...")
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    print(f"   Loaded {len(catalog)} entries.")

    print(f"\n2. Loading embedding model '{EMBEDDING_MODEL}'...")
    start = time.time()
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"   Model loaded in {time.time() - start:.1f}s")

    print(f"\n3. Generating embeddings...")
    texts = [entry_to_text(entry) for entry in catalog]
    start = time.time()
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    embeddings = np.array(embeddings, dtype=np.float32)
    print(f"   Generated {embeddings.shape[0]} embeddings ({embeddings.shape[1]} dims) in {time.time() - start:.1f}s")

    print(f"\n4. Saving to {EMBEDDINGS_PATH}...")
    os.makedirs(os.path.dirname(EMBEDDINGS_PATH), exist_ok=True)
    np.save(EMBEDDINGS_PATH, embeddings)
    file_size = os.path.getsize(EMBEDDINGS_PATH) / 1024
    print(f"   Saved ({file_size:.1f} KB)")

    print(f"\n5. Verifying...")
    loaded = np.load(EMBEDDINGS_PATH)
    assert loaded.shape == embeddings.shape
    assert np.allclose(loaded, embeddings)
    print(f"   Shape: {loaded.shape} ✓")

    print(f"\n{'=' * 60}")
    print(f"Done! Deploy data/embeddings.npy alongside data/catalog.json")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
