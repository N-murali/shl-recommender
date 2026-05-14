"""
main.py — FastAPI application with /health and /chat endpoints.

What this file does:
    Defines the HTTP entry points for the SHL Assessment Recommender.
    - GET /health: Returns {"status": "ok"} for evaluator readiness check.
    - POST /chat: Stateless conversational endpoint. Full conversation history
      sent on every call. Delegates to agent.process_conversation().

Why these decisions:
    - FastAPI for automatic Pydantic validation, async support, OpenAPI docs.
    - Startup event initializes retriever (loads model + builds FAISS index).
    - Startup validates GROQ_API_KEY exists (fail fast if missing).
    - No session state stored — completely stateless design.
    - Response model enforces schema compliance at serialization time.

What breaks if this file is wrong:
    - Wrong endpoint path → evaluator can't find /health or /chat → submission fails.
    - Wrong response format → evaluator can't parse → submission fails.
    - Missing startup init → retriever not loaded → 500 on first /chat call.
    - Wrong port → Render can't route traffic → service unreachable.
"""

import time
import sys

from fastapi import FastAPI
from fastapi.responses import JSONResponse

import config
from models import ChatRequest, ChatResponse
from retriever import initialize_retriever
from agent import process_conversation

# Initialize FastAPI application
app = FastAPI(
    title="SHL Assessment Recommender",
    description="Conversational AI agent that helps hiring managers find SHL assessments.",
    version="1.0.0",
)


@app.on_event("startup")
async def startup():
    """
    Application startup event — runs once when the server starts.

    Steps:
    1. Validate GROQ_API_KEY is set (fail fast if missing).
    2. Initialize the retriever (load catalog, build embeddings, build FAISS index).

    Raises:
        SystemExit: If GROQ_API_KEY is not set.
        RuntimeError: If retriever initialization fails.

    Notes:
        - Must complete within 120 seconds (Render cold start budget).
        - Retriever init takes ~13 seconds (model load + embedding generation).
    """
    start_time = time.time()
    print("=" * 50)
    print("SHL Assessment Recommender — Starting up...")
    print("=" * 50)

    # Step 1: Validate API key
    if not config.GROQ_API_KEY:
        print("FATAL: GROQ_API_KEY not set. Add it to .env or environment variables.")
        sys.exit(1)
    print(f"  API key: configured (provider={config.LLM_PROVIDER}, model={config.LLM_MODEL})")

    # Step 2: Initialize retriever
    print("  Initializing retriever...")
    try:
        initialize_retriever()
    except Exception as e:
        print(f"FATAL: Retriever initialization failed: {e}")
        sys.exit(1)

    elapsed = time.time() - start_time
    print(f"\n  Startup complete in {elapsed:.1f}s")
    print(f"  Listening on port {config.PORT}")
    print("=" * 50)


@app.get("/health")
async def health() -> dict:
    """
    Health check endpoint for the auto-evaluator.

    Returns:
        JSON response {"status": "ok"} with HTTP 200.

    Notes:
        - Evaluator allows up to 120 seconds for cold start on first call.
        - After warm-up, must respond within 1 second.
        - Only GET method is supported (FastAPI returns 405 for others automatically).
    """
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Main conversational endpoint — stateless, full history in every request.

    The evaluator sends the complete conversation history on every call.
    No server-side state is stored between requests.

    Args:
        request: ChatRequest with messages array (validated by Pydantic).

    Returns:
        ChatResponse with reply, recommendations, and end_of_conversation.

    Notes:
        - Must respond within 30 seconds (evaluator timeout).
        - Schema compliance is enforced by Pydantic response_model.
        - All recommendations are validated against catalog (provenance check).
    """
    # Convert Pydantic messages to plain dicts for agent
    messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

    # Process conversation through agent
    result = process_conversation(messages)

    # Return as ChatResponse (Pydantic validates schema)
    return ChatResponse(
        reply=result["reply"],
        recommendations=result["recommendations"],
        end_of_conversation=result["end_of_conversation"],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.PORT,
        reload=True,  # Auto-reload during development
    )
