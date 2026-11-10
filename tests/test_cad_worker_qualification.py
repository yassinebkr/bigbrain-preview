"""Regression checks for the isolated worker acceptance comparator."""

from copy import deepcopy
from tools.check_cad_worker_qualification import verify


def evidence():
    value = {'timeline': [{'id': 1, 'name': 'Base', 'type': 'Extrude', 'error': None}],
             'params': [{'name': 'flange_thickness', 'expression': '50', 'value': 50}],
             'sketches': [{'id': 1, 'name': 'Profile', 'curves': 4, 'profiles': 1, 'dof': 0, 'status': 'solved'}],
             'bodies': [{'name': 'Body', 'closed': True, 'volume_mm3': 100,
                         'bbox': {'min': [0, 0, 0], 'max': [10, 10, 1]}}]}
    report = {'status': 'observed', 'clicks': 2, 'maxHostFrameGapMs': 14,
              **{key: deepcopy(value) for key in ('initial', 'edited', 'undone', 'reopened')}}
    report['edited']['params'][0].update(expression='51 mm', value=51)
    report['edited']['bodies'][0]['volume_mm3'] = 101
    return report, value, deepcopy(value)


def test_accepts_preserved_geometry_and_history():
    assert verify(*evidence()) == []


def test_rejects_missing_named_history():
    report, reference, native = evidence()
    native['timeline'].clear()
    assert 'native reopen: named history' in verify(report, reference, native)


def test_rejects_changed_native_geometry():
    report, reference, native = evidence()
    native['bodies'][0]['volume_mm3'] = 120
    assert 'native reopen: volume' in verify(report, reference, native)


def test_rejects_lost_constraints():
    report, reference, native = evidence()
    report['reopened']['sketches'][0]['dof'] = 1
    assert 'reopened: sketch constraints' in verify(report, reference, native)


def test_rejects_unresponsive_host():
    report, reference, native = evidence()
    report['maxHostFrameGapMs'] = 30000
    assert 'Host frame gap below 200 ms' in verify(report, reference, native)


def test_rejects_incomplete_campaign():
    report, reference, native = evidence()
    report['status'] = 'failed'
    assert verify(report, reference, native) == ['Campaign incomplete']
