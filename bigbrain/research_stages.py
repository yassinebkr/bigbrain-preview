"""Finite research stages and the single targeted complement allowance."""
from dataclasses import dataclass, field
from typing import Literal

Stage = Literal["scope", "collect", "freeze", "draft", "control", "settle",
                "collect_complement", "freeze_new_revision", "revise"]

TRANSITIONS = {
    "scope": {"collect", "settle"},
    "collect": {"freeze", "settle"},
    "freeze": {"draft", "settle"},
    "draft": {"control", "settle"},
    "control": {"collect_complement", "settle"},
    "collect_complement": {"freeze_new_revision", "settle"},
    "freeze_new_revision": {"revise", "settle"},
    "revise": {"control", "settle"},
    "settle": set(),
}


@dataclass
class StageController:
    """Validate every transition and record one terminal outcome per attempt."""

    stage: Stage = "scope"
    complement_used: bool = False
    history: list[dict] = field(default_factory=list)
    outcome: str | None = None

    def advance(self, target: Stage, *, reason: str, closing_fits=True):
        if target not in TRANSITIONS[self.stage]:
            raise ValueError(f"Invalid research transition: {self.stage} -> {target}")
        if not reason.strip():
            raise ValueError("Research transitions require a reason")
        if target == "collect_complement":
            if self.complement_used:
                raise ValueError("Research complement allowance exhausted")
            if not closing_fits:
                raise ValueError("Research complement cannot fit its closing envelope")
            self.complement_used = True
        self.history.append({"from": self.stage, "to": target, "reason": reason})
        self.stage = target

    def settle(self, outcome: str, *, reason: str):
        """Settle once; duplicate or late completions are rejected."""
        if outcome not in {"complete", "partial", "blocked", "cancelled", "interrupted"}:
            raise ValueError("Unknown research outcome")
        self.advance("settle", reason=reason)
        self.outcome = outcome
