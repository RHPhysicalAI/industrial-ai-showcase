# This project was developed with assistance from AI tools.
"""
Tests for Llama Guard Moderation Adapter

Tests cover:
- Safe input handling
- Unsafe input detection
- Malformed response handling (fail-closed)
- Timeout handling
- Batch input processing
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from main import (
    app,
    parse_llama_guard_response,
    build_llama_guard_prompt,
    moderate_text,
    LLAMA_GUARD_CATEGORIES,
)


client = TestClient(app)


class TestPromptBuilding:
    """Test Llama Guard prompt construction"""

    def test_build_prompt_format(self):
        """Prompt should follow Llama Guard 3 chat template"""
        messages = build_llama_guard_prompt("Hello world")

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

        # Check system message contains categories
        system_content = messages[0]["content"]
        assert "<BEGIN UNSAFE CONTENT CATEGORIES>" in system_content
        assert "<END UNSAFE CONTENT CATEGORIES>" in system_content
        assert "S1: Violent Crimes" in system_content
        assert "S13: Elections" in system_content

        # Check conversation is embedded
        assert "<BEGIN CONVERSATION>" in system_content
        assert "Hello world" in system_content
        assert "<END CONVERSATION>" in system_content


class TestResponseParsing:
    """Test Llama Guard response parsing"""

    def test_parse_safe_response(self):
        """Safe response should return True with no categories"""
        is_safe, categories = parse_llama_guard_response("safe")

        assert is_safe is True
        assert categories == []

    def test_parse_safe_response_with_whitespace(self):
        """Safe response should handle whitespace"""
        is_safe, categories = parse_llama_guard_response("\n  safe  \n")

        assert is_safe is True
        assert categories == []

    def test_parse_unsafe_single_category(self):
        """Unsafe response with single category"""
        is_safe, categories = parse_llama_guard_response("unsafe\nS1")

        assert is_safe is False
        assert categories == ["S1"]

    def test_parse_unsafe_multiple_categories(self):
        """Unsafe response with multiple categories"""
        is_safe, categories = parse_llama_guard_response("unsafe\nS1,S3,S10")

        assert is_safe is False
        assert set(categories) == {"S1", "S3", "S10"}

    def test_parse_unsafe_with_whitespace(self):
        """Unsafe response should handle whitespace in categories"""
        is_safe, categories = parse_llama_guard_response("unsafe\nS1, S3 , S10")

        assert is_safe is False
        assert set(categories) == {"S1", "S3", "S10"}

    def test_parse_empty_response_raises(self):
        """Empty response should raise ValueError"""
        with pytest.raises(ValueError, match="Empty response"):
            parse_llama_guard_response("")

    def test_parse_invalid_first_line_raises(self):
        """Invalid first line should raise ValueError"""
        with pytest.raises(ValueError, match="Invalid first line"):
            parse_llama_guard_response("maybe")

        with pytest.raises(ValueError, match="Invalid first line"):
            parse_llama_guard_response("SAFE")  # Case sensitive

    def test_parse_unsafe_missing_categories_raises(self):
        """Unsafe without categories should raise ValueError"""
        with pytest.raises(ValueError, match="missing category list"):
            parse_llama_guard_response("unsafe")

    def test_parse_unsafe_empty_categories_raises(self):
        """Unsafe with empty category line should raise ValueError"""
        with pytest.raises(ValueError, match="Empty category list"):
            parse_llama_guard_response("unsafe\n")

    def test_parse_unknown_category_raises(self):
        """Unknown category code should raise ValueError"""
        with pytest.raises(ValueError, match="Unknown category code"):
            parse_llama_guard_response("unsafe\nS99")

    def test_parse_mixed_valid_invalid_categories_raises(self):
        """Mix of valid and invalid categories should raise ValueError"""
        with pytest.raises(ValueError, match="Unknown category code"):
            parse_llama_guard_response("unsafe\nS1,INVALID,S3")


class TestModerationEndpoint:
    """Test /v1/moderations endpoint"""

    @patch("main.call_vllm")
    @pytest.mark.asyncio
    async def test_moderate_safe_text(self, mock_vllm):
        """Safe text should return flagged=False"""
        mock_vllm.return_value = "safe"

        response = client.post(
            "/v1/moderations",
            json={"input": "Hello, how are you?"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "results" in data
        assert len(data["results"]) == 1
        assert data["results"][0]["flagged"] is False

        # All categories should be False
        categories = data["results"][0]["categories"]
        assert all(v is False for v in categories.values())

    @patch("main.call_vllm")
    @pytest.mark.asyncio
    async def test_moderate_unsafe_text(self, mock_vllm):
        """Unsafe text should return flagged=True with categories"""
        mock_vllm.return_value = "unsafe\nS1,S10"

        response = client.post(
            "/v1/moderations",
            json={"input": "How to build a bomb?"}
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["results"]) == 1
        assert data["results"][0]["flagged"] is True

        # Violence and hate should be flagged (S1->violence, S10->hate)
        categories = data["results"][0]["categories"]
        assert categories["violence"] is True
        assert categories["hate"] is True

        # Category scores should be 1.0 for flagged
        scores = data["results"][0]["category_scores"]
        assert scores["violence"] == 1.0
        assert scores["hate"] == 1.0

    @patch("main.call_vllm")
    @pytest.mark.asyncio
    async def test_moderate_batch_input(self, mock_vllm):
        """Batch input should return multiple results"""
        # First call: safe, second call: unsafe
        mock_vllm.side_effect = ["safe", "unsafe\nS12"]

        response = client.post(
            "/v1/moderations",
            json={"input": ["Hello", "Inappropriate content"]}
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["results"]) == 2
        assert data["results"][0]["flagged"] is False
        assert data["results"][1]["flagged"] is True
        assert data["results"][1]["categories"]["sexual"] is True

    @patch("main.call_vllm")
    @pytest.mark.asyncio
    async def test_moderate_malformed_response_fail_closed(self, mock_vllm):
        """Malformed response should fail closed (treat as unsafe)"""
        mock_vllm.return_value = "This is not a valid response"

        response = client.post(
            "/v1/moderations",
            json={"input": "Test"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should be flagged as unsafe (fail-closed)
        assert data["results"][0]["flagged"] is True

        # All categories should be flagged (conservative fail-closed)
        categories = data["results"][0]["categories"]
        assert all(v is True for v in categories.values())

    @patch("main.call_vllm")
    @pytest.mark.asyncio
    async def test_moderate_partial_malformed_fail_closed(self, mock_vllm):
        """Unsafe response with invalid category should fail closed"""
        mock_vllm.return_value = "unsafe\nINVALID_CATEGORY"

        response = client.post(
            "/v1/moderations",
            json={"input": "Test"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should be flagged as unsafe (fail-closed)
        assert data["results"][0]["flagged"] is True

        # All categories flagged (fail-closed)
        categories = data["results"][0]["categories"]
        assert all(v is True for v in categories.values())

    def test_moderate_empty_input_error(self):
        """Empty input should return 400"""
        response = client.post(
            "/v1/moderations",
            json={"input": []}
        )

        assert response.status_code == 400

    @patch("main.call_vllm")
    @pytest.mark.asyncio
    async def test_vllm_timeout_error(self, mock_vllm):
        """vLLM timeout should return 504"""
        from httpx import TimeoutException

        mock_vllm.side_effect = TimeoutException("Request timed out")

        response = client.post(
            "/v1/moderations",
            json={"input": "Test"}
        )

        assert response.status_code == 504
        assert "timed out" in response.json()["detail"].lower()

    @patch("main.call_vllm")
    @pytest.mark.asyncio
    async def test_vllm_http_error(self, mock_vllm):
        """vLLM HTTP error should return 502"""
        from httpx import HTTPError

        mock_vllm.side_effect = HTTPError("Connection failed")

        response = client.post(
            "/v1/moderations",
            json={"input": "Test"}
        )

        assert response.status_code == 502


class TestCategoryMapping:
    """Test Llama Guard to OpenAI category mapping"""

    @patch("main.call_vllm")
    @pytest.mark.asyncio
    async def test_all_categories_mapped(self, mock_vllm):
        """All Llama Guard categories should map to OpenAI categories"""
        # Test each category individually
        for llama_cat in LLAMA_GUARD_CATEGORIES.keys():
            mock_vllm.return_value = f"unsafe\n{llama_cat}"

            response = client.post(
                "/v1/moderations",
                json={"input": f"Test {llama_cat}"}
            )

            assert response.status_code == 200
            data = response.json()

            # Should have at least one OpenAI category flagged
            categories = data["results"][0]["categories"]
            assert any(v is True for v in categories.values()), \
                f"Category {llama_cat} not mapped to any OpenAI category"


class TestHealthEndpoint:
    """Test health check endpoint"""

    @patch("httpx.AsyncClient.get")
    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_get):
        """Health check should return 200 when vLLM is reachable"""
        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None
        mock_get.return_value = mock_response

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "vllm_url" in data

    @patch("httpx.AsyncClient.get")
    @pytest.mark.asyncio
    async def test_health_check_vllm_down(self, mock_get):
        """Health check should return 503 when vLLM is unreachable"""
        from httpx import HTTPError

        mock_get.side_effect = HTTPError("Connection refused")

        response = client.get("/health")

        assert response.status_code == 503
        assert "not available" in response.json()["detail"].lower()


class TestAuthentication:
    """Test optional API key authentication"""

    @patch("main.API_KEY", "test-api-key")
    @patch("main.call_vllm")
    @pytest.mark.asyncio
    async def test_valid_api_key(self, mock_vllm):
        """Valid API key should allow access"""
        mock_vllm.return_value = "safe"

        response = client.post(
            "/v1/moderations",
            json={"input": "Test"},
            headers={"Authorization": "Bearer test-api-key"}
        )

        assert response.status_code == 200

    @patch("main.API_KEY", "test-api-key")
    def test_invalid_api_key(self):
        """Invalid API key should return 401"""
        response = client.post(
            "/v1/moderations",
            json={"input": "Test"},
            headers={"Authorization": "Bearer wrong-key"}
        )

        assert response.status_code == 401

    @patch("main.API_KEY", "test-api-key")
    def test_missing_api_key(self):
        """Missing API key should return 401"""
        response = client.post(
            "/v1/moderations",
            json={"input": "Test"}
        )

        assert response.status_code == 401
