"""
tests/test_api.py — API endpoint integration tests.

What this file does:
    Tests the FastAPI endpoints (/health and /chat) using httpx TestClient.
    Verifies schema compliance, validation errors, and response format.

Why these decisions:
    - Uses FastAPI TestClient (httpx-based) for in-process testing.
    - Mocks call_llm() to avoid real API calls in tests (fast, free, deterministic).
    - Tests both happy path and error cases.

What breaks if this file is wrong:
    - False positives → bugs slip through to production.
    - False negatives → valid code fails tests → blocks development.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="module")
def client():
    """Create a test client for the FastAPI app (startup runs once for module)."""
    with TestClient(app) as c:
        yield c


# ============================================================
# /health endpoint tests
# ============================================================


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_returns_ok(self, client):
        """GET /health should return 200 with {"status": "ok"}."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_content_type(self, client):
        """GET /health should return application/json content type."""
        response = client.get("/health")
        assert "application/json" in response.headers["content-type"]

    def test_health_post_not_allowed(self, client):
        """POST /health should return 405 Method Not Allowed."""
        response = client.post("/health")
        assert response.status_code == 405


# ============================================================
# /chat endpoint — validation tests
# ============================================================


class TestChatValidation:
    """Tests for POST /chat request validation."""

    def test_empty_body_returns_422(self, client):
        """POST /chat with no body should return 422."""
        response = client.post("/chat")
        assert response.status_code == 422

    def test_empty_messages_returns_422(self, client):
        """POST /chat with empty messages array should return 422."""
        response = client.post("/chat", json={"messages": []})
        assert response.status_code == 422

    def test_invalid_role_returns_422(self, client):
        """POST /chat with invalid role should return 422."""
        response = client.post("/chat", json={
            "messages": [{"role": "system", "content": "hello"}]
        })
        assert response.status_code == 422

    def test_empty_content_returns_422(self, client):
        """POST /chat with empty content should return 422."""
        response = client.post("/chat", json={
            "messages": [{"role": "user", "content": ""}]
        })
        assert response.status_code == 422

    def test_missing_content_returns_422(self, client):
        """POST /chat with missing content field should return 422."""
        response = client.post("/chat", json={
            "messages": [{"role": "user"}]
        })
        assert response.status_code == 422

    def test_too_many_messages_returns_422(self, client):
        """POST /chat with >50 messages should return 422."""
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(51)]
        response = client.post("/chat", json={"messages": messages})
        assert response.status_code == 422


# ============================================================
# /chat endpoint — response schema tests
# ============================================================


class TestChatResponseSchema:
    """Tests for POST /chat response schema compliance."""

    @patch("agent.call_llm")
    def test_valid_request_returns_200(self, mock_llm, client):
        """POST /chat with valid request should return 200."""
        mock_llm.return_value = json.dumps({
            "reply": "What role are you hiring for?",
            "recommendations": [],
            "end_of_conversation": False,
        })
        response = client.post("/chat", json={
            "messages": [{"role": "user", "content": "I need assessments for a senior Java developer with problem-solving and communication skills"}]
        })
        assert response.status_code == 200

    @patch("agent.call_llm")
    def test_response_has_required_fields(self, mock_llm, client):
        """Response must have reply, recommendations, end_of_conversation."""
        mock_llm.return_value = json.dumps({
            "reply": "What role are you hiring for?",
            "recommendations": [],
            "end_of_conversation": False,
        })
        response = client.post("/chat", json={
            "messages": [{"role": "user", "content": "I need assessments for a senior Java developer with problem-solving and communication skills"}]
        })
        data = response.json()
        assert "reply" in data
        assert "recommendations" in data
        assert "end_of_conversation" in data

    @patch("agent.call_llm")
    def test_reply_is_string(self, mock_llm, client):
        """reply field must be a string."""
        mock_llm.return_value = json.dumps({
            "reply": "Hello there",
            "recommendations": [],
            "end_of_conversation": False,
        })
        response = client.post("/chat", json={
            "messages": [{"role": "user", "content": "I need assessments for a senior developer with leadership skills"}]
        })
        data = response.json()
        assert isinstance(data["reply"], str)
        assert len(data["reply"]) > 0

    @patch("agent.call_llm")
    def test_recommendations_is_list(self, mock_llm, client):
        """recommendations field must be a list."""
        mock_llm.return_value = json.dumps({
            "reply": "Here you go",
            "recommendations": [],
            "end_of_conversation": False,
        })
        response = client.post("/chat", json={
            "messages": [{"role": "user", "content": "I need assessments for a senior developer with leadership skills"}]
        })
        data = response.json()
        assert isinstance(data["recommendations"], list)

    @patch("agent.call_llm")
    def test_end_of_conversation_is_bool(self, mock_llm, client):
        """end_of_conversation field must be a boolean."""
        mock_llm.return_value = json.dumps({
            "reply": "Done",
            "recommendations": [],
            "end_of_conversation": False,
        })
        response = client.post("/chat", json={
            "messages": [{"role": "user", "content": "I need assessments for a senior developer with leadership skills"}]
        })
        data = response.json()
        assert isinstance(data["end_of_conversation"], bool)
