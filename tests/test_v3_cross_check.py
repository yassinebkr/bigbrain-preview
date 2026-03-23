"""Tests for V3 Cross-Provider Verification."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bigbrain.llm.mock_provider import MockLLMProvider
from bigbrain.llm.provider import LLMProvider
from bigbrain.verification.pipeline import VerificationLevel, VerificationResult
from bigbrain.verification.v3_cross_check import CrossProviderVerifier


class FakeLLMProvider(LLMProvider):
    """Fake LLM provider that returns a preconfigured response."""

    def __init__(self, response: str = ""):
        self.response = response
        self.last_prompt = None
        self.call_count = 0

    async def complete(self, prompt, model="default", stream=False, max_tokens=2048,
                       temperature=0.7, **kwargs):
        self.last_prompt = prompt
        self.call_count += 1
        return self.response

    async def chat_complete(self, messages, model="default", stream=False,
                            max_tokens=2048, temperature=0.7, **kwargs):
        self.call_count += 1
        return self.response

    def get_available_models(self):
        return ["fake-model"]

    def estimate_tokens(self, text):
        return len(text) // 4


class TestCrossProviderVerifier:
    """Test CrossProviderVerifier functionality."""

    @pytest.fixture
    def passing_review(self):
        return json.dumps({
            "passed": True,
            "score": 0.95,
            "feedback": "Output correctly addresses the task with no issues.",
            "issues": []
        })

    @pytest.fixture
    def failing_review(self):
        return json.dumps({
            "passed": False,
            "score": 0.3,
            "feedback": "Output has scope creep and missing requirements.",
            "issues": ["Added unrequested feature X", "Missing error handling"]
        })

    @pytest.mark.asyncio
    async def test_passing_review(self, passing_review):
        """Test that a passing LLM review yields a passed VerificationResult."""
        provider = FakeLLMProvider(response=passing_review)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify(
            {"success": True, "output": "Hello World"},
            {"task_description": "Write a hello world program"}
        )

        assert isinstance(result, VerificationResult)
        assert result.passed is True
        assert result.level == VerificationLevel.V3_CROSS_CHECK
        assert result.score == pytest.approx(0.95)
        assert "correctly addresses" in result.message
        assert result.details["issues"] == []
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_failing_review(self, failing_review):
        """Test that a failing LLM review yields a failed VerificationResult."""
        provider = FakeLLMProvider(response=failing_review)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify(
            {"success": True, "output": "complex output"},
            {"task_description": "Simple task"}
        )

        assert result.passed is False
        assert result.level == VerificationLevel.V3_CROSS_CHECK
        assert result.score == pytest.approx(0.3)
        assert len(result.details["issues"]) == 2
        assert "scope creep" in result.message.lower()

    @pytest.mark.asyncio
    async def test_review_with_task_payload_context(self, passing_review):
        """Test that task_payload context is properly extracted."""
        provider = FakeLLMProvider(response=passing_review)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify(
            {"success": True},
            {"task_payload": {"type": "execute_code", "code": "print('hi')"}}
        )

        assert result.passed is True
        # Check that the prompt included task info
        assert "execute_code" in provider.last_prompt
        assert "print('hi')" in provider.last_prompt

    @pytest.mark.asyncio
    async def test_review_with_query_in_payload(self, passing_review):
        """Test extraction of 'query' field from task_payload."""
        provider = FakeLLMProvider(response=passing_review)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify(
            {"success": True, "data": "research results"},
            {"task_payload": {"query": "What is quantum computing?"}}
        )

        assert result.passed is True
        assert "quantum computing" in provider.last_prompt

    @pytest.mark.asyncio
    async def test_malformed_json_response_fallback(self):
        """Test heuristic fallback when LLM returns non-JSON response."""
        provider = FakeLLMProvider(
            response="The output looks correct and addresses all requirements."
        )
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify(
            {"success": True},
            {"task_description": "Do something"}
        )

        # Heuristic should detect positive sentiment
        assert result.passed is True
        assert result.score > 0
        assert "Could not parse" in result.message

    @pytest.mark.asyncio
    async def test_malformed_json_negative_fallback(self):
        """Test heuristic fallback detects negative sentiment."""
        provider = FakeLLMProvider(
            response="The output is incorrect and has several errors. Missing key requirements."
        )
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify(
            {"success": True},
            {"task_description": "Some task"}
        )

        # Heuristic should detect negative sentiment
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_json_embedded_in_text(self):
        """Test extraction of JSON embedded within surrounding text."""
        review_json = json.dumps({
            "passed": True,
            "score": 0.88,
            "feedback": "Looks good overall.",
            "issues": ["Minor style nit"]
        })
        response = f"Here is my review:\n{review_json}\nEnd of review."
        provider = FakeLLMProvider(response=response)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify(
            {"output": "code"},
            {"task_description": "Write code"}
        )

        assert result.passed is True
        assert result.score == pytest.approx(0.88)
        assert len(result.details["issues"]) == 1

    @pytest.mark.asyncio
    async def test_llm_provider_exception(self):
        """Test graceful handling when LLM provider raises an exception."""
        provider = FakeLLMProvider(response="")
        # Make complete() raise
        provider.complete = AsyncMock(side_effect=RuntimeError("API connection failed"))
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify(
            {"success": True},
            {"task_description": "Some task"}
        )

        assert result.passed is False
        assert result.score == 0.0
        assert "Cross-check error" in result.message
        assert result.details["exception"] == "RuntimeError"

    @pytest.mark.asyncio
    async def test_string_data_formatting(self):
        """Test that string data is passed through directly."""
        review = json.dumps({"passed": True, "score": 0.9, "feedback": "OK", "issues": []})
        provider = FakeLLMProvider(response=review)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify(
            "This is raw string output from the brain",
            {"task_description": "Produce text output"}
        )

        assert result.passed is True
        assert "raw string output" in provider.last_prompt

    @pytest.mark.asyncio
    async def test_dict_data_formatting(self):
        """Test that dict data is JSON-formatted in the prompt."""
        review = json.dumps({"passed": True, "score": 0.9, "feedback": "OK", "issues": []})
        provider = FakeLLMProvider(response=review)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify(
            {"key": "value", "nested": {"a": 1}},
            {"task_description": "Produce structured output"}
        )

        assert result.passed is True
        # Dict should be JSON-serialized in the prompt
        assert '"key"' in provider.last_prompt
        assert '"value"' in provider.last_prompt

    @pytest.mark.asyncio
    async def test_no_task_description(self):
        """Test handling when no task description is available."""
        review = json.dumps({"passed": True, "score": 0.8, "feedback": "OK", "issues": []})
        provider = FakeLLMProvider(response=review)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify({"success": True}, {})

        assert result.passed is True
        # Empty context defaults to task_payload={}, which falls back to type=unknown
        assert "unknown" in provider.last_prompt.lower()

    @pytest.mark.asyncio
    async def test_score_clamping(self):
        """Test that scores are clamped to [0, 1]."""
        review = json.dumps({
            "passed": True,
            "score": 1.5,  # Out of range
            "feedback": "Great",
            "issues": []
        })
        provider = FakeLLMProvider(response=review)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify({"success": True}, {"task_description": "task"})

        assert result.score == 1.0  # Clamped

    @pytest.mark.asyncio
    async def test_negative_score_clamping(self):
        """Test that negative scores are clamped to 0."""
        review = json.dumps({
            "passed": False,
            "score": -0.5,
            "feedback": "Bad",
            "issues": ["everything"]
        })
        provider = FakeLLMProvider(response=review)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify({"success": True}, {"task_description": "task"})

        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_custom_model_and_temperature(self):
        """Test that custom model and temperature are passed to LLM."""
        review = json.dumps({"passed": True, "score": 0.9, "feedback": "OK", "issues": []})
        provider = FakeLLMProvider(response=review)
        provider.complete = AsyncMock(return_value=review)

        verifier = CrossProviderVerifier(
            llm_provider=provider,
            model="custom-review-model",
            temperature=0.1,
            max_tokens=512,
        )

        await verifier.verify({"success": True}, {"task_description": "task"})

        provider.complete.assert_called_once()
        call_kwargs = provider.complete.call_args
        assert call_kwargs[1]["model"] == "custom-review-model"
        assert call_kwargs[1]["temperature"] == 0.1
        assert call_kwargs[1]["max_tokens"] == 512

    @pytest.mark.asyncio
    async def test_level_property(self):
        """Test level property returns V3_CROSS_CHECK."""
        provider = FakeLLMProvider()
        verifier = CrossProviderVerifier(llm_provider=provider)
        assert verifier.level == VerificationLevel.V3_CROSS_CHECK

    @pytest.mark.asyncio
    async def test_with_mock_llm_provider(self):
        """Test integration with the actual MockLLMProvider from bigbrain."""
        provider = MockLLMProvider(token_delay_ms=0, realistic_responses=False)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify(
            {"success": True, "output": "test"},
            {"task_description": "Run a test"}
        )

        # MockLLMProvider returns non-JSON responses, so fallback heuristic applies
        assert isinstance(result, VerificationResult)
        assert result.level == VerificationLevel.V3_CROSS_CHECK
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_issues_as_non_list(self):
        """Test handling when 'issues' is a string instead of list."""
        review = json.dumps({
            "passed": False,
            "score": 0.4,
            "feedback": "Has problems",
            "issues": "Single issue as string"
        })
        provider = FakeLLMProvider(response=review)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify({"success": True}, {"task_description": "task"})

        assert result.passed is False
        assert isinstance(result.details["issues"], list)
        assert result.details["issues"] == ["Single issue as string"]

    @pytest.mark.asyncio
    async def test_empty_context(self):
        """Test verify with None context."""
        review = json.dumps({"passed": True, "score": 0.9, "feedback": "OK", "issues": []})
        provider = FakeLLMProvider(response=review)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify({"success": True}, None)

        assert result.passed is True

    @pytest.mark.asyncio
    async def test_details_contain_raw_response(self, passing_review):
        """Test that details include the raw LLM response."""
        provider = FakeLLMProvider(response=passing_review)
        verifier = CrossProviderVerifier(llm_provider=provider)

        result = await verifier.verify(
            {"success": True},
            {"task_description": "task"}
        )

        assert "raw_response" in result.details
        assert result.details["raw_response"] == passing_review
        assert result.details["model_used"] == "default"
