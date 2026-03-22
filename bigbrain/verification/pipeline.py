"""Verification Pipeline - Multi-layer verification system for BigBrain."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ValidationError


class VerificationLevel(str, Enum):
    """Verification levels in order of execution (cheapest first)."""
    V1_SCHEMA = "v1_schema"              # Pydantic schema validation
    V2_SANDBOX = "v2_sandbox"            # OS-level isolation (not implemented in preview)
    V3_CROSS_CHECK = "v3_cross_check"    # Different-provider LLM review (mock in preview)
    V4_DETERMINISTIC = "v4_deterministic"  # Syntax, tests, types - no LLM
    V5_HUMAN_GATE = "v5_human_gate"      # Human approval (not implemented in preview)


@dataclass
class VerificationResult:
    """Result from a single verification step."""
    level: VerificationLevel
    passed: bool
    score: float = 0.0  # 0.0-1.0 confidence score
    message: str = ""
    details: Dict[str, Any] = None
    execution_time: float = 0.0
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}


@dataclass
class PipelineResult:
    """Result from complete verification pipeline."""
    passed: bool
    results: List[VerificationResult]
    total_time: float = 0.0
    failed_at_level: Optional[VerificationLevel] = None
    
    def get_result(self, level: VerificationLevel) -> Optional[VerificationResult]:
        """Get result for a specific verification level."""
        for result in self.results:
            if result.level == level:
                return result
        return None
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of verification results."""
        return {
            "passed": self.passed,
            "total_time": self.total_time,
            "levels_checked": len(self.results),
            "failed_at": self.failed_at_level.value if self.failed_at_level else None,
            "scores": {r.level.value: r.score for r in self.results}
        }


class BaseVerifier(ABC):
    """Base class for verification implementations."""
    
    @abstractmethod
    async def verify(self, data: Any, context: Dict[str, Any] = None) -> VerificationResult:
        """
        Verify the given data.
        
        Args:
            data: Data to verify (code, result, etc.)
            context: Additional context for verification
            
        Returns:
            VerificationResult with pass/fail and details
        """
        pass
    
    @property
    @abstractmethod
    def level(self) -> VerificationLevel:
        """The verification level this verifier implements."""
        pass


class VerificationPipeline:
    """
    Multi-layer verification pipeline for BigBrain.
    
    Implements the 5-layer verification system with configurable verifiers.
    Executes in order from cheapest to most expensive:
    V4 (deterministic) → V1 (schema) → V3 (cross-check) → V5 (human gate)
    
    Key Features:
    - Fail-fast: stops at first failed verification
    - Async execution for performance
    - Detailed logging and timing
    - Configurable per-brain verification rules
    """
    
    def __init__(self):
        """Initialize empty verification pipeline."""
        self.verifiers: Dict[VerificationLevel, BaseVerifier] = {}
        self.enabled_levels: List[VerificationLevel] = [
            VerificationLevel.V4_DETERMINISTIC,
            VerificationLevel.V1_SCHEMA
        ]
    
    def add_verifier(self, verifier: BaseVerifier) -> None:
        """Add a verifier to the pipeline."""
        self.verifiers[verifier.level] = verifier
    
    def set_enabled_levels(self, levels: List[VerificationLevel]) -> None:
        """Set which verification levels are enabled."""
        self.enabled_levels = levels
    
    async def verify(self, data: Any, context: Dict[str, Any] = None) -> PipelineResult:
        """
        Run complete verification pipeline on data.
        
        Executes enabled verifiers in order, stopping at first failure.
        
        Args:
            data: Data to verify
            context: Additional context for verifiers
            
        Returns:
            PipelineResult with overall pass/fail and individual results
        """
        import time
        start_time = time.time()
        
        results = []
        context = context or {}
        
        # Execute verifiers in order
        for level in self.enabled_levels:
            verifier = self.verifiers.get(level)
            if not verifier:
                continue  # Skip missing verifiers
            
            try:
                result = await verifier.verify(data, context)
                results.append(result)
                
                # Stop on first failure (fail-fast)
                if not result.passed:
                    end_time = time.time()
                    return PipelineResult(
                        passed=False,
                        results=results,
                        total_time=end_time - start_time,
                        failed_at_level=level
                    )
                    
            except Exception as e:
                # Verifier itself failed - treat as verification failure
                error_result = VerificationResult(
                    level=level,
                    passed=False,
                    message=f"Verifier error: {str(e)}",
                    details={"exception": type(e).__name__, "traceback": str(e)}
                )
                results.append(error_result)
                
                end_time = time.time()
                return PipelineResult(
                    passed=False,
                    results=results,
                    total_time=end_time - start_time,
                    failed_at_level=level
                )
        
        # All verifications passed
        end_time = time.time()
        return PipelineResult(
            passed=True,
            results=results,
            total_time=end_time - start_time
        )
    
    async def verify_code_execution(self, code: str, result: Dict[str, Any],
                                   expected_schema: Type[BaseModel] = None) -> PipelineResult:
        """
        Convenience method for verifying code execution results.
        
        Common use case: verify Python brain output meets requirements.
        """
        context = {
            "code": code,
            "result": result,
            "expected_schema": expected_schema,
            "verification_type": "code_execution"
        }
        
        # For code execution, we typically verify the result, not the code
        return await self.verify(result, context)
    
    async def verify_task_result(self, task_payload: Dict[str, Any], 
                                result: Dict[str, Any],
                                expected_schema: Type[BaseModel] = None) -> PipelineResult:
        """
        Convenience method for verifying task results.
        
        Common use case: verify brain output meets task requirements.
        """
        context = {
            "task_payload": task_payload,
            "result": result,
            "expected_schema": expected_schema,
            "verification_type": "task_result"
        }
        
        return await self.verify(result, context)
    
    def get_status(self) -> Dict[str, Any]:
        """Get pipeline configuration and status."""
        return {
            "enabled_levels": [level.value for level in self.enabled_levels],
            "available_verifiers": [level.value for level in self.verifiers.keys()],
            "verifier_count": len(self.verifiers)
        }


class MockVerifier(BaseVerifier):
    """Mock verifier for testing and development."""
    
    def __init__(self, level: VerificationLevel, should_pass: bool = True,
                 score: float = 1.0, message: str = "Mock verification"):
        self._level = level
        self.should_pass = should_pass
        self.score = score
        self.message = message
    
    async def verify(self, data: Any, context: Dict[str, Any] = None) -> VerificationResult:
        """Mock verification that always returns configured result."""
        await asyncio.sleep(0.01)  # Simulate processing time
        
        return VerificationResult(
            level=self._level,
            passed=self.should_pass,
            score=self.score,
            message=self.message,
            details={"mock": True, "data_type": type(data).__name__}
        )
    
    @property
    def level(self) -> VerificationLevel:
        return self._level