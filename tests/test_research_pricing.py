"""Official reference price accounting and incomplete measurement coverage."""
from bigbrain.llm.usage import UsageRecord
from bigbrain.research_pricing import reference_cost


def test_subscription_reference_prices_cache_and_output_once():
    record = UsageRecord(model_id="gpt-6-luna", provider="codex", input_tokens=1000,
                         cached_input_tokens=500, output_tokens=200, reasoning_output_tokens=100,
                         total_tokens=1200)
    result = reference_cost([record], logical_calls=1)
    assert result["measured_subtotal_usd"] == .000155
    assert result["complete"]
    assert result["actual_subscription_charge_usd"] is None


def test_unknown_usage_and_aliases_keep_reference_coverage_incomplete():
    result = reference_cost([UsageRecord(model_id="unmapped", provider="fixture", total_tokens=10)], logical_calls=2)
    assert result["measured_subtotal_usd"] == 0
    assert not result["complete"]
    assert result["unavailable_models"] == ["unmapped"]


def test_absent_cache_measurement_leaves_reference_cost_unpriced():
    record = UsageRecord.from_openai_usage({'prompt_tokens': 100, 'completion_tokens': 10},
                                          model_id='gpt-6-luna', provider='codex')
    assert record.input_tokens_known and record.output_tokens_known
    assert not record.cached_input_tokens_known
    result = reference_cost([record], logical_calls=1)
    assert not result['complete']
    assert result['priced_records'] == 0
