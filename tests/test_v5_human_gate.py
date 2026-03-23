"""Tests for V5 Human Gate Verification."""

import asyncio
import time

import pytest

from bigbrain.verification.pipeline import VerificationLevel, VerificationResult
from bigbrain.verification.v5_human_gate import HumanGateVerifier, PendingVerification


class TestPendingVerification:
    """Test PendingVerification data class."""

    def test_create_pending(self):
        """Test creating a PendingVerification."""
        pending = PendingVerification(
            data={"output": "test"},
            context={"task_description": "do something"},
            description="Awaiting approval"
        )

        assert pending.data == {"output": "test"}
        assert pending.context == {"task_description": "do something"}
        assert pending.description == "Awaiting approval"
        assert pending.created_at > 0

    def test_to_dict(self):
        """Test serialization for UI display."""
        pending = PendingVerification(
            data="data",
            context={"key": "value"},
            description="Test pending"
        )

        d = pending.to_dict()

        assert d["description"] == "Test pending"
        assert "created_at" in d
        assert "age_seconds" in d
        assert d["age_seconds"] >= 0
        assert d["context_keys"] == ["key"]

    def test_to_dict_empty_context(self):
        """Test serialization with empty context."""
        pending = PendingVerification(data="d", context={}, description="x")
        d = pending.to_dict()
        assert d["context_keys"] == []


class TestHumanGateVerifier:
    """Test HumanGateVerifier functionality."""

    @pytest.mark.asyncio
    async def test_approve(self):
        """Test approving a pending gate."""
        verifier = HumanGateVerifier(timeout=5.0)

        async def approve_soon():
            await asyncio.sleep(0.05)
            verifier.approve(feedback="Looks good!")

        task = asyncio.create_task(approve_soon())

        result = await verifier.verify(
            {"output": "brain result"},
            {"task_description": "test task"}
        )

        await task

        assert isinstance(result, VerificationResult)
        assert result.passed is True
        assert result.level == VerificationLevel.V5_HUMAN_GATE
        assert result.score == 1.0
        assert "Looks good!" in result.message
        assert result.details["decision"] == "approved"
        assert result.details["feedback"] == "Looks good!"
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_reject(self):
        """Test rejecting a pending gate."""
        verifier = HumanGateVerifier(timeout=5.0)

        async def reject_soon():
            await asyncio.sleep(0.05)
            verifier.reject(reason="Output is wrong")

        task = asyncio.create_task(reject_soon())

        result = await verifier.verify(
            {"output": "bad result"},
            {"task_description": "test task"}
        )

        await task

        assert result.passed is False
        assert result.level == VerificationLevel.V5_HUMAN_GATE
        assert result.score == 0.0
        assert "Output is wrong" in result.message
        assert result.details["decision"] == "rejected"
        assert result.details["reason"] == "Output is wrong"

    @pytest.mark.asyncio
    async def test_approve_no_feedback(self):
        """Test approving without feedback."""
        verifier = HumanGateVerifier(timeout=5.0)

        async def approve_soon():
            await asyncio.sleep(0.05)
            verifier.approve()

        task = asyncio.create_task(approve_soon())
        result = await verifier.verify({"output": "ok"}, {})
        await task

        assert result.passed is True
        assert "Approved by human reviewer" in result.message
        assert result.details["feedback"] == ""

    @pytest.mark.asyncio
    async def test_reject_no_reason(self):
        """Test rejecting without reason."""
        verifier = HumanGateVerifier(timeout=5.0)

        async def reject_soon():
            await asyncio.sleep(0.05)
            verifier.reject()

        task = asyncio.create_task(reject_soon())
        result = await verifier.verify({"output": "nope"}, {})
        await task

        assert result.passed is False
        assert "Rejected by human reviewer" in result.message
        assert result.details["reason"] == ""

    @pytest.mark.asyncio
    async def test_timeout(self):
        """Test that gate times out correctly."""
        verifier = HumanGateVerifier(timeout=0.1)  # 100ms timeout

        start = time.time()
        result = await verifier.verify(
            {"output": "waiting..."},
            {"task_description": "will timeout"}
        )
        elapsed = time.time() - start

        assert result.passed is False
        assert result.level == VerificationLevel.V5_HUMAN_GATE
        assert result.score == 0.0
        assert "timed out" in result.message.lower()
        assert result.details["decision"] == "timeout"
        assert result.details["timeout_seconds"] == 0.1
        assert elapsed >= 0.1  # Should have waited at least timeout duration

    @pytest.mark.asyncio
    async def test_get_pending_while_waiting(self):
        """Test that get_pending() returns info while gate is active."""
        verifier = HumanGateVerifier(timeout=5.0)
        pending_result = []

        async def check_and_approve():
            await asyncio.sleep(0.05)
            pending = verifier.get_pending()
            pending_result.append(pending)
            verifier.approve()

        task = asyncio.create_task(check_and_approve())
        await verifier.verify(
            {"output": "data"},
            {"description": "Check this output"}
        )
        await task

        assert len(pending_result) == 1
        pending = pending_result[0]
        assert pending is not None
        assert pending["description"] == "Check this output"
        assert "created_at" in pending
        assert "age_seconds" in pending

    @pytest.mark.asyncio
    async def test_get_pending_when_idle(self):
        """Test that get_pending() returns None when no gate is active."""
        verifier = HumanGateVerifier()
        assert verifier.get_pending() is None

    @pytest.mark.asyncio
    async def test_get_pending_after_completion(self):
        """Test that get_pending() returns None after gate resolves."""
        verifier = HumanGateVerifier(timeout=5.0)

        async def approve_soon():
            await asyncio.sleep(0.05)
            verifier.approve()

        task = asyncio.create_task(approve_soon())
        await verifier.verify({"output": "data"}, {})
        await task

        # After completion, pending should be cleared
        assert verifier.get_pending() is None

    @pytest.mark.asyncio
    async def test_pending_after_timeout(self):
        """Test that pending is cleared after timeout."""
        verifier = HumanGateVerifier(timeout=0.05)
        await verifier.verify({"output": "data"}, {})
        assert verifier.get_pending() is None

    @pytest.mark.asyncio
    async def test_concurrent_gates_sequential(self):
        """Test that sequential verify calls work independently."""
        verifier = HumanGateVerifier(timeout=5.0)

        # First gate - approve
        async def approve_first():
            await asyncio.sleep(0.05)
            verifier.approve(feedback="First OK")

        task1 = asyncio.create_task(approve_first())
        result1 = await verifier.verify({"output": "first"}, {"description": "Gate 1"})
        await task1
        assert result1.passed is True
        assert "First OK" in result1.message

        # Second gate - reject
        async def reject_second():
            await asyncio.sleep(0.05)
            verifier.reject(reason="Second bad")

        task2 = asyncio.create_task(reject_second())
        result2 = await verifier.verify({"output": "second"}, {"description": "Gate 2"})
        await task2
        assert result2.passed is False
        assert "Second bad" in result2.message

    @pytest.mark.asyncio
    async def test_description_from_task_payload(self):
        """Test description extraction from task_payload."""
        verifier = HumanGateVerifier(timeout=5.0)
        pending_desc = []

        async def check_and_approve():
            await asyncio.sleep(0.05)
            p = verifier.get_pending()
            pending_desc.append(p["description"] if p else None)
            verifier.approve()

        task = asyncio.create_task(check_and_approve())
        await verifier.verify(
            {"output": "x"},
            {"task_payload": {"description": "Run analysis on dataset"}}
        )
        await task

        assert pending_desc[0] == "Run analysis on dataset"

    @pytest.mark.asyncio
    async def test_description_from_task_type(self):
        """Test description fallback to task type."""
        verifier = HumanGateVerifier(timeout=5.0)
        pending_desc = []

        async def check_and_approve():
            await asyncio.sleep(0.05)
            p = verifier.get_pending()
            pending_desc.append(p["description"] if p else None)
            verifier.approve()

        task = asyncio.create_task(check_and_approve())
        await verifier.verify(
            {"output": "x"},
            {"task_payload": {"type": "execute_code"}}
        )
        await task

        assert pending_desc[0] == "execute_code"

    @pytest.mark.asyncio
    async def test_default_timeout(self):
        """Test that default timeout is 300 seconds."""
        verifier = HumanGateVerifier()
        assert verifier.timeout == 300.0

    @pytest.mark.asyncio
    async def test_custom_timeout(self):
        """Test custom timeout value."""
        verifier = HumanGateVerifier(timeout=60.0)
        assert verifier.timeout == 60.0

    def test_level_property(self):
        """Test level property returns V5_HUMAN_GATE."""
        verifier = HumanGateVerifier()
        assert verifier.level == VerificationLevel.V5_HUMAN_GATE

    @pytest.mark.asyncio
    async def test_approve_before_verify_is_safe(self):
        """Test that calling approve/reject before verify doesn't crash."""
        verifier = HumanGateVerifier(timeout=5.0)
        # Should not raise
        verifier.approve(feedback="early")
        verifier.reject(reason="early")

    @pytest.mark.asyncio
    async def test_wait_time_in_details(self):
        """Test that wait_time is recorded in details."""
        verifier = HumanGateVerifier(timeout=5.0)

        async def approve_after_delay():
            await asyncio.sleep(0.1)
            verifier.approve()

        task = asyncio.create_task(approve_after_delay())
        result = await verifier.verify({"output": "x"}, {})
        await task

        assert result.details["wait_time"] >= 0.05  # Should be at least ~100ms

    @pytest.mark.asyncio
    async def test_none_context(self):
        """Test verify with None context."""
        verifier = HumanGateVerifier(timeout=5.0)

        async def approve_soon():
            await asyncio.sleep(0.05)
            verifier.approve()

        task = asyncio.create_task(approve_soon())
        result = await verifier.verify({"output": "x"}, None)
        await task

        assert result.passed is True
