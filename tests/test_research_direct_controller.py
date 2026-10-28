"""Direct-loop admission reserves synthesis and preserves monitored overruns."""
import pytest

from bigbrain.research_direct_controller import DirectController, DirectLimits, DirectLimitReached


def admit(controller, **kwargs):
    return controller.admit(**dict(decision_input=1000, decision_output=200,
        finish_input=2000, finish_output=1000, seconds_remaining=100, **kwargs))


def test_normal_decision_and_unknown_usage_consume_their_reservations():
    controller = DirectController()
    assert admit(controller).phase == 'decide'
    controller.record()
    assert (controller.input_units, controller.output_units, controller.calls) == (1000, 200, 1)
    assert not controller.records[0]['input_known']
    assert not controller.records[0]['output_known']


@pytest.mark.parametrize('field,value', [('input_units', 62000), ('output_units', 2900), ('calls', 6)])
def test_final_allowance_forces_finish_only(field, value):
    controller = DirectController()
    setattr(controller, field, value)
    assert admit(controller).phase == 'finish'
    controller.record(input_units=500, output_units=200)
    with pytest.raises(DirectLimitReached):
        admit(controller)
    controller.settle('partial', 'One requested aspect remains unestablished')


def test_clock_reserve_forces_finish():
    controller = DirectController()
    reservation = controller.admit(decision_input=100, decision_output=100,
        finish_input=100, finish_output=500, seconds_remaining=15)
    assert reservation.phase == 'finish'


@pytest.mark.parametrize('outcome', ['complete', 'partial', 'blocked', 'clarification', 'cancelled', 'failed'])
def test_every_terminal_outcome_is_durable_and_prevents_later_calls(outcome):
    controller = DirectController()
    controller.settle(outcome, 'Explicit test boundary')
    assert controller.history[-1]['outcome'] == outcome
    with pytest.raises(DirectLimitReached):
        admit(controller)
    with pytest.raises(ValueError, match='already settled'):
        controller.settle(outcome, 'Another terminal message')


def test_inflight_overrun_stops_subsequent_calls_and_preserves_partial_result():
    controller = DirectController()
    admit(controller)
    controller.record(input_units=65000, output_units=200)
    with pytest.raises(DirectLimitReached):
        admit(controller)
    controller.settle('partial', 'Input threshold exceeded during the previous call')
    assert controller.input_units == 65000
    assert controller.records[0]['input_known']


def test_usage_dimensions_are_independently_known():
    controller = DirectController()
    admit(controller)
    controller.record(input_units=300)
    assert controller.input_units == 300
    assert controller.output_units == 200
    assert controller.records[0]['input_known']
    assert not controller.records[0]['output_known']


def test_active_calls_require_accounting_even_when_cancelled():
    controller = DirectController()
    admit(controller)
    with pytest.raises(DirectLimitReached):
        admit(controller)
    with pytest.raises(ValueError, match='active model call'):
        controller.settle('cancelled', 'Stop requested')
    controller.record(outcome='cancelled')
    controller.settle('cancelled', 'Stop requested')
    assert len(controller.records) == 1


@pytest.mark.parametrize('remaining', [0, -1, float('nan'), float('inf')])
def test_expired_or_invalid_deadline_never_starts_a_model_call(remaining):
    controller = DirectController()
    with pytest.raises(DirectLimitReached):
        controller.admit(decision_input=100, decision_output=100, finish_input=100,
                         finish_output=100, seconds_remaining=remaining)
    assert controller.calls == 0


def test_final_output_allowance_is_clamped_to_remaining_units():
    controller = DirectController(output_units=3900)
    reservation = admit(controller)
    assert reservation.phase == 'finish'
    assert reservation.output_units == 100


@pytest.mark.parametrize('kwargs', [{'input_units': 0}, {'calls': True}, {'seconds': float('inf')},
                                   {'finish_seconds': 120}, {'output_units': -1}])
def test_invalid_limits_fail_before_an_attempt(kwargs):
    with pytest.raises(ValueError):
        DirectLimits(**kwargs)
