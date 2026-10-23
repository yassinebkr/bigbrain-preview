"""Generic pinned-source navigation; no provider calls or domain shortcuts."""
import json
from types import SimpleNamespace

import pytest

from bigbrain.verification import review_evidence as evidence
from bigbrain.verification.semantics import review_semantics
from tests.test_maintenance import recorded_stub_usage


@pytest.mark.asyncio
async def test_unread_assertion_request_continues_reviewer_without_worker():
    calls = []
    async def complete(**kwargs):
        recorded_stub_usage()
        calls.append(kwargs)
        if len(calls) == 1:
            return json.dumps({'decision': 'needs_evidence', 'contradictions': [], 'coverage': [],
                'missing_evidence': [{'criterion_id': '0', 'kind': 'executed_assertion',
                    'path': 'test_main.py', 'source_revision': 'current', 'request': 'Inspect output assertion'}]})
        snapshot = json.loads(kwargs['messages'][1]['content'])
        assert snapshot['observations'][-1]['pages'][0]['path'] == 'test_main.py'
        return json.dumps({'decision': 'needs_evidence', 'contradictions': [], 'coverage': [],
            'missing_evidence': [{'criterion_id': '0', 'kind': 'missing_test',
                'path': 'test_main.py', 'source_revision': 'current', 'request': 'Add an output assertion'}]})
    result = await review_semantics(SimpleNamespace(chat_complete=complete),
        request='Print six', contracts=['Print six'],
        sources={'main.py': '# filler\n' * 7000, 'test_main.py': 'def test_ok():\n    assert True\n'},
        tests={'status': 'passed', 'passed_cases': ['test_main.py::test_ok']}, progressive=True)
    assert len(calls) == 2
    assert result.details['cause'] == 'missing_test'
    assert result.details['next_action'] == 'extend_validation'


def test_exact_executed_symbols_include_class_async_and_parametrization():
    source = 'class Suite:\n    async def test_value(self):\n        assert 2 == 2\n'
    result = evidence.test_locations({'checks.py': source}, [
        'checks.py::Suite::test_value[2]', 'checks.py::missing', 'absent.py::test_value'])
    assert result['locations'] == [{'case': 'checks.py::Suite::test_value[2]',
        'path': 'checks.py', 'start': 2, 'end': 3}]


def test_unparseable_or_nonpython_cases_are_not_guessed():
    assert evidence.test_locations({'bad.py': 'broken(', 'suite.js': 'test("x")'},
        ['bad.py::test_x', 'suite.js::x'])['locations'] == []


def test_search_is_literal_paginated_and_does_not_access_disk():
    sources = {'module.ts': 'const value = ".*";\n' * 23, 'other.py': 'pass\n'}
    first = evidence.search_sources(sources, '.*')
    assert len(first['hits']) == 20 and first['next_offset'] == 20
    second = evidence.search_sources(sources, '.*', offset=20)
    assert [h['line'] for h in second['hits']] == [21, 22, 23]
    assert second['next_offset'] is None
    assert not evidence.search_sources(sources, 'missing')['hits']


@pytest.mark.parametrize('query,path,offset', [('', None, 0), ('x'*201, None, 0),
    ('x', '../secret', 0), ('x', [], 0), ('x', None, -1), ('x', None, True)])
def test_invalid_search_inputs_fail_closed(query, path, offset):
    with pytest.raises(ValueError):
        evidence.search_sources({'module.py': 'x'}, query, path, offset)


def test_grouped_pages_are_bounded_and_explicitly_truncated():
    pages = evidence.read_pages({'module.py': 'x'*100 + '\n' + 'y'*3400 + '\n'},
                                [{'path': 'module.py', 'start': 1, 'count': 2}])
    assert pages[0]['next_line'] == 2
    assert len(pages[0]['content']) <= 3500
    with pytest.raises(ValueError):
        evidence.read_pages({'module.py': 'pass'}, [{'path': '../secret', 'start': 1, 'count': 1}])
    with pytest.raises(ValueError):
        evidence.read_pages({'module.py': 'pass'}, [] )


@pytest.mark.asyncio
async def test_targeted_assertions_and_implementation_are_read_together():
    calls = []
    async def complete(**kwargs):
        calls.append(kwargs)
        recorded_stub_usage()
        context = json.loads(kwargs['messages'][1]['content'])
        if len(calls) == 1:
            locations = context['passing_test_locations']['locations']
            assert locations[0]['start'] == 3001
            return json.dumps({'action': {'type': 'read_many', 'pages': [
                {'path': 'test_value.py', 'start': 3001, 'count': 2},
                {'path': 'value.py', 'start': 1, 'count': 2}]}})
        assert len(context['observations'][-1]['pages']) == 2
        return json.dumps({'decision': 'pass', 'contradictions': [], 'coverage': [
            {'criterion_id': '0', 'tests': ['test_value.py::test_value'],
             'sources': ['value.py', 'test_value.py'], 'reason': 'Actual assertion calls value() and compares six'}]})
    result = await review_semantics(SimpleNamespace(chat_complete=complete),
        request='Return six', contracts=['value returns six'],
        sources={'value.py': 'def value():\n    return 6\n',
                 'test_value.py': '# padding\n'*3000 + 'def test_value():\n    assert value() == 6\n',
                 'other.ts': '// padding\n'*3000},
        tests={'status': 'passed', 'passed_cases': ['test_value.py::test_value']}, progressive=True)
    assert result.status == 'passed'
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_navigation_hits_do_not_authorize_unread_source_coverage():
    replies = iter([{'action': {'type': 'search', 'query': 'assert', 'path': None, 'offset': 0}},
        {'decision': 'pass', 'contradictions': [], 'coverage': [
            {'criterion_id': '0', 'tests': ['test_x.py::test_x'],
             'sources': ['test_x.py'], 'reason': 'Search hit only'}]}])
    async def complete(**kwargs):
        recorded_stub_usage()
        return json.dumps(next(replies))
    result = await review_semantics(SimpleNamespace(chat_complete=complete),
        request='x', contracts=['x'], sources={'x.py': '# large\n'*7000,
            'test_x.py': 'def test_x():\n    assert x()\n'},
        tests={'status': 'passed', 'passed_cases': ['test_x.py::test_x']}, progressive=True)
    assert result.status == 'inconclusive'
