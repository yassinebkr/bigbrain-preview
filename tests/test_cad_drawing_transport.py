"""Compact drawing round trips retain authority, uncertainty and crop provenance."""

import json

import pytest

from bigbrain.cad_drawings import DrawingSource, DrawingSpecification
from bigbrain.cad_drawing_transport import WIRE_VERSION, compact_drawing, expand_intake, intake_schema
from bigbrain.cad_intake import DrawingIntake
from tests.test_cad_drawings import drawing


def test_round_trip_restores_defaults_and_independent_regions():
    data = drawing()
    data['dimensions'][0]['sources'] = [{**data['sources'][0], 'region': [0.1, 0.2, 0.8, 0.9]}]
    data['dimensions'][0]['critical'] = False
    source = DrawingSource.model_validate(data['sources'][0])
    compact = compact_drawing(data, [source])
    assert 'sha256' not in json.dumps(compact)
    assert 'schema_version' not in json.dumps(compact)
    assert compact['dimensions'][0]['critical'] is False
    assert 'region' not in compact['sources'][0]
    assert compact['dimensions'][0]['sources'][0]['region'] == [0.1, 0.2, 0.8, 0.9]
    decoded = expand_intake({'wire_version': WIRE_VERSION, 'drawing': compact, 'question': None}, [source])
    assert DrawingIntake.model_validate(decoded).drawing == DrawingSpecification.model_validate(data)


@pytest.mark.parametrize('origin', ['user', 'derived', 'unresolved'])
def test_round_trip_retains_critical_dimension_evidence(origin):
    data = drawing()
    dimension = data['dimensions'][0]
    if origin == 'user':
        dimension.update(origin='user', user_message_id='m-2', user_quote='60 mm')
    elif origin == 'derived':
        second = {**dimension, 'id': 'half_width', 'value': 30, 'origin': 'derived',
                  'dependencies': ['width'], 'derivation': 'width / 2'}
        data['dimensions'].append(second)
    else:
        dimension.update(origin='unresolved', value=None)
    sources = [DrawingSource.model_validate(data['sources'][0])]
    compact = compact_drawing(data, sources)
    decoded = expand_intake({'wire_version': WIRE_VERSION, 'drawing': compact, 'question': 'Quelle cote ?'}, sources)
    assert DrawingIntake.model_validate(decoded).drawing == DrawingSpecification.model_validate(data)


@pytest.mark.parametrize('index', [True, -1, 1, 0.0, '0'])
def test_source_reference_requires_a_known_strict_integer(index):
    sources = [DrawingSource.model_validate(drawing()['sources'][0])]
    with pytest.raises(ValueError, match='source reference'):
        expand_intake({'wire_version': WIRE_VERSION, 'drawing': {'sources': [{'source_index': index}]}}, sources)


def test_transport_rejects_hash_override_invalid_region_and_foreign_encode():
    data = drawing()
    sources = [DrawingSource.model_validate(data['sources'][0])]
    for extra in ({'sha256': 'b' * 64}, {'region': [0, 0, 2, 1]}):
        with pytest.raises(ValueError):
            expand_intake({'wire_version': WIRE_VERSION, 'source': {'source_index': 0, **extra}}, sources)
    data['sources'][0] = {**data['sources'][0], 'sha256': 'b' * 64}
    data['dimensions'][0]['sources'] = data['sources']
    with pytest.raises(ValueError, match='ledger'):
        compact_drawing(data, sources)
    with pytest.raises(ValueError, match='version'):
        expand_intake({'wire_version': 'future'}, sources)


def test_provider_schema_omits_repeated_versions_and_source_hashes():
    schema = intake_schema(DrawingIntake.model_json_schema())
    assert schema['properties']['wire_version']['const'] == WIRE_VERSION
    assert 'schema_version' not in schema['properties']
    assert 'sha256' not in schema['$defs']['DrawingSource']['properties']
    assert 'region' in schema['$defs']['DrawingSource']['properties']


def test_full_image_default_is_independent_of_ledger_crop():
    data = drawing()
    ledger = [DrawingSource.model_validate({**data['sources'][0], 'region': [0.1, 0.1, 0.9, 0.9]})]
    encoded = compact_drawing(data, ledger)
    result = expand_intake({'wire_version': WIRE_VERSION, 'drawing': encoded, 'question': None}, ledger)
    assert DrawingIntake.model_validate(result).drawing == DrawingSpecification.model_validate(data)
