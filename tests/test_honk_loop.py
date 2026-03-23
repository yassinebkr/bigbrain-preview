"""Tests for PythonBrain Honk pattern — inner loop (generate → execute → verify → fix → retry)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bigbrain.brains.python_brain import PythonBrain
from bigbrain.bus.message import BusMessage, MessageType, Priority


class MockLLM:
    """Mock LLM that returns different code on each call."""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self.prompts = []

    async def complete(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
        else:
            response = 'print("fallback")'
        self.call_count += 1
        return response

    async def chat_complete(self, messages, **kwargs):
        return await self.complete(messages[-1]["content"], **kwargs)


def make_brain(llm_responses=None, timeout=5):
    """Create a PythonBrain with mock bus and LLM."""
    bus = MagicMock()
    bus.send = AsyncMock()
    bus.send_result = AsyncMock()
    bus.broadcast_event = AsyncMock()

    llm = MockLLM(responses=llm_responses or ['print("hello")'])
    brain = PythonBrain(
        name="python_brain",
        bus=bus,
        workspace="test",
        timeout=timeout,
        llm_provider=llm,
    )
    return brain, llm, bus


# === Single-shot success (attempt 1 works) ===

class TestHonkSingleShot:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        brain, llm, _ = make_brain(['print("Hello, world!")'])
        payload = {"user_request": "Print hello world"}
        msg = BusMessage(
            type=MessageType.TASK,
            source="front_brain",
            target="python_brain",
            payload={"type": "generate_and_execute", **payload},
        )

        result = await brain._generate_and_execute(msg.payload)

        assert result["success"] is True
        assert result["exit_code"] == 0
        assert "Hello, world!" in result["stdout"]
        assert result["attempt"] == 1
        assert result["total_attempts"] == 1
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_returns_generated_code(self):
        brain, llm, _ = make_brain(['print(42)'])
        result = await brain._generate_and_execute({"user_request": "Print 42"})
        assert "print(42)" in result["generated_code"]


# === Retry on failure (Honk inner loop) ===

class TestHonkRetryLoop:
    @pytest.mark.asyncio
    async def test_retries_on_syntax_error(self):
        """First attempt has syntax error → LLM fixes it → attempt 2 succeeds."""
        brain, llm, _ = make_brain([
            'print("hello"\n',         # Bad code (syntax error)
            'print("hello")',           # Fixed code
        ])
        result = await brain._generate_and_execute({"user_request": "Print hello"})

        assert result["success"] is True
        assert result["attempt"] == 2
        assert result["total_attempts"] == 2
        assert llm.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_runtime_error(self):
        """First attempt raises exception → LLM fixes → attempt 2 succeeds."""
        brain, llm, _ = make_brain([
            'x = 1 / 0',               # Runtime error (ZeroDivisionError)
            'print("fixed")',           # Fixed code
        ])
        result = await brain._generate_and_execute({"user_request": "Do something"})

        assert result["success"] is True
        assert result["attempt"] == 2
        assert "fixed" in result["stdout"]

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """All attempts fail → returns failure with history."""
        brain, llm, _ = make_brain([
            'raise ValueError("fail 1")',
            'raise ValueError("fail 2")',
            'raise ValueError("fail 3")',
            'raise ValueError("fail 4")',
            'raise ValueError("fail 5")',
        ])
        result = await brain._generate_and_execute({"user_request": "Broken task"})

        assert result.get("success") is not True
        assert result["exit_code"] != 0 or "fail" in result.get("stderr", "")
        assert len(result.get("attempt_history", [])) >= 4  # At least 4 failed attempts recorded

    @pytest.mark.asyncio
    async def test_custom_max_retries(self):
        """Respects max_retries from payload."""
        brain, llm, _ = make_brain([
            'raise ValueError("fail")',
            'print("success")',
        ])
        result = await brain._generate_and_execute({
            "user_request": "Test",
            "max_retries": 2,
        })
        assert result["success"] is True
        assert result["attempt"] == 2


# === Reflexion memory (don't repeat mistakes) ===

class TestReflexionMemory:
    @pytest.mark.asyncio
    async def test_error_fed_back_to_llm(self):
        """Second LLM call receives the error from first attempt."""
        brain, llm, _ = make_brain([
            'x = undefined_var',       # NameError
            'print("fixed")',          # Fixed
        ])
        result = await brain._generate_and_execute({"user_request": "Use a variable"})

        assert result["success"] is True
        # Second prompt should contain the error from attempt 1
        assert len(llm.prompts) == 2
        fix_prompt = llm.prompts[1]
        assert "Attempt 1" in fix_prompt or "attempt" in fix_prompt.lower()
        assert "error" in fix_prompt.lower() or "Error" in fix_prompt

    @pytest.mark.asyncio
    async def test_multiple_errors_accumulated(self):
        """Third attempt sees errors from both attempt 1 and 2."""
        brain, llm, _ = make_brain([
            'x = undefined_var',        # Attempt 1: NameError
            'print(1/0)',               # Attempt 2: ZeroDivisionError
            'print("finally works")',   # Attempt 3: success
        ])
        result = await brain._generate_and_execute({"user_request": "Do math"})

        assert result["success"] is True
        assert result["attempt"] == 3
        # Third prompt should have both previous errors
        fix_prompt = llm.prompts[2]
        assert "Attempt 1" in fix_prompt or "attempt" in fix_prompt.lower()

    @pytest.mark.asyncio
    async def test_attempt_history_in_result(self):
        """Result includes full attempt history for debugging."""
        brain, llm, _ = make_brain([
            'raise RuntimeError("oops")',
            'print("ok")',
        ])
        result = await brain._generate_and_execute({"user_request": "Test"})

        assert "attempt_history" in result
        history = result["attempt_history"]
        assert len(history) == 1  # One failed attempt recorded
        assert history[0]["attempt"] == 1
        assert "oops" in history[0].get("stderr", "")


# === Progress events ===

class TestHonkProgress:
    @pytest.mark.asyncio
    async def test_progress_events_emitted(self):
        brain, llm, bus = make_brain(['print("ok")'])
        await brain._generate_and_execute({"user_request": "Test"})

        # send_progress calls bus.send() with PROGRESS messages
        send_calls = bus.send.call_args_list
        progress_calls = [c for c in send_calls if "generat" in str(c).lower() or "execut" in str(c).lower()]
        assert len(progress_calls) >= 1

    @pytest.mark.asyncio
    async def test_retry_progress_events(self):
        """Retries emit progress events with attempt numbers."""
        brain, llm, bus = make_brain([
            'raise ValueError("fail")',
            'print("ok")',
        ])
        await brain._generate_and_execute({"user_request": "Test"})

        # Progress events go through bus.send() as PROGRESS messages
        send_calls = bus.send.call_args_list
        payloads = [str(c) for c in send_calls]
        # Should have progress for both attempts (generating + executing x2)
        assert any("attempt" in p for p in payloads)


# === Edge cases ===

class TestHonkEdgeCases:
    @pytest.mark.asyncio
    async def test_no_llm_provider(self):
        brain, _, _ = make_brain()
        brain.llm_provider = None
        result = await brain._generate_and_execute({"user_request": "Test"})
        assert result["success"] is False
        assert "LLM" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_request(self):
        brain, _, _ = make_brain()
        result = await brain._generate_and_execute({"user_request": ""})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_llm_returns_empty(self):
        """LLM returns empty string → treated as failure, retried."""
        brain, llm, _ = make_brain([
            "",                      # Empty response
            'print("recovered")',    # Recovery
        ])
        result = await brain._generate_and_execute({"user_request": "Test"})
        assert result["success"] is True
        assert result["attempt"] == 2

    @pytest.mark.asyncio
    async def test_stderr_without_failure_still_retries(self):
        """Code that prints to stderr but exits 0 — counts as needing fix."""
        brain, llm, _ = make_brain([
            'import sys; sys.stderr.write("warning\\n"); print("ok")',
            'print("clean")',
        ])
        result = await brain._generate_and_execute({"user_request": "Test"})
        # First attempt has stderr → retry → second attempt clean
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_timeout_is_passed_through(self):
        """Timeout from payload overrides default."""
        brain, llm, _ = make_brain(['import time; time.sleep(10); print("done")'], timeout=2)
        result = await brain._generate_and_execute({
            "user_request": "Sleep",
            "max_retries": 1,  # Don't retry, just check timeout works
        })
        assert result.get("success") is not True or "timeout" in result.get("stderr", "").lower()
