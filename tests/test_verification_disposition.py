"""Routing must follow evidence state, including simultaneous failures."""
import pytest

from bigbrain.verification.disposition import verification_disposition


@pytest.mark.parametrize('cause,action', [
    ('uninspected_evidence', 'inspect'), ('missing_test', 'extend_validation'),
    ('reproduced_defect', 'repair'), ('contradiction', 'stop'),
    ('environment_blocked', 'stop'), ('review_blocked', 'stop'),
])
def test_explicit_cause_selects_actor(cause, action):
    assert verification_disposition([{'stage': 'semantics', 'details': {'cause': cause}}])['action'] == action


@pytest.mark.parametrize('cause', ['contradiction', 'environment_blocked', 'uninspected_evidence'])
def test_failure_does_not_override_blocker_or_unread_evidence(cause):
    failures = [{'stage': 'tests', 'status': 'failed'},
                {'stage': 'semantics', 'details': {'cause': cause}}]
    assert verification_disposition(failures)['action'] == ('inspect' if cause == 'uninspected_evidence' else 'stop')


def test_unknown_failure_is_not_a_reproduced_defect():
    assert verification_disposition([{'stage': 'tests', 'details': {'reason': 'tests failed'}}])['action'] == 'stop'
    assert verification_disposition([{'stage': 'tests', 'status': 'failed'}])['action'] == 'repair'
    assert verification_disposition([{'stage': 'semantics', 'details': {
        'cause': 'missing_test', 'requires_arbitration': True}}])['action'] == 'stop'


def test_nonmandatory_stages_do_not_block_repair():
    assert verification_disposition([{'stage': 'tests', 'status': 'failed'},
        {'stage': 'preview', 'status': 'not_applicable'}])['action'] == 'repair'
    assert verification_disposition([{'stage': 'tests', 'status': 'not_applicable',
        'details': {'cause': 'missing_test'}}, {'stage': 'semantics',
        'details': {'cause': 'awaiting_checks'}}])['action'] == 'extend_validation'


def test_review_waits_for_repaired_checks_without_inventing_contradiction():
    assert verification_disposition([{'stage': 'tests', 'status': 'failed'},
        {'stage': 'semantics', 'details': {'cause': 'awaiting_checks'}}])['action'] == 'repair'
    assert verification_disposition([{'stage': 'semantics',
        'details': {'cause': 'awaiting_checks'}}])['action'] == 'stop'
