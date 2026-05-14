"""
config.py — Configuration and environment variable loading.

What this file does:
    Loads environment variables from .env file and defines all application
    constants in one place. This is the ONLY file that needs to change
    (along with agent.py's call_llm body and requirements.txt) when
    swapping LLM providers.

Why these decisions:
    - All constants centralized here so nothing is hardcoded elsewhere.
    - python-dotenv loads .env automatically — no manual export needed.
    - LLM_PROVIDER and LLM_MODEL as named constants enable single-point swap.

What breaks if this file is wrong:
    - Missing GROQ_API_KEY → service fails to start (intentional fail-fast).
    - Wrong PORT → Render can't route traffic to the service.
    - Wrong CATALOG_PATH → retriever can't find catalog at startup.
"""

import os
from dotenv import load_dotenv

# Load .env file from project root (if it exists)
load_dotenv()

# ============================================================
# LLM Configuration
# To swap provider, change these 3 lines + call_llm() body in agent.py
# ============================================================
LLM_PROVIDER: str = "groq"
LLM_MODEL: str = "llama-3.3-70b-versatile"
GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")

# ============================================================
# Application Constants
# ============================================================

# Server port — Render sets PORT env var; default 10000 for local dev
PORT: int = int(os.getenv("PORT", "10000"))

# Path to scraped catalog JSON file
CATALOG_PATH: str = os.getenv("CATALOG_PATH", "data/catalog.json")

# Sentence-transformers embedding model (384 dimensions, fast on CPU)
EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

# ============================================================
# Conversation Constraints (enforced by auto-evaluator)
# ============================================================

# Maximum turns per conversation (user + assistant messages combined)
MAX_TURNS: int = 8

# Maximum recommendations in a single response
MAX_RECOMMENDATIONS: int = 10

# Number of catalog entries to retrieve per search
RETRIEVER_TOP_K: int = 10

# Maximum seconds allowed per API call (retrieval + LLM combined)
REQUEST_TIMEOUT: int = 30

# ============================================================
# Request Validation Limits
# ============================================================

# Maximum messages allowed in a single request
MAX_MESSAGES: int = 50

# Maximum characters per message content field
MAX_CONTENT_LENGTH: int = 10000

# Maximum characters in the reply field of response
MAX_REPLY_LENGTH: int = 2000
