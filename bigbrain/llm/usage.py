"""Token accounting for BigBrain — usage records, budgets, and cost tracking.

Port of the usage discipline from shopifast-local (canvas/server): every
provider records a UsageRecord with the full OpenAI-style usage breakdown
(input, cached input, cache-write, output, reasoning output), so per-role
budgets and cost reporting work identically across providers.

Cost estimation stays honest: prices are configurable per model via env
(``BIGBRAIN_PRICE_<KEY>_IN`` / ``_OUT`` in USD per million tokens) and a
model with no configured price reports ``cost_usd=None`` rather than a
guessed number.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

_usage_capture = ContextVar('inference_usage_capture', default=None)


@contextmanager
def capture_usage():
    """Task-local accounting, excluding concurrent conversations' records."""
    records = []
    token = _usage_capture.set(records)
    try:
        yield records
    finally:
        _usage_capture.reset(token)


@dataclass
class UsageRecord:
    """One completion's token usage, provider-agnostic.

    Field names follow the codex app-server usage event shape (verified
    live in shopifast-local against codex-cli 0.153.4), which maps 1:1 to
    the OpenAI usage object for API-key providers.
    """

    model_id: str
    provider: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: Optional[float] = None
    role: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def from_openai_usage(cls, usage: dict, model_id: str, provider: str,
                           role: Optional[str] = None) -> "UsageRecord":
        """Build a record from an OpenAI-style usage object.

        Accepts both the plain fields (prompt_tokens/completion_tokens) and
        the detailed breakdown (prompt_tokens_details.cached_tokens).
        """
        prompt_details = usage.get("prompt_tokens_details") or {}
        completion_details = usage.get("completion_tokens_details") or {}
        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        return cls(
            model_id=model_id,
            provider=provider,
            role=role,
            input_tokens=input_tokens,
            cached_input_tokens=int(prompt_details.get("cached_tokens") or 0),
            cache_write_input_tokens=int(prompt_details.get("cache_write_tokens") or 0),
            output_tokens=output_tokens,
            reasoning_output_tokens=int(completion_details.get("reasoning_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or (input_tokens + output_tokens)),
            # Subscription credits are not priced as API-key tokens.
            cost_usd=None if provider == 'codex' else estimate_cost_usd(model_id, input_tokens, output_tokens),
        )

    @property
    def billable_output_tokens(self) -> int:
        """Output tokens billed: reasoning shares the completion budget."""
        return self.output_tokens


# -- pricing (env-configurable, unknown price -> None) --------------------------

_PRICE_TABLE: dict[str, tuple[float, float]] = {}


def _price_for(model_id: str) -> Optional[tuple[float, float]]:
    """(input, output) USD per million tokens for a model, or None.

    Prices change often and guessing them would corrupt cost reports, so a
    price exists only if configured: either programmatically via
    register_price() (tests, deployments that fetch a live price sheet) or
    via env ``BIGBRAIN_PRICE_<SANITIZED>_IN`` / ``_OUT``.
    """
    if model_id in _PRICE_TABLE:
        return _PRICE_TABLE[model_id]
    sanitized = "".join(
        ch if ch.isalnum() else "_" for ch in model_id.upper()
    )
    try:
        price_in = float(os.environ[f"BIGBRAIN_PRICE_{sanitized}_IN"])
        price_out = float(os.environ[f"BIGBRAIN_PRICE_{sanitized}_OUT"])
    except (KeyError, ValueError):
        return None
    return price_in, price_out


def register_price(model_id: str, price_in: float, price_out: float) -> None:
    """Declare a model's USD price per million tokens (input, output)."""
    _PRICE_TABLE[model_id] = (float(price_in), float(price_out))


def estimate_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    price = _price_for(model_id)
    if price is None:
        return None
    return (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000


# -- budgets --------------------------------------------------------------------

DEFAULT_ROLE_BUDGETS = {
    # tokens per day, per role; 0 disables the budget check for that role.
    "front": 0,
    "code": 0,
    "planner": 0,
    "subagent": 0,
}


class BudgetExceeded(RuntimeError):
    """Raised when a role exceeds its configured token budget."""


class UsageTracker:
    """Thread-safe token ledger with per-role daily budgets."""

    def __init__(self, role_budgets: Optional[dict[str, int]] = None):
        self._records: list[UsageRecord] = []
        self._lock = threading.Lock()
        self._role_budgets = dict(role_budgets or self._load_env_budgets())

    @staticmethod
    def _load_env_budgets() -> dict[str, int]:
        budgets = dict(DEFAULT_ROLE_BUDGETS)
        for role in list(budgets):
            raw = os.environ.get(f"BIGBRAIN_BUDGET_{role.upper()}")
            if raw is not None:
                try:
                    budgets[role] = int(raw)
                except ValueError:
                    continue
        return budgets

    def record(self, record: UsageRecord) -> None:
        with self._lock:
            self._records.append(record)
        captured = _usage_capture.get()
        if captured is not None:
            captured.append(record)

    def check_budget(self, role: str) -> None:
        """Raise BudgetExceeded if ``role`` is over its daily token budget."""
        budget = self._role_budgets.get(role, 0)
        if budget <= 0:
            return
        spent = self.tokens_for_role(role)
        if spent > budget:
            raise BudgetExceeded(
                f"role '{role}' spent {spent} tokens (budget {budget})"
            )

    def tokens_for_role(self, role: str) -> int:
        with self._lock:
            return sum(r.total_tokens for r in self._records if r.role == role)

    def totals(self) -> dict:
        """Aggregate ledger totals (no secrets, no per-message content)."""
        with self._lock:
            records = list(self._records)
        by_model: dict[str, dict[str, int]] = {}
        for r in records:
            slot = by_model.setdefault(
                r.model_id,
                {"input_tokens": 0, "cached_input_tokens": 0, "cache_write_input_tokens": 0,
                 "output_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": 0, "calls": 0},
            )
            slot["input_tokens"] += r.input_tokens
            slot['cached_input_tokens'] += r.cached_input_tokens
            slot['cache_write_input_tokens'] += r.cache_write_input_tokens
            slot['reasoning_output_tokens'] += r.reasoning_output_tokens
            slot["output_tokens"] += r.output_tokens
            slot["total_tokens"] += r.total_tokens
            slot["calls"] += 1
        cost = sum(r.cost_usd for r in records if r.cost_usd is not None)
        return {
            "calls": len(records),
            "total_tokens": sum(r.total_tokens for r in records),
            "cost_usd": cost if records and all(r.cost_usd is not None for r in records) else None,
            "by_model": by_model,
        }

    def reset(self) -> None:
        with self._lock:
            self._records.clear()


_tracker: Optional[UsageTracker] = None


def get_tracker() -> UsageTracker:
    """Process-wide tracker singleton (providers use it automatically)."""
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
    return _tracker


def set_tracker_for_test(tracker: UsageTracker) -> None:
    """Test hook: replace the singleton tracker."""
    global _tracker
    _tracker = tracker
