"""Experimental direct research orchestration over the existing acquisition runtime."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from .research import (Action, Claim, CollectionRequest, Contract, EvidenceLink,
                       Observation, ResearchActionRejected, parse_model_contract)
from .research_direct_context import ObservedPassages, encoded
from .research_direct_controller import DirectController, DirectLimitReached, DirectLimits
from .research_direct_result import DirectConclusion, validate_conclusion


class DirectWindow(Contract):
    passage_id: str
    start: int = Field(ge=0, strict=True)
    end: int = Field(ge=1, strict=True)


class DirectDecision(Contract):
    kind: Literal['acquire', 'select', 'finish', 'clarify']
    requests: list[CollectionRequest] = Field(default_factory=list, max_length=4)
    conclusion: DirectConclusion | None = None
    clarification: str | None = Field(default=None, min_length=1, max_length=500)
    windows: list[DirectWindow] = Field(default_factory=list, max_length=8)
    catalog_source_id: str | None = None
    catalog_offset: int = Field(default=0, ge=0, strict=True)

    @model_validator(mode='after')
    def one_operation(self):
        if self.kind != 'select' and (self.catalog_source_id is not None or self.catalog_offset):
            raise ValueError('Catalog navigation belongs to local selection')
        if self.kind == 'acquire':
            if not self.requests or self.conclusion or self.clarification or self.windows:
                raise ValueError('Acquisition requires requests and its own operation')
            Action(tool='batch', question_id=self.requests[0].question_id,
                   rationale='Validate direct acquisition arguments', requests=self.requests)
        elif self.kind == 'select':
            if (not self.windows and self.catalog_source_id is None
                    or self.requests or self.conclusion or self.clarification):
                raise ValueError('Local selection requires its own bounded passage windows')
        elif self.kind == 'finish':
            if self.requests or self.clarification or self.windows or self.conclusion is None:
                raise ValueError('Finish requires a conclusion and its own operation')
        elif self.requests or self.conclusion or self.windows or not self.clarification or not self.clarification.strip():
            raise ValueError('Clarification requires its own nonempty question')
        return self


class DirectFinish(Contract):
    """The forced-final schema excludes further acquisition requests."""
    conclusion: DirectConclusion


@dataclass(frozen=True)
class DirectReply:
    value: dict | str
    input_units: int | None = None
    output_units: int | None = None


def model_packet(runtime, receipts, controller, mode, byte_limit, windows=(), catalog_source_id=None, catalog_offset=0,
                 compact=False):
    packet = {'mode': mode, 'working_set': {}, 'remaining': {
        'calls': controller.limits.calls - controller.calls,
        'input_units': max(0, controller.limits.input_units - controller.input_units),
        'output_units': max(0, controller.limits.output_units - controller.output_units)}}
    packet['remaining'].update({key: max(0, getattr(runtime.limits, key) - runtime.counts[key])
                                for key in ('searches', 'pages', 'browsers')})
    fixed_bytes = len(encoded(packet)) - 2
    packet['working_set'] = receipts.packet(runtime.state, byte_limit=byte_limit - fixed_bytes, windows=windows,
        catalog_source_id=catalog_source_id, catalog_offset=catalog_offset, compact=compact)
    assert len(encoded(packet)) <= byte_limit
    return packet


async def run_direct(runtime, adapter, *, limits=None, packet_bytes=12000, review_required=False):
    """Run the offline-testable loop through an explicit inference adapter.

    The adapter forecasts full protocol/native context and returns per-dimension
    usage through DirectReply. Acquisition, source limits and observations remain
    owned by ResearchRuntime. Worker selection and provider wiring are separate.
    """
    state = runtime.state
    if state is None or not state.questions:
        raise ValueError('Direct research requires an initialized immutable scope')
    controller = DirectController(limits=limits or DirectLimits())
    runtime.limits = runtime.limits.model_copy(update={name: min(getattr(runtime.limits, name),
        getattr(controller.limits, name)) for name in ('searches', 'pages', 'browsers')})
    receipts = ObservedPassages(require_exposure=True)
    attempted = set()
    state.delivery_mode = 'documentary'
    state.execution_outcome = 'running'
    acquisition_closed = False
    selected_windows = ()
    catalog_source_id, catalog_offset = None, 0
    candidates = []
    loop = asyncio.get_running_loop()
    started = loop.time()

    def remaining_seconds():
        return min(runtime.remaining()['seconds'], controller.limits.seconds - (loop.time() - started))

    def publish_budget():
        """Expose monitored direct admission through the shared UI budget contract."""
        state.usage['stage_budget'] = {
            'policy': 'monitored', 'input_units': controller.input_units,
            'output_units': controller.output_units, 'logical_calls': controller.calls,
            'input_limit': controller.limits.input_units,
            'output_limit': controller.limits.output_units, 'call_limit': controller.limits.calls,
            'threshold_exceeded': controller.input_units > controller.limits.input_units
                or controller.output_units > controller.limits.output_units,
            'excess_input_units': max(0, controller.input_units - controller.limits.input_units),
            'excess_output_units': max(0, controller.output_units - controller.limits.output_units)}
        from .research_pricing import reference_cost
        state.usage['api_reference'] = reference_cost(runtime.usage_records, logical_calls=controller.calls)
        # Reported totals remain separate from monitored reservations. A missing
        # dimension stays null even when another dimension was measured as zero.
        state.usage['reported_usage'] = {field: sum(getattr(record, field) for record in runtime.usage_records)
            if runtime.usage_records and len(runtime.usage_records) == controller.calls
                and all(getattr(record, field + '_known') for record in runtime.usage_records) else None
            for field in ('input_tokens', 'output_tokens', 'cached_input_tokens')}

    def settle(outcome, reason):
        if controller.pending is not None:
            controller.record(outcome='interrupted')
        controller.settle(outcome, reason)
        state.execution_outcome, state.reason = outcome, reason
        state.status = {'complete': 'completed', 'blocked': 'unavailable', 'failed': 'partial'}.get(outcome, outcome)
        state.answer_status = 'complete' if outcome == 'complete' else 'partial' if state.claims else 'unassessed'

    async def watch_stop(owner):
        while True:
            await asyncio.sleep(.05)
            if runtime.cancelled():
                owner.cancel()
                return

    watcher = asyncio.create_task(watch_stop(asyncio.current_task()))
    try:
        if runtime.limits.cost_usd is not None:
            raise ValueError('A hard cost ceiling requires a priced transport reservation adapter')
        async with asyncio.timeout(remaining_seconds()):
            while controller.outcome == 'running':
                if runtime.cancelled():
                    raise asyncio.CancelledError
                receipts.ingest(state)
                ordinary = model_packet(runtime, receipts, controller, 'decide', packet_bytes, selected_windows,
                                        catalog_source_id, catalog_offset, compact=getattr(adapter, 'compact_evidence', False))
                final = model_packet(runtime, receipts, controller, 'finish_only', packet_bytes, selected_windows,
                                     catalog_source_id, catalog_offset, compact=getattr(adapter, 'compact_evidence', False))
                decision_input, decision_output = adapter.forecast(ordinary, DirectDecision)
                finish_input, finish_output = adapter.forecast(final, DirectFinish)
                reservation = controller.admit(decision_input=decision_input, decision_output=decision_output,
                    finish_input=finish_input, finish_output=finish_output,
                    seconds_remaining=remaining_seconds(), force_finish=acquisition_closed)
                contract = DirectFinish if reservation.phase == 'finish' else DirectDecision
                state.phase = 'closing' if reservation.phase == 'finish' else 'collecting'
                state.workflow = {'version': 'direct-1', 'stage': reservation.phase}
                publish_budget()
                await runtime.emit({'stage': 'research_direct_decision', 'phase': reservation.phase})
                reply, call_outcome = None, 'failed'
                call_started = loop.time()
                submitted = final if reservation.phase == 'finish' else ordinary
                try:
                    receipts.expose(submitted)
                    reply = await adapter.infer(submitted, reservation, contract)
                    if not isinstance(reply, DirectReply):
                        raise TypeError('Direct inference adapter must return DirectReply')
                    call_outcome = 'ok'
                except asyncio.CancelledError:
                    call_outcome = 'cancelled' if runtime.cancelled() else 'interrupted'
                    raise
                except TimeoutError:
                    call_outcome = 'timeout'
                    raise
                finally:
                    controller.record(input_units=reply.input_units if reply else None,
                        output_units=reply.output_units if reply else None, outcome=call_outcome)
                    controller.records[-1]['seconds'] = round(loop.time() - call_started, 4)
                    controller.records[-1]['packet_bytes'] = len(encoded(submitted))
                    publish_budget()
                from .research_acquisition import artifact
                candidate = artifact(reply.value.encode() if isinstance(reply.value, str) else encoded(reply.value),
                    name='research-direct-provider-candidate.json',
                    metadata={'call': controller.calls, 'contract': contract.__name__})
                candidates.append({'call': controller.calls, 'artifact': candidate})
                state.usage['direct_candidates'] = candidates
                decision = (parse_model_contract(contract, reply.value) if isinstance(reply.value, str)
                            else contract.model_validate(reply.value))
                if isinstance(decision, DirectFinish) or decision.kind == 'finish':
                    result = validate_conclusion(decision.conclusion, state, receipts,
                                                 review_required=review_required)
                    state.claims = [Claim(id=f['id'], question_id=f['question_id'], text=f['text'],
                        status=f['semantic_support'], basis=f['scope_detail'], scope=f['scope'],
                        reasoning=f['reasoning'],
                        limitations=f['limitations'], evidence=[EvidenceLink(passage_id=c['passage_id'],
                            relation=c['relation']) for c in f['citations']]) for f in result['findings']]
                    state.assessments = result['evidence_audits']
                    state.question_coverage = result['question_coverage']
                    state.original_request_coverage = {'complete': result['outcome'] == 'complete',
                        'gaps': [g for q in result['questions'] for g in q['gaps']]}
                    state.usage['direct_result'] = result
                    gaps = state.original_request_coverage['gaps']
                    # Allow one targeted complement after a premature partial.
                    # Both the next decision and final synthesis must fit the
                    # current allowance before this opportunity is admitted.
                    if (gaps and isinstance(decision, DirectDecision)
                            and reservation.phase == 'decide'
                            and not state.usage.get('direct_complement')
                            and controller.calls + 2 <= controller.limits.calls
                            and remaining_seconds() > controller.limits.finish_seconds + 10
                            and not acquisition_closed):
                        next_packet = model_packet(runtime, receipts, controller, 'decide', packet_bytes,
                                                   compact=getattr(adapter, 'compact_evidence', False))
                        end_packet = model_packet(runtime, receipts, controller, 'finish_only', packet_bytes,
                                                  compact=getattr(adapter, 'compact_evidence', False))
                        next_input, next_output = adapter.forecast(next_packet, DirectDecision)
                        end_input, end_output = adapter.forecast(end_packet, DirectFinish)
                        if (controller.input_units + next_input + end_input <= controller.limits.input_units
                                and controller.output_units + next_output + end_output <= controller.limits.output_units):
                            state.usage['direct_complement'] = {'gaps': gaps, 'after_call': controller.calls}
                            await runtime.emit({'stage': 'research_direct_complement',
                                                'remaining_requirements': gaps})
                            continue
                    blocked = not state.claims and any(s.status == 'inaccessible' for s in state.sources)
                    settle('blocked' if blocked else result['outcome'],
                           'Direct evidence synthesis settled with explicit coverage and review status')
                    break
                if decision.kind == 'clarify':
                    settle('clarification', decision.clarification)
                    break
                # An acquisition decision that exhausts the model allowance cannot
                # start another read-and-synthesis cycle within this attempt.
                if (controller.input_units >= controller.limits.input_units
                        or controller.output_units >= controller.limits.output_units):
                    raise DirectLimitReached('Model threshold exhausted before acquisition')
                if decision.kind == 'select':
                    selected_windows = tuple((w.passage_id, w.start, w.end) for w in decision.windows)
                    catalog_source_id, catalog_offset = decision.catalog_source_id, decision.catalog_offset
                    continue
                action = Action(tool='batch', question_id=state.questions[0].id,
                    rationale='Execute direct research acquisitions', requests=decision.requests)
                index = max((o.index for o in state.observations), default=-1) + 1
                try:
                    runtime.validate_action(state, action, runtime.counts, attempted)
                except ResearchActionRejected as exc:
                    # A rejected proposal is feedback to the bounded controller.
                    # Validation completes before any acquisition in this batch.
                    observation = Observation(index=index, action=action, status='error',
                                              data={'error': str(exc), 'executed': False})
                    state.observations.append(observation)
                    await runtime.emit({'stage': 'research_observation',
                                        'observation': observation.model_dump(mode='json')})
                    continue
                runtime.current_action = action.model_dump(mode='json')
                await runtime.emit({'stage': 'research_action', 'index': index,
                                    'action': runtime.current_action})
                # Keep the conclusion time reserve while waiting for acquisition.
                acquisition_seconds = remaining_seconds() - controller.limits.finish_seconds
                if acquisition_seconds <= 0:
                    raise DirectLimitReached('Deadline reserved for final synthesis')
                try:
                    async with asyncio.timeout(acquisition_seconds):
                        observation = await runtime.execute(state, action, runtime.counts,
                                                            attempted, index, prevalidated=True)
                except TimeoutError:
                    acquisition_closed = True
                    observation = Observation(index=index, action=action, status='error', data={
                        'error': 'Acquisition allowance exhausted; remaining time reserved for synthesis',
                        'items': [o.model_dump(mode='json') for o in state.pending_observations]})
                state.observations.append(observation)
                selected_windows = ()
                catalog_source_id, catalog_offset = None, 0
                state.pending_observations = []
                runtime.current_action = None
                await runtime.emit({'stage': 'research_observation', 'observation': observation.model_dump(mode='json')})
    except asyncio.CancelledError:
        state.diagnostic = {'code': 'cancelled', 'message': 'Research cancelled during the active operation'}
        settle('cancelled', 'Research cancelled during the active operation')
    except (DirectLimitReached, TimeoutError) as exc:
        state.diagnostic = {'code': 'direct_budget', 'type': type(exc).__name__, 'message': str(exc)}
        settle('partial', str(exc) or 'Research deadline exhausted; observations retained')
    except Exception as exc:
        state.diagnostic = {**getattr(exc, 'diagnostic', {}), 'code': 'direct_failure',
                            'type': type(exc).__name__, 'message': str(exc)[:1000]}
        if candidates:
            state.diagnostic['candidate_artifact'] = candidates[-1]['artifact']
        if state.usage.get('direct_wire_candidates'):
            state.diagnostic['wire_candidate_artifact'] = state.usage['direct_wire_candidates'][-1]
        settle('failed', f'Direct research stopped: {type(exc).__name__}')
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        state.phase = 'settled'
        state.usage['direct_candidates'] = candidates
        publish_budget()
        runtime.current_action = None
        state.workflow = {'version': 'direct-1', 'stage': 'settle', 'outcome': controller.outcome,
            'budget': {'input_units': controller.input_units, 'output_units': controller.output_units,
                       'calls': controller.calls, 'records': controller.records},
            'history': controller.history}
    return state
