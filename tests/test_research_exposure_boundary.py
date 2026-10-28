"""Exercise acquisition, forecast and inference exposure as separate boundaries."""
import pytest

from bigbrain.research_direct_context import ObservedPassages
from tests.test_research_direct_context import observed


def test_acquisition_and_forecast_do_not_authorize_a_citation():
    state = observed()
    store = ObservedPassages(require_exposure=True)
    store.ingest(state)
    receipt = store.get('s1:p0')
    packet = {'working_set': store.packet(state, byte_limit=12000)}
    with pytest.raises(ValueError, match='model-exposed'):
        store.citation(receipt.passage_id, receipt.capture_sha256,
                       receipt.text, receipt_id=receipt.identity)
    store.expose(packet)
    assert store.citation(receipt.passage_id, receipt.capture_sha256,
                          receipt.text, receipt_id=receipt.identity)['citation_integrity'] == 'verified'


def test_exposure_cannot_extend_beyond_submitted_window():
    store = ObservedPassages(require_exposure=True)
    store.ingest(observed())
    receipt = store.get('s1:p0')
    store.expose({'working_set': {'passages': [{'id': receipt.passage_id,
        'view_start': 0, 'view_end': 10, 'text': receipt.text[:10]}]}})
    with pytest.raises(ValueError, match='model-exposed'):
        store.citation(receipt.passage_id, receipt.capture_sha256,
                       receipt.text, receipt_id=receipt.identity)


def test_changed_capture_requires_fresh_exposure():
    store = ObservedPassages(require_exposure=True)
    state = observed()
    store.ingest(state)
    store.expose({'working_set': store.packet(state, byte_limit=12000)})
    state = observed(digest='b' * 64)
    store.ingest(state)
    receipt = store.get('s1:p0')
    with pytest.raises(ValueError, match='model-exposed'):
        store.citation(receipt.passage_id, receipt.capture_sha256,
                       receipt.text, receipt_id=receipt.identity)
