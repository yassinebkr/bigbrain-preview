"""Targeted recovery regression using the losslessly retained live failure."""
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zlib

import pytest

from bigbrain.research import CollectionRequest, ResearchState
from bigbrain.research_complement import ComplementRejected, complement_packet, target_diagnostics
from bigbrain.research_context import InspectionBudgetExceeded, policy_view


def live_trace():
    record = json.loads((Path(__file__).parent / 'fixtures/research_complement_live_20261027.json').read_text())
    raw = zlib.decompress(base64.b64decode(record['state']))
    assert hashlib.sha256(raw).hexdigest() == record['state_sha256']
    state = ResearchState.model_validate_json(raw)
    control = SimpleNamespace(complement=[CollectionRequest.model_validate(record['control_target'])],
        original_request_gaps=[state.original_request_coverage['gaps'][0]],
        questions=[SimpleNamespace(question_id=q['question_id'], missing_evidence=q['missing_evidence'])
                   for q in state.question_coverage])
    return state, control


def test_exact_live_failure_fits_targeted_packet_without_general_context():
    state, control = live_trace()
    before = state.model_dump_json()
    with pytest.raises(InspectionBudgetExceeded):
        policy_view(state, byte_limit=5000)
    packet = complement_packet(state, control, {'seconds':70, 'pages':2})
    assert len(json.dumps(packet, ensure_ascii=False).encode()) < 5000
    assert packet['state']['original_request'] == state.original_request
    assert [s['id'] for s in packet['state']['sources']] == ['s2']
    assert {p['id'] for p in packet['state']['passages']} == {'s2:p1', 's2:p2'}
    assert packet['state']['claims'] == []
    assert {d['type'] for d in packet['target_diagnostics']} == {'invalid_target', 'already_inspected'}
    assert packet['targets'][0]['focus'] == 'Path.unlink'
    assert packet['targets'][0]['group_ids'] == control.complement[0].group_ids
    assert state.model_dump_json() == before


def test_removing_selector_conflict_still_detects_the_repeated_inspection():
    state, control = live_trace()
    target = control.complement[0].model_copy(update={'focus':None})
    assert [d['type'] for d in target_diagnostics(state, [target])] == ['already_inspected']


def test_targeted_packet_does_not_grow_with_prior_drafts_and_audits():
    state, control = live_trace()
    original = complement_packet(state, control, {})
    state.claims[0].text += 'Unrelated reviewed material. ' * 10000
    state.assessments.extend([{'rationale':'Prior audit data. ' * 1000}] * 20)
    assert complement_packet(state, control, {}) == original


def test_targeted_packet_keeps_observed_passages_atomic():
    state, control = live_trace()
    with pytest.raises(InspectionBudgetExceeded):
        complement_packet(state, control, {}, byte_limit=500)


def test_valid_new_target_remains_eligible_for_recovery():
    state, control = live_trace()
    control.complement = [CollectionRequest(tool='visit', question_id='q1',
        url='https://reference.test/qualification', rationale='Inspect the missing documented condition')]
    packet = complement_packet(state, control, {})
    assert not packet['target_diagnostics']
    assert packet['state']['sources'] == packet['state']['passages'] == []


@pytest.mark.asyncio
async def test_invalid_control_target_preserves_supported_claims_and_stops_before_another_call():
    from tests.test_research_workflow import StageInference, journey
    class InvalidRecovery(StageInference):
        async def complete(self, prompt, **kwargs):
            raw = await super().complete(prompt, **kwargs)
            if kwargs['tool_schema']['name'] == 'research_control':
                report = json.loads(raw)
                report.update(original_request_complete=False, original_request_gaps=['Missing condition'],
                    complement=[dict(tool='open', question_id='q1', source_id='s1',
                        rationale='Inspect condition', focus='condition', group_ids=['invented'],
                        observation_sha256='a'*64)])
                return json.dumps(report)
            return raw
    state, runtime, _ = await journey(InvalidRecovery())
    assert state.execution_outcome == 'partial'
    assert state.diagnostic['code'] == 'complement_preflight'
    assert runtime.model_calls == 4
    assert state.claims[0].status == 'supported'
    assert state.assessments
