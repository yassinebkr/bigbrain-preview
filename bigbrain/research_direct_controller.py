"""Deterministic admission and terminal states for the direct research loop."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Literal


class DirectLimitReached(ValueError):
    """The attempt has exhausted a monitored threshold or its deadline."""


@dataclass(frozen=True)
class DirectLimits:
    input_units: int = 64000
    output_units: int = 4000
    calls: int = 7
    searches: int = 3
    pages: int = 4
    browsers: int = 2
    seconds: float = 120
    finish_seconds: float = 20

    def __post_init__(self):
        for value in (self.input_units, self.output_units, self.calls, self.searches, self.pages):
            if type(value) is not int or value <= 0:
                raise ValueError('Call and unit limits must be positive integers')
        if type(self.browsers) is not int or self.browsers < 0:
            raise ValueError('Browser allowance must be a nonnegative integer')
        if not 0 < self.finish_seconds < self.seconds or not math.isfinite(self.seconds):
            raise ValueError('The finish reserve must fit inside a finite deadline')


@dataclass(frozen=True)
class CallReservation:
    phase: Literal['decide', 'finish']
    input_units: int
    output_units: int


@dataclass
class DirectController:
    """Reserve a finish opportunity before admitting another acquisition decision.

    Forecasts supplied by the adapter must include protocol and native retained
    context. Native usage replaces reservations when available. An in-flight
    overrun is recorded and prevents all subsequent calls, including finish.
    """
    limits: DirectLimits = field(default_factory=DirectLimits)
    input_units: int = 0
    output_units: int = 0
    calls: int = 0
    outcome: str = 'running'
    reason: str | None = None
    records: list = field(default_factory=list)
    pending: CallReservation | None = None
    finish_requested: bool = False
    history: list = field(default_factory=list)

    def _available(self, seconds_remaining):
        if self.outcome != 'running' or self.pending is not None or self.finish_requested:
            raise DirectLimitReached('The attempt is terminal or a model call is still active')
        if (seconds_remaining <= 0 or not math.isfinite(seconds_remaining)
                or self.calls >= self.limits.calls
                or self.input_units >= self.limits.input_units
                or self.output_units >= self.limits.output_units):
            raise DirectLimitReached('Research deadline or monitored threshold exhausted')

    def admit(self, *, decision_input, decision_output, finish_input, finish_output, seconds_remaining,
              force_finish=False):
        """Choose ordinary or finish-only schema before starting the model call."""
        self._available(seconds_remaining)
        for value in (decision_input, decision_output, finish_input, finish_output):
            if type(value) is not int or value <= 0:
                raise ValueError('Forecast units must be positive integers')
        if type(force_finish) is not bool:
            raise ValueError('The forced-finish signal must be a boolean')
        finish_only = (force_finish or self.calls + 1 >= self.limits.calls
            or seconds_remaining <= self.limits.finish_seconds
            or self.input_units + decision_input + finish_input > self.limits.input_units
            or self.output_units + decision_output + finish_output > self.limits.output_units)
        if finish_only and self.input_units + finish_input > self.limits.input_units:
            raise DirectLimitReached('Final synthesis forecast exceeds the remaining input allowance; retained findings remain available')
        reservation = CallReservation('finish' if finish_only else 'decide',
            finish_input if finish_only else decision_input,
            min(finish_output if finish_only else decision_output,
                self.limits.output_units - self.output_units))
        self.pending = reservation
        self.finish_requested = finish_only
        self.calls += 1
        self.history.append({'phase': reservation.phase, 'call': self.calls})
        return reservation

    def record(self, *, input_units=None, output_units=None, outcome='ok'):
        """Charge measured dimensions independently and reserve unknown dimensions."""
        if self.pending is None:
            raise ValueError('No active reservation exists')
        for value in (input_units, output_units):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError('Observed units must be nonnegative integers or unknown')
        reservation = self.pending
        incoming = reservation.input_units if input_units is None else input_units
        outgoing = reservation.output_units if output_units is None else output_units
        self.input_units += incoming
        self.output_units += outgoing
        self.records.append({'phase': reservation.phase, 'outcome': outcome,
            'input_units': incoming, 'output_units': outgoing,
            'input_known': input_units is not None, 'output_known': output_units is not None})
        self.pending = None

    def settle(self, outcome, reason):
        """Commit exactly one terminal outcome after the caller preserves evidence."""
        if self.outcome != 'running':
            raise ValueError('Research attempt already settled')
        if self.pending is not None:
            raise ValueError('Record the active model call before settling')
        if outcome not in {'complete', 'partial', 'blocked', 'clarification', 'cancelled', 'failed'}:
            raise ValueError('Unknown terminal research outcome')
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('Terminal outcomes require an explicit reason')
        self.outcome, self.reason = outcome, reason
        self.history.append({'outcome': outcome, 'reason': reason})
