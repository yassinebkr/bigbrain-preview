"""Tests for token accounting (Phase 5)."""

import pytest

from bigbrain.llm.usage import (
    BudgetExceeded,
    UsageRecord,
    UsageTracker,
    estimate_cost_usd,
    get_tracker,
    register_price,
)


def test_from_openai_usage_plain_fields():
    record = UsageRecord.from_openai_usage(
        {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        model_id="openai/gpt-5.6-sol",
        provider="openai_compat",
        role="front",
    )
    assert record.input_tokens == 10
    assert record.output_tokens == 4
    assert record.total_tokens == 14
    assert record.role == "front"


def test_from_openai_usage_detailed_breakdown():
    """Cached tokens, cache writes and reasoning tokens are captured."""
    record = UsageRecord.from_openai_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "total_tokens": 140,
            "prompt_tokens_details": {"cached_tokens": 80, "cache_write_tokens": 5},
            "completion_tokens_details": {"reasoning_tokens": 25},
        },
        model_id="gpt-5.6-luna",
        provider="codex",
    )
    assert record.cached_input_tokens == 80
    assert record.cache_write_input_tokens == 5
    assert record.reasoning_output_tokens == 25
    assert record.billable_output_tokens == 40


def test_totals_aggregate_by_model():
    tracker = UsageTracker()
    tracker.record(UsageRecord(model_id="m1", provider="p", input_tokens=10,
                               output_tokens=5, total_tokens=15, role="front"))
    tracker.record(UsageRecord(model_id="m1", provider="p", input_tokens=20,
                               output_tokens=5, total_tokens=25, role="code"))
    tracker.record(UsageRecord(model_id="m2", provider="p", input_tokens=1,
                               output_tokens=1, total_tokens=2))
    totals = tracker.totals()
    assert totals["calls"] == 3
    assert totals["total_tokens"] == 42
    assert totals["by_model"]["m1"]["calls"] == 2
    assert totals["by_model"]["m1"]["total_tokens"] == 40


def test_budget_enforcement():
    tracker = UsageTracker(role_budgets={"front": 100, "code": 0})
    tracker.record(UsageRecord(model_id="m", provider="p", total_tokens=60,
                               role="front"))
    tracker.check_budget("front")  # under budget
    tracker.record(UsageRecord(model_id="m", provider="p", total_tokens=60,
                               role="front"))
    with pytest.raises(BudgetExceeded):
        tracker.check_budget("front")
    # Zero budget = check disabled.
    tracker.record(UsageRecord(model_id="m", provider="p", total_tokens=999,
                               role="code"))
    tracker.check_budget("code")


def test_cost_unknown_price_is_none():
    assert estimate_cost_usd("no-such-model", 1000, 1000) is None
    record = UsageRecord.from_openai_usage(
        {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        model_id="no-such-model",
        provider="openai_compat",
    )
    assert record.cost_usd is None


def test_cost_with_registered_price():
    register_price("priced-model", price_in=1.0, price_out=2.0)  # $/Mtok
    # 1M input + 1M output = $1 + $2 = $3
    assert estimate_cost_usd("priced-model", 1_000_000, 1_000_000) == pytest.approx(3.0)


def test_cost_with_env_price(monkeypatch):
    monkeypatch.setenv("BIGBRAIN_PRICE_ENV_MODEL_IN", "0.5")
    monkeypatch.setenv("BIGBRAIN_PRICE_ENV_MODEL_OUT", "1.5")
    assert estimate_cost_usd("env-model", 2_000_000, 1_000_000) == pytest.approx(2.5)


def test_tracker_singleton_and_reset():
    tracker = get_tracker()
    assert get_tracker() is tracker
    tracker.record(UsageRecord(model_id="m", provider="p", total_tokens=5))
    assert get_tracker().totals()["calls"] >= 1
    get_tracker().reset()
    assert get_tracker().totals()["calls"] == 0


def test_budget_from_env(monkeypatch):
    monkeypatch.setenv("BIGBRAIN_BUDGET_FRONT", "42")
    tracker = UsageTracker()
    assert tracker._role_budgets["front"] == 42
