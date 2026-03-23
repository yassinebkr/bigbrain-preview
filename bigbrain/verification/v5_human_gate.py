"""V5 Human Gate Verification - Human approval gate for BigBrain.

Pauses execution and waits for explicit human approval or rejection
before allowing results to proceed through the pipeline.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .pipeline import BaseVerifier, VerificationLevel, VerificationResult


@dataclass
class PendingVerification:
    """Represents a verification waiting for human decision."""
    data: Any
    context: Dict[str, Any]
    created_at: float = field(default_factory=time.time)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize pending verification for UI display."""
        return {
            "description": self.description,
            "created_at": self.created_at,
            "age_seconds": time.time() - self.created_at,
            "context_keys": list(self.context.keys()) if self.context else [],
        }


class HumanGateVerifier(BaseVerifier):
    """
    V5 Human Gate Verifier — pauses and waits for human approval.

    When verify() is called, the verifier stores the pending verification
    and waits on an asyncio.Event. External code (UI, API, etc.) can then
    call approve() or reject() to resolve the gate.

    Key Features:
    - Async event-based waiting (non-blocking to the event loop)
    - Configurable timeout with automatic failure
    - Pending state inspection for UI rendering
    - Support for concurrent gates (each verify call is independent)
    - Approve/reject with optional feedback
    """

    def __init__(self, timeout: float = 300.0):
        """
        Initialize human gate verifier.

        Args:
            timeout: Maximum seconds to wait for human decision (default 300s = 5 min)
        """
        self.timeout = timeout

        # Internal state for the current pending gate
        self._event: Optional[asyncio.Event] = None
        self._approved: Optional[bool] = None
        self._feedback: str = ""
        self._pending: Optional[PendingVerification] = None

    async def verify(self, data: Any, context: Dict[str, Any] = None) -> VerificationResult:
        """
        Pause and wait for human approval.

        Creates a pending verification and waits for approve() or reject()
        to be called, or for the timeout to expire.

        Args:
            data: Data awaiting human review
            context: Additional context for the verification

        Returns:
            VerificationResult based on human decision or timeout
        """
        start_time = time.time()
        context = context or {}

        # Set up the gate
        self._event = asyncio.Event()
        self._approved = None
        self._feedback = ""

        # Build description for UI
        description = context.get("description", "")
        if not description:
            task_payload = context.get("task_payload", {})
            if isinstance(task_payload, dict):
                description = task_payload.get("description", task_payload.get("type", "Task awaiting approval"))
            else:
                description = "Task awaiting approval"

        self._pending = PendingVerification(
            data=data,
            context=context,
            created_at=start_time,
            description=str(description),
        )

        try:
            # Wait for human decision or timeout
            await asyncio.wait_for(self._event.wait(), timeout=self.timeout)

            end_time = time.time()
            if self._approved:
                return VerificationResult(
                    level=VerificationLevel.V5_HUMAN_GATE,
                    passed=True,
                    score=1.0,
                    message=self._feedback or "Approved by human reviewer",
                    details={
                        "decision": "approved",
                        "feedback": self._feedback,
                        "wait_time": end_time - start_time,
                    },
                    execution_time=end_time - start_time,
                )
            else:
                return VerificationResult(
                    level=VerificationLevel.V5_HUMAN_GATE,
                    passed=False,
                    score=0.0,
                    message=self._feedback or "Rejected by human reviewer",
                    details={
                        "decision": "rejected",
                        "reason": self._feedback,
                        "wait_time": end_time - start_time,
                    },
                    execution_time=end_time - start_time,
                )

        except asyncio.TimeoutError:
            end_time = time.time()
            return VerificationResult(
                level=VerificationLevel.V5_HUMAN_GATE,
                passed=False,
                score=0.0,
                message="Human gate timed out",
                details={
                    "decision": "timeout",
                    "timeout_seconds": self.timeout,
                    "wait_time": end_time - start_time,
                },
                execution_time=end_time - start_time,
            )
        finally:
            # Clean up pending state
            self._pending = None

    def approve(self, feedback: str = "") -> None:
        """
        Approve the pending verification.

        Args:
            feedback: Optional feedback from the human reviewer
        """
        self._approved = True
        self._feedback = feedback
        if self._event is not None:
            self._event.set()

    def reject(self, reason: str = "") -> None:
        """
        Reject the pending verification.

        Args:
            reason: Reason for rejection
        """
        self._approved = False
        self._feedback = reason
        if self._event is not None:
            self._event.set()

    def get_pending(self) -> Optional[Dict[str, Any]]:
        """
        Get the current pending verification for UI display.

        Returns:
            Dict with pending verification info, or None if no gate is active
        """
        if self._pending is not None:
            return self._pending.to_dict()
        return None

    @property
    def level(self) -> VerificationLevel:
        """This is a V5 (human gate) verifier."""
        return VerificationLevel.V5_HUMAN_GATE
