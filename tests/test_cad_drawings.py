"""Drawing provenance and uncertainty gates before native geometry mutation."""

import pytest
from pydantic import ValidationError

from bigbrain.cad_drawings import DrawingSpecification


def drawing():
    source = {'attachment_id': 'att-012345abcdef', 'sha256': 'a' * 64}
    return {'title': 'Stepped support', 'sources': [source], 'views': ['front', 'top'],
            'dimensions': [{'id': 'width', 'feature_id': 'body', 'label': 'Width',
                'kind': 'length', 'value': 60, 'unit': 'mm', 'origin': 'explicit',
                'sources': [source], 'annotation': '60'}]}


def test_explicit_dimension_keeps_source_and_region():
    spec = DrawingSpecification.model_validate(drawing()).require_resolved()
    assert spec.dimensions[0].sources[0].sha256 == 'a' * 64
    assert spec.dimensions[0].sources[0].region == (0, 0, 1, 1)


def test_critical_unreadable_dimension_requires_clarification():
    data = drawing()
    data['dimensions'][0].update(value=None, origin='unresolved', annotation='6?')
    spec = DrawingSpecification.model_validate(data)
    assert len(spec.clarification_questions()) == 1
    with pytest.raises(ValueError, match='clarification'):
        spec.require_resolved()


@pytest.mark.parametrize('change', [
    {'sources': [{'attachment_id': 'att-012345abcdef', 'sha256': 'b' * 64}]},
    {'origin': 'derived', 'dependencies': ['width'], 'derivation': 'same dimension'},
    {'origin': 'derived', 'dependencies': ['missing'], 'derivation': 'unknown'},
    {'value': float('nan')}, {'unit': 'degree'}, {'value': -1},
    {'sources': [{'attachment_id': 'att-012345abcdef', 'sha256': 'a' * 64,
                  'region': [0, 0, 2, 1]}]},
])
def test_invalid_evidence_and_derivations_fail_closed(change):
    data = drawing()
    data['dimensions'][0].update(change)
    with pytest.raises(ValidationError):
        DrawingSpecification.model_validate(data)


def test_conflict_blocks_even_with_numeric_dimension():
    data = drawing()
    data['issues'] = [{'id': 'conflict', 'question': 'Which width is correct, 60 or 65 mm?',
                      'reason': 'conflicting', 'dimension_ids': ['width']}]
    with pytest.raises(ValueError, match='60 or 65'):
        DrawingSpecification.model_validate(data).require_resolved()


def test_derived_dimension_preserves_units_and_dependencies():
    data = drawing()
    dimension = dict(data['dimensions'][0])
    dimension.update(id='half_width', value=30, origin='derived',
                     dependencies=['width'], derivation='width / 2')
    data['dimensions'].append(dimension)
    assert DrawingSpecification.model_validate(data).require_resolved().dimensions[1].value == 30
