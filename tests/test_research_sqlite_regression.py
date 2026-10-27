"""Section-level recovery and optional review-budget admission regressions."""
from unittest.mock import AsyncMock

import pytest

from bigbrain.research import Action, ModelPolicy
from bigbrain.research_context import select
from tests.test_research_assessment import evidence


def test_complete_matching_section_survives_oversized_neighbour_packet():
    blocks = [
        {"id": "previous", "kind": "p", "context": ["Background"], "text": "Background. " * 600},
        {"id": "answer", "kind": "p", "context": ["Concurrency"],
         "text": "WAL permits concurrent readers and a writer. Only one writer can run at a time."},
        {"id": "following", "kind": "p", "context": ["Appendix"], "text": "Appendix. " * 600},
    ]
    selected, scope = select("WAL concurrent readers writer", blocks, "a" * 64, limit=500)
    assert [block["id"] for block in selected] == ["answer"]
    assert selected[0]["text"] == blocks[1]["text"]
    assert scope["status"] == "selected" and scope["coverage"] == "partial"
    assert len(scope["omitted_group_ids"]) == 2


def test_single_oversized_section_keeps_refinement_required():
    selected, scope = select("WAL", [{"id": "huge", "kind": "p", "context": [],
        "text": "WAL " * 500 + "Only under the documented conditions."}], "b" * 64, limit=500)
    assert selected == [] and scope["status"] == "needs_context"


@pytest.mark.asyncio
async def test_optional_correction_reserve_yields_to_viable_collection_path():
    provider = AsyncMock()
    provider.complete.return_value = Action(tool="search", question_id="q",
        query="official documentation", rationale="Collect the missing evidence").model_dump_json()
    policy = ModelPolicy(provider)
    policy.allowance = lambda *args: 20000
    await policy.choose(evidence(), {"tokens":70000, "actions":5,
        "review_reserve":40000, "single_review_reserve":20000,
        "review_attempts_reserved":2, "review_shares_context":False})
    assert policy.last_budget_decision["phase"] == "collecting"
    assert policy.last_budget_decision["review_attempts"] == 1
    assert policy.last_budget_decision["closing_units"] == 20000
    assert "Collection budget is closing" not in provider.complete.call_args.args[0]
