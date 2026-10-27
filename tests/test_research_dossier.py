"""Evidence snapshot identity, isolation and checkpoint integrity."""
import pytest

from bigbrain.research import Question, ResearchState
from bigbrain.research_dossier import EvidenceDossier


def test_frozen_dossier_survives_state_changes_and_reload():
    state = ResearchState(objective="Compare the requested versions", questions=[
        Question(id="q1", text="Which versions?", evidence_needed="Versioned signatures")])
    dossier, _ = EvidenceDossier.freeze(state)
    state.objective = "Changed request"
    assert dossier.view()["objective"] == "Compare the requested versions"
    assert EvidenceDossier.restore(dossier.checkpoint()) == dossier
    view = dossier.view()
    view["objective"] = "Mutated consumer"
    assert dossier.view()["objective"] != view["objective"]


def test_dossier_rejects_checkpoint_tampering():
    dossier, _ = EvidenceDossier.freeze(ResearchState(objective="Original", questions=[]))
    record = dossier.checkpoint()
    record["packet"]["objective"] = "Replacement"
    with pytest.raises(ValueError, match="digest mismatch"):
        EvidenceDossier.restore(record)


def test_dossier_hash_is_stable_and_changes_with_request_constraints():
    state = ResearchState(objective="Compare versions", original_request="Compare versions 3.7 and 3.13",
                          questions=[Question(id="q1", text="Signature", evidence_needed="Versioned signature")])
    first, _ = EvidenceDossier.freeze(state)
    repeated, _ = EvidenceDossier.freeze(state)
    assert first == repeated
    state.original_request = "Compare versions 3.8 and 3.13"
    changed, _ = EvidenceDossier.freeze(state)
    assert changed.sha256 != first.sha256


def test_restored_dossier_rejects_an_invalid_revision():
    dossier, _ = EvidenceDossier.freeze(ResearchState(objective="Original", questions=[]))
    record = dossier.checkpoint()
    record['revision'] = 0
    with pytest.raises(ValueError, match="revision must be positive"):
        EvidenceDossier.restore(record)


def test_dossier_rejects_stale_capture_even_for_legacy_passages():
    from bigbrain.research import Source, Passage
    state = ResearchState(objective='Current API', questions=[], sources=[
        Source(id='s1', url='https://source.test/api', discovered_by='fixture', status='read', content_sha256='b'*64)],
        passages=[Passage(id='p1', source_id='s1', text='Earlier capture', observation_sha256='a'*64)])
    with pytest.raises(ValueError, match='current source capture'):
        EvidenceDossier.freeze(state)


def test_bounded_dossier_grows_to_preserve_consulted_evidence():
    from bigbrain.research import Source, Passage
    text = 'Condition and version qualification. ' * 220
    state = ResearchState(objective='Establish the complete qualified behavior', questions=[], sources=[
        Source(id='s1', url='https://source.test/api', discovered_by='fixture',
               status='read', content_sha256='a'*64)], passages=[
        Passage(id='p1', source_id='s1', text=text, observation_sha256='a'*64)])
    dossier, _ = EvidenceDossier.freeze_bounded(state)
    assert 6000 < len(dossier.payload) <= 24000
    assert dossier.view()['passages'][0]['text'] == text


def test_bounded_dossier_preserves_capture_integrity_errors(monkeypatch):
    from bigbrain.research_context import InspectionBudgetExceeded
    calls = []
    def freeze(cls, state, *, revision, byte_limit):
        calls.append(byte_limit)
        if byte_limit == 6000:
            raise InspectionBudgetExceeded('Required section exceeds envelope')
        raise ValueError('Capture integrity failure')
    monkeypatch.setattr(EvidenceDossier, 'freeze', classmethod(freeze))
    with pytest.raises(ValueError, match='Capture integrity'):
        EvidenceDossier.freeze_bounded(ResearchState(objective='Inspect', questions=[]))
    assert calls == [6000, 8000]


def test_bounded_dossier_exhaustion_has_a_finite_limit(monkeypatch):
    from bigbrain.research_context import InspectionBudgetExceeded
    calls = []
    def freeze(cls, state, *, revision, byte_limit):
        calls.append(byte_limit)
        raise InspectionBudgetExceeded('Required evidence too large')
    monkeypatch.setattr(EvidenceDossier, 'freeze', classmethod(freeze))
    with pytest.raises(InspectionBudgetExceeded):
        EvidenceDossier.freeze_bounded(ResearchState(objective='Inspect', questions=[]))
    assert calls == list(range(6000, 24001, 2000))
