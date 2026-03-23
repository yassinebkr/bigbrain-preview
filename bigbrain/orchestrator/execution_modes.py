"""Execution Modes - Per-brain autonomy configuration for BigBrain.

Defines how much autonomy each brain gets: full auto (lightning),
human-gated (control), or custom per-brain verification rules.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from ..verification.pipeline import VerificationLevel


class ExecutionMode(str, Enum):
    """Execution mode determining brain autonomy level."""
    LIGHTNING = "lightning"  # Full auto — no human gates
    CONTROL = "control"     # Human gate at every brain output
    CUSTOM = "custom"       # Per-brain configuration


@dataclass
class BrainExecutionConfig:
    """
    Per-brain execution configuration.

    Controls which verification levels run and whether human approval
    is required before results are delivered.

    Attributes:
        brain_name: Name of the brain this config applies to
        mode: Execution mode (lightning/control/custom)
        requires_approval: Whether V5 human gate is required before result delivery
        max_retries: Maximum V3 cross-check retry attempts before giving up
        verification_levels: Which V levels to run (None = all available)
    """
    brain_name: str
    mode: ExecutionMode = ExecutionMode.LIGHTNING
    requires_approval: bool = False
    max_retries: int = 3
    verification_levels: Optional[List[VerificationLevel]] = None

    def should_run_v3(self) -> bool:
        """Check if V3 cross-check should run for this brain."""
        if self.mode == ExecutionMode.LIGHTNING:
            return False
        if self.verification_levels is not None:
            return VerificationLevel.V3_CROSS_CHECK in self.verification_levels
        # CONTROL and CUSTOM with no explicit list: run all
        return True

    def should_run_v5(self) -> bool:
        """Check if V5 human gate should run for this brain."""
        if self.mode == ExecutionMode.LIGHTNING:
            return False
        if self.mode == ExecutionMode.CONTROL:
            return True
        # CUSTOM mode: check explicit config
        if self.requires_approval:
            return True
        if self.verification_levels is not None:
            return VerificationLevel.V5_HUMAN_GATE in self.verification_levels
        return False

    def get_effective_levels(self) -> List[VerificationLevel]:
        """Get the effective list of verification levels to run."""
        if self.mode == ExecutionMode.LIGHTNING:
            # Lightning mode: only fast deterministic + schema checks
            return [
                VerificationLevel.V4_DETERMINISTIC,
                VerificationLevel.V1_SCHEMA,
            ]

        if self.mode == ExecutionMode.CONTROL:
            # Control mode: all levels including human gate
            return [
                VerificationLevel.V4_DETERMINISTIC,
                VerificationLevel.V1_SCHEMA,
                VerificationLevel.V3_CROSS_CHECK,
                VerificationLevel.V5_HUMAN_GATE,
            ]

        # CUSTOM mode: use explicit levels or default to all
        if self.verification_levels is not None:
            return list(self.verification_levels)

        return [
            VerificationLevel.V4_DETERMINISTIC,
            VerificationLevel.V1_SCHEMA,
            VerificationLevel.V3_CROSS_CHECK,
            VerificationLevel.V5_HUMAN_GATE,
        ]
