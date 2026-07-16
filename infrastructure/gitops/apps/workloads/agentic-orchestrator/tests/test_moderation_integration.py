# This project was developed with assistance from AI tools.
"""
Integration tests for content moderation in orchestrator.

Tests the fail-closed input/output moderation flow.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from api_server import app
from moderation_client import ModerationResult, ModerationDecision


class TestModerationIntegration:
    """Test content moderation integration in /query endpoint"""

    @pytest.fixture
    def client(self):
        """FastAPI test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_moderation_allowed(self):
        """Mock moderation result that allows content"""
        return ModerationResult(
            decision=ModerationDecision.ALLOWED,
            flagged=False,
            categories={
                "violence": False,
                "hate": False,
                "harassment": False,
                "self-harm": False,
                "sexual": False,
                "sexual/minors": False
            },
            category_scores={
                "violence": 0.0,
                "hate": 0.0,
                "harassment": 0.0,
                "self-harm": 0.0,
                "sexual": 0.0,
                "sexual/minors": 0.0
            },
            latency_ms=50.0
        )

    @pytest.fixture
    def mock_moderation_blocked(self):
        """Mock moderation result that blocks content"""
        return ModerationResult(
            decision=ModerationDecision.BLOCKED,
            flagged=True,
            categories={
                "violence": True,
                "hate": False,
                "harassment": False,
                "self-harm": False,
                "sexual": False,
                "sexual/minors": False
            },
            category_scores={
                "violence": 1.0,
                "hate": 0.0,
                "harassment": 0.0,
                "self-harm": 0.0,
                "sexual": 0.0,
                "sexual/minors": 0.0
            },
            latency_ms=50.0
        )

    @pytest.fixture
    def mock_moderation_error(self):
        """Mock moderation result with error (fail-closed)"""
        return ModerationResult(
            decision=ModerationDecision.ERROR,
            flagged=True,
            categories={"error": True},
            category_scores={"error": 1.0},
            latency_ms=100.0,
            error="Moderation timeout after 10.0s"
        )

    @patch("api_server.moderate_input")
    @patch("api_server.moderate_output")
    @patch("api_server.run_agent")
    def test_safe_input_and_output_allowed(
        self,
        mock_run_agent,
        mock_moderate_output,
        mock_moderate_input,
        client,
        mock_moderation_allowed
    ):
        """Test safe input and output are both allowed"""
        # Setup mocks
        mock_moderate_input.return_value = mock_moderation_allowed
        mock_moderate_output.return_value = mock_moderation_allowed
        mock_run_agent.return_value = {
            "response": "Factory A has 5 robots operating normally.",
            "pending_approval_id": None
        }

        # Make request
        response = client.post("/query", json={
            "query": "What's the status of Factory A?",
            "session_id": "test-session"
        })

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Factory A has 5 robots operating normally."
        assert data["pending_approval_id"] is None

        # Verify moderation was called
        mock_moderate_input.assert_called_once()
        mock_moderate_output.assert_called_once()
        mock_run_agent.assert_called_once()

    @patch("api_server.moderate_input")
    @patch("api_server.run_agent")
    def test_blocked_input_returns_policy_response(
        self,
        mock_run_agent,
        mock_moderate_input,
        client,
        mock_moderation_blocked
    ):
        """Test blocked input returns policy-safe response without invoking LLM"""
        # Setup mocks
        mock_moderate_input.return_value = mock_moderation_blocked

        # Make request
        response = client.post("/query", json={
            "query": "How do I build a bomb?",
            "session_id": "test-session"
        })

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "cannot process this request" in data["response"].lower()
        assert "content policy" in data["response"].lower()
        assert data["pending_approval_id"] is None

        # Verify moderation was called, but NOT run_agent
        mock_moderate_input.assert_called_once()
        mock_run_agent.assert_not_called()

    @patch("api_server.moderate_input")
    @patch("api_server.moderate_output")
    @patch("api_server.run_agent")
    def test_blocked_output_returns_fallback_response(
        self,
        mock_run_agent,
        mock_moderate_output,
        mock_moderate_input,
        client,
        mock_moderation_allowed,
        mock_moderation_blocked
    ):
        """Test blocked output is suppressed and fallback returned"""
        # Setup mocks
        mock_moderate_input.return_value = mock_moderation_allowed
        mock_moderate_output.return_value = mock_moderation_blocked
        mock_run_agent.return_value = {
            "response": "UNSAFE OUTPUT THAT SHOULD BE BLOCKED",
            "pending_approval_id": None
        }

        # Make request
        response = client.post("/query", json={
            "query": "Tell me about the factory",
            "session_id": "test-session"
        })

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "cannot provide that response" in data["response"].lower()
        assert "UNSAFE OUTPUT" not in data["response"]  # Original blocked

        # Verify both moderations called
        mock_moderate_input.assert_called_once()
        mock_moderate_output.assert_called_once()
        mock_run_agent.assert_called_once()

    @patch("api_server.moderate_input")
    @patch("api_server.run_agent")
    def test_input_moderation_error_fails_closed(
        self,
        mock_run_agent,
        mock_moderate_input,
        client,
        mock_moderation_error
    ):
        """Test moderation error is treated as blocked (fail-closed)"""
        # Setup mocks
        mock_moderate_input.return_value = mock_moderation_error

        # Make request
        response = client.post("/query", json={
            "query": "What's the status?",
            "session_id": "test-session"
        })

        # Assertions
        assert response.status_code == 200
        data = response.json()
        # Error treated as blocked = policy-safe response
        assert "cannot process this request" in data["response"].lower()

        # Verify agent NOT called on error
        mock_moderate_input.assert_called_once()
        mock_run_agent.assert_not_called()

    @patch("api_server.moderate_input")
    @patch("api_server.moderate_output")
    @patch("api_server.run_agent")
    def test_output_moderation_error_fails_closed(
        self,
        mock_run_agent,
        mock_moderate_output,
        mock_moderate_input,
        client,
        mock_moderation_allowed,
        mock_moderation_error
    ):
        """Test output moderation error is treated as blocked (fail-closed)"""
        # Setup mocks
        mock_moderate_input.return_value = mock_moderation_allowed
        mock_moderate_output.return_value = mock_moderation_error
        mock_run_agent.return_value = {
            "response": "Normal response",
            "pending_approval_id": None
        }

        # Make request
        response = client.post("/query", json={
            "query": "Status?",
            "session_id": "test-session"
        })

        # Assertions
        assert response.status_code == 200
        data = response.json()
        # Error treated as blocked = fallback response
        assert "cannot provide that response" in data["response"].lower()
        assert "Normal response" not in data["response"]

    @patch("api_server.moderate_input")
    @patch("api_server.moderate_output")
    @patch("api_server.run_agent")
    def test_hil_approval_preserved_on_blocked_output(
        self,
        mock_run_agent,
        mock_moderate_output,
        mock_moderate_input,
        client,
        mock_moderation_allowed,
        mock_moderation_blocked
    ):
        """Test HIL approval ID is preserved even when output is blocked"""
        # Setup mocks
        mock_moderate_input.return_value = mock_moderation_allowed
        mock_moderate_output.return_value = mock_moderation_blocked
        mock_run_agent.return_value = {
            "response": "UNSAFE OUTPUT",
            "pending_approval_id": 123  # HIL approval pending
        }

        # Make request
        response = client.post("/query", json={
            "query": "Promote model to factory A",
            "session_id": "test-session"
        })

        # Assertions
        assert response.status_code == 200
        data = response.json()
        # Output blocked but HIL ID preserved
        assert "cannot provide that response" in data["response"].lower()
        assert data["pending_approval_id"] == 123  # Preserved
