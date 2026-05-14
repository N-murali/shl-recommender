"""
models.py — Pydantic v2 request/response models for the SHL Recommender API.

What this file does:
    Defines strict data validation models for the POST /chat endpoint.
    FastAPI uses these to automatically validate incoming requests and
    serialize outgoing responses. Any schema violation returns HTTP 422
    with field-level error details.

Why these decisions:
    - Literal["user", "assistant"] for role — rejects any other value at the boundary.
    - Field constraints (min_length, max_length) enforce evaluator limits.
    - Separate Recommendation model ensures each item has exactly 3 fields.
    - BehaviorMode enum used internally by agent.py for mode routing.

What breaks if this file is wrong:
    - Wrong field names → auto-evaluator can't parse responses → submission fails.
    - Missing validation → invalid data reaches agent → unpredictable behavior.
    - Wrong types → serialization errors → 500 instead of proper response.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    """
    A single message in the conversation history.

    Attributes:
        role: Must be exactly "user" or "assistant". No other values accepted.
        content: The message text. Must be non-empty, max 10,000 characters.
    """

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=10000)


class ChatRequest(BaseModel):
    """
    Request body for POST /chat endpoint.

    The evaluator sends the full conversation history on every call.
    No server-side state — all context comes from this messages array.

    Attributes:
        messages: List of 1-50 Message objects representing the conversation.
    """

    messages: list[Message] = Field(min_length=1, max_length=50)


class Recommendation(BaseModel):
    """
    A single assessment recommendation returned to the user.

    Every field must exactly match a catalog entry (case-sensitive).
    The auto-evaluator validates URLs against the scraped catalog.

    Attributes:
        name: Assessment name, must match catalog entry exactly.
        url: SHL product page URL, must start with "https://".
        test_type: Assessment type code (e.g., "K", "P", "A", "B", "C").
    """

    name: str = Field(min_length=1)
    url: str = Field(pattern=r"^https://.*")
    test_type: str = Field(min_length=1)


class ChatResponse(BaseModel):
    """
    Response body for POST /chat endpoint.

    THIS SCHEMA IS NON-NEGOTIABLE. The auto-evaluator parses every response.
    Any deviation fails the entire submission.

    Rules:
        - recommendations is [] when clarifying or refusing.
        - recommendations has 1-10 items when committing to a shortlist.
        - end_of_conversation is true ONLY when task is complete.

    Attributes:
        reply: Natural language response to the user (1-2000 chars).
        recommendations: List of 0-10 Recommendation objects.
        end_of_conversation: Whether the conversation is complete.
    """

    reply: str = Field(min_length=1, max_length=2000)
    recommendations: list[Recommendation] = Field(default_factory=list, max_length=10)
    end_of_conversation: bool = False


class BehaviorMode(str, Enum):
    """
    Internal enum for agent behavior routing.

    Used by agent.py to determine which conversational behavior to execute.
    Not exposed in the API — purely internal logic.
    """

    CLARIFY = "clarify"
    RECOMMEND = "recommend"
    REFINE = "refine"
    COMPARE = "compare"
    REFUSE = "refuse"
