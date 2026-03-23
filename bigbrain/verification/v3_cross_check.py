"""V3 Cross-Provider Verification - LLM-based cross-check for BigBrain.

Uses a different LLM provider to review another brain's output,
catching scope creep, subtle errors, and missing requirements.
"""

import json
import re
import time
from typing import Any, Dict, Optional

from ..llm.provider import LLMProvider
from .pipeline import BaseVerifier, VerificationLevel, VerificationResult


# Prompt template for cross-provider review
REVIEW_PROMPT_TEMPLATE = """\
You are a verification reviewer. Your job is to evaluate whether the following output \
correctly addresses the original task. Be thorough but fair.

## Original Task
{task_description}

## Brain Output
{brain_output}

## Review Instructions
Evaluate the output against these criteria:
1. **Correctness**: Does the output correctly address the original task?
2. **Completeness**: Are all requirements from the task fulfilled?
3. **Scope**: Is there any scope creep (work beyond what was asked)?
4. **Errors**: Are there any factual errors, bugs, or issues?

Respond in the following JSON format ONLY (no other text):
{{
    "passed": true or false,
    "score": 0.0 to 1.0,
    "feedback": "Brief summary of your assessment",
    "issues": ["list of specific issues found, if any"]
}}
"""


class CrossProviderVerifier(BaseVerifier):
    """
    V3 Cross-Provider Verifier using a different LLM to review output.

    Sends the brain's output along with the original task description
    to a separate LLM provider for independent review. This catches
    issues that the original brain may have missed or introduced.

    Key Features:
    - Uses a different LLM provider for unbiased review
    - Structured review prompt with clear criteria
    - Parses LLM response into pass/fail + score + feedback
    - Graceful error handling for malformed LLM responses
    - Configurable model and temperature for review
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        model: str = "default",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ):
        """
        Initialize cross-provider verifier.

        Args:
            llm_provider: LLM provider to use for review (should differ from the brain's provider)
            model: Model name to use for review
            temperature: Sampling temperature (lower = more deterministic review)
            max_tokens: Maximum tokens for the review response
        """
        self.llm_provider = llm_provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def verify(self, data: Any, context: Dict[str, Any] = None) -> VerificationResult:
        """
        Verify brain output by sending it to a different LLM for review.

        Args:
            data: The brain's output to verify
            context: Must contain 'task_description' or 'task_payload' for the original task

        Returns:
            VerificationResult with the cross-check assessment
        """
        start_time = time.time()
        context = context or {}

        try:
            # Extract task description from context
            task_description = self._extract_task_description(context)

            # Format brain output for review
            brain_output = self._format_brain_output(data)

            # Build the review prompt
            review_prompt = REVIEW_PROMPT_TEMPLATE.format(
                task_description=task_description,
                brain_output=brain_output,
            )

            # Send to LLM for review
            response = await self.llm_provider.complete(
                prompt=review_prompt,
                model=self.model,
                stream=False,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            # Parse the LLM response
            review = self._parse_review_response(response)

            end_time = time.time()
            return VerificationResult(
                level=VerificationLevel.V3_CROSS_CHECK,
                passed=review["passed"],
                score=review["score"],
                message=review["feedback"],
                details={
                    "issues": review["issues"],
                    "raw_response": response,
                    "model_used": self.model,
                    "task_description": task_description,
                },
                execution_time=end_time - start_time,
            )

        except Exception as e:
            end_time = time.time()
            return VerificationResult(
                level=VerificationLevel.V3_CROSS_CHECK,
                passed=False,
                score=0.0,
                message=f"Cross-check error: {str(e)}",
                details={
                    "exception": type(e).__name__,
                    "error": str(e),
                },
                execution_time=end_time - start_time,
            )

    @property
    def level(self) -> VerificationLevel:
        """This is a V3 (cross-check) verifier."""
        return VerificationLevel.V3_CROSS_CHECK

    def _extract_task_description(self, context: Dict[str, Any]) -> str:
        """Extract a human-readable task description from context."""
        # Direct task description
        if "task_description" in context:
            return str(context["task_description"])

        # From task_payload
        task_payload = context.get("task_payload", {})
        if isinstance(task_payload, dict):
            # Try common fields
            for field in ("description", "query", "task", "prompt", "instruction"):
                if field in task_payload:
                    return str(task_payload[field])
            # Fall back to type + code or full payload
            task_type = task_payload.get("type", "unknown")
            if "code" in task_payload:
                return f"Task type: {task_type}\nCode:\n{task_payload['code']}"
            return f"Task type: {task_type}\nPayload: {json.dumps(task_payload, default=str)}"

        return "No task description available"

    def _format_brain_output(self, data: Any) -> str:
        """Format brain output into a string for review."""
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            return json.dumps(data, indent=2, default=str)
        return str(data)

    def _parse_review_response(self, response: str) -> Dict[str, Any]:
        """
        Parse the LLM's review response into structured data.

        Attempts to extract JSON from the response. Falls back to
        heuristic parsing if strict JSON parsing fails.
        """
        # Try direct JSON parse
        try:
            parsed = json.loads(response.strip())
            return self._validate_review(parsed)
        except (json.JSONDecodeError, ValueError):
            pass

        # Try extracting JSON from within the response (e.g., surrounded by text)
        json_match = re.search(r'\{[^{}]*"passed"[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                return self._validate_review(parsed)
            except (json.JSONDecodeError, ValueError):
                pass

        # Heuristic fallback: try to determine pass/fail from text
        response_lower = response.lower()
        passed = not any(
            word in response_lower
            for word in ("fail", "incorrect", "wrong", "error", "missing", "reject")
        )
        return {
            "passed": passed,
            "score": 0.7 if passed else 0.3,
            "feedback": f"Could not parse structured review. Raw response: {response[:200]}",
            "issues": ["Review response was not in expected JSON format"],
        }

    def _validate_review(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize parsed review data."""
        passed = bool(parsed.get("passed", False))
        score = float(parsed.get("score", 1.0 if passed else 0.0))
        score = max(0.0, min(1.0, score))  # Clamp to [0, 1]
        feedback = str(parsed.get("feedback", ""))
        issues = parsed.get("issues", [])
        if not isinstance(issues, list):
            issues = [str(issues)]
        issues = [str(i) for i in issues]

        return {
            "passed": passed,
            "score": score,
            "feedback": feedback,
            "issues": issues,
        }
