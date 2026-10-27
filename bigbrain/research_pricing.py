"""Dated official API reference costs for observed research usage.

Subscription billing remains provider-owned. This snapshot estimates equivalent
standard short-context API costs and reports measurement coverage explicitly.
"""
from decimal import Decimal

SNAPSHOT = {
    "verified_on": "2026-10-26",
    "url": "https://developers.openai.com/api/docs/pricing",
    "currency": "USD",
    "tier": "Standard, short context, no regional uplift or cache writes",
    "rates_per_million": {
        "gpt-6.1-sol": {"input": "2.00", "cached_input": "0.10", "output": "10.00"},
        "gpt-6-luna": {"input": "0.10", "cached_input": "0.01", "output": "0.50"},
    },
}

# These mappings are declared explicitly from registry entries. Other aliases
# retain an unavailable estimate until their public model identity is verified.
ALIASES = {"codex-sol-6.1": "gpt-6.1-sol", "codex-luna-6": "gpt-6-luna",
           "openai/gpt-6.1-sol": "gpt-6.1-sol", "openai/gpt-6-luna": "gpt-6-luna"}


def reference_cost(records, *, logical_calls):
    """Price measured usage; reasoning is already included in output tokens."""
    subtotal = Decimal(0)
    priced = 0
    unavailable = []
    for record in records:
        model = ALIASES.get(record.model_id, record.model_id)
        rates = SNAPSHOT["rates_per_million"].get(model)
        if (rates is None or record.total_tokens <= 0 or record.cache_write_input_tokens
                or not 0 <= record.cached_input_tokens <= record.input_tokens):
            unavailable.append(record.model_id)
            continue
        subtotal += (Decimal(record.input_tokens - record.cached_input_tokens) * Decimal(rates["input"])
                     + Decimal(record.cached_input_tokens) * Decimal(rates["cached_input"])
                     + Decimal(record.output_tokens) * Decimal(rates["output"])) / Decimal(1_000_000)
        priced += 1
    return {"kind": "official_api_equivalent", "measured_subtotal_usd": float(subtotal),
            "priced_records": priced, "observed_records": len(records), "logical_calls": logical_calls,
            "complete": priced == logical_calls and not unavailable,
            "unavailable_models": sorted(set(unavailable)), "pricing_snapshot": SNAPSHOT,
            "actual_subscription_charge_usd": None,
            "limitations": ["Cache writes require their retention tier before an equivalent price can be established"]}
