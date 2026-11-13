"""Model-directed CAD execution with observed boundaries and durable recovery."""

from __future__ import annotations

import json
import time
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from .cad_contracts import Contract, Hash, Identity
from .cad_execution import CadExecutionStore, ExecutionGroup, digest
from .cad_stages import CadConstruction
from .cad_decision_transport import decision_tool_schema, parse_decision_response
from .solidcraft import CadCommandError, CadError, CadTimeoutError


class BasedDecision(Contract):
    base_checkpoint: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


class Execute(BasedDecision):
    operation: Literal['execute']
    group: ExecutionGroup


class Observe(BasedDecision):
    operation: Literal['observe']
    tool: Literal['inspect_design', 'body_topology', 'parameter_graph', 'precise_geometry', 'feature_definition']
    body: Identity | None = None
    feature: Identity | None = None
    question: str | None = Field(default=None, min_length=10, max_length=1000)


class Reference(BasedDecision):
    operation: Literal['reference']
    commands: tuple[str, ...] = Field(default=(), max_length=16)
    skills: tuple[str, ...] = Field(default=(), max_length=3)


class Revise(BasedDecision):
    operation: Literal['revise']
    checkpoint: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    reason: str = Field(min_length=10, max_length=1000)


class Complete(BasedDecision):
    operation: Literal['complete']


class Blocked(BasedDecision):
    operation: Literal['blocked']
    reason: str = Field(min_length=3, max_length=2000)


class ExecutionAuthorization(Contract):
    status: Literal['confirmed']
    contract_sha256: Hash
    definition_sha256: Hash
    design_id: Identity
    revision: int = Field(strict=True, ge=1)
    approval_plan_id: Identity
    document_id: Identity


class ContinuationAllowance(Contract):
    """Operator-recorded resource extension for one retained candidate."""

    contract_sha256: Hash
    definition_sha256: Hash
    document_id: Identity
    engine_sha256: Hash
    baseline_decisions: int = Field(strict=True, ge=0)
    baseline_failures: int = Field(strict=True, ge=0)
    additional_calls: int = Field(strict=True, ge=1, le=48)
    authorization_source: str = Field(min_length=10, max_length=1000)
    previous_authorization_sha256: Hash | None = None
    decision_ceiling: int | None = Field(default=None, strict=True, ge=1, le=256)
    command_capacity: Literal[64, 96] | None = None
    inspection_reserve: int | None = Field(default=None, strict=True, ge=0, le=12)
    stop_on_new_error: bool | None = None


Decision = TypeAdapter(Annotated[Execute | Observe | Reference | Revise | Complete | Blocked,
                               Field(discriminator='operation')])
ClosingDecision = TypeAdapter(Annotated[Complete | Blocked, Field(discriminator='operation')])


def boundary_diagnostics(group):
    """Stop proposals that defer a required solver or topology observation."""
    commands = [item.command for item in group.commands]
    if 'sketch.finish' in commands[:-1]:
        return ['End the group at sketch.finish; inspect solver state before the dependent operation.']
    finishes = {'solid.fillet', 'solid.chamfer'}
    if any(command in finishes for command in commands) and len(commands) != 1:
        return ['Select one finishing operation from the observed operand in its own execution group. '
                'Set its native history name with command.params.name; omit a separate timeline.rename '
                'and never predict a new feature ID.']
    return []


def group_fingerprint(group):
    """Identify the exact attempted inputs, workflow and material-removal scope."""
    return digest({'base': group.base_checkpoint,
        'commands': [c.model_dump(mode='json') for c in group.commands],
        'workflow': group.workflow.model_dump(mode='json'),
        'cut_intents': [c.model_dump(mode='json') for c in group.cut_intents]})


def observation_key(decision, design):
    """Validate each observation's targets before native I/O and identify its scope."""
    if not decision.question:
        raise ValueError('An observation requires the specific question it can answer')
    if decision.tool == 'feature_definition':
        if decision.feature not in {item['name'] for item in (design or {}).get('timeline', [])}:
            raise ValueError('Feature inspection requires an existing named history feature')
    elif decision.feature is not None:
        raise ValueError('A feature target requires feature_definition')
    if decision.tool == 'body_topology' and decision.body is None:
        raise ValueError('Topology observation requires an existing body')
    if decision.body is not None:
        if decision.tool not in {'body_topology', 'precise_geometry'}:
            raise ValueError('A body target requires body_topology or precise_geometry')
        if decision.body not in {body['name'] for body in (design or {}).get('bodies', [])}:
            raise ValueError('Observation requires an existing body')
    return decision.tool + ':' + (decision.feature or
        (decision.body if decision.tool == 'body_topology' else '') or '')


def decision_design(design):
    """Keep global parameters and solver state; detailed geometry stays retrievable."""
    def selected(items, keys):
        return [{key: value for key, value in item.items() if key in keys} for item in items]

    return {'params': design['params'],
        'timeline': selected(design['timeline'], {'id', 'name', 'type', 'kind', 'error', 'warning', 'suppressed', 'rolled_back'}),
        'sketches': selected(design['sketches'], {'id', 'name', 'status', 'dof', 'fully_constrained', 'failing', 'error'}),
        'bodies': selected(design['bodies'], {'id', 'name', 'bbox', 'closed', 'volume_mm3'})}


class CadConstructionDriver:
    """Keep model choices behind revision, observation and resource checks.

    The worker owns the document lock and total deadline. Every provider call
    uses its existing accounting wrapper. Persisted interaction/repair counters
    apply across resumptions; the complete-part delivery gate remains in CadBrain.
    """

    def __init__(self, provider, definition, reference, images, store: CadExecutionStore,
                 *, model=None, progress=None, max_decisions=64, authorization=None):
        if type(max_decisions) is not int or not 1 <= max_decisions <= 256:
            raise ValueError('CAD decision allowance must be between 1 and 256')
        self.provider, self.definition, self.reference = provider, definition, reference
        self.images, self.store, self.model, self.progress = images, store, model, progress
        self.max_decisions = max_decisions
        self.active_allowance = None
        self.authorization = ExecutionAuthorization.model_validate(authorization) if authorization is not None else None
        if self.authorization and (self.authorization.contract_sha256 != store.contract
                or self.authorization.definition_sha256 != digest(definition.model_dump(mode='json'))
                or self.authorization.document_id != store.root.name):
            raise CadError('CAD execution authorization differs from the confirmed definition or candidate')
        self.path = store.directory / 'controller.json'
        self.state = {'contract_sha256': store.contract, 'decisions': 0, 'failures': [],
                      'observations': {}, 'feedback': None, 'protocol_diagnostics': [], 'last_action': None}
        catalog_digest = digest(getattr(reference, 'catalog', {}))
        if self.path.exists():
            self.state = store._read(self.path)
            if self.state.get('contract_sha256') != store.contract:
                raise CadError('CAD controller contract changed')
            if self.state.get('catalog_sha256') != catalog_digest:
                raise CadError('CAD native catalog changed during continuation')
            if hasattr(reference, 'restore'):
                reference.restore(self.state.get('retrieved_reference', {}))
        self.state['catalog_sha256'] = catalog_digest

    def save(self):
        if hasattr(self.reference, 'retrieved'):
            self.state['retrieved_reference'] = self.reference.retrieved()
        self.store._write(self.path, self.state)

    def continuation(self):
        """Keep the original failure history and reserve calls through decisions."""
        path = self.store.directory / 'continuation.json'
        if not path.exists():
            return None
        grant = ContinuationAllowance.model_validate(self.store._read(path))
        if (grant.decision_ceiling is not None
                and grant.decision_ceiling < grant.baseline_decisions + grant.additional_calls):
            raise CadError('CAD decision extension cannot cover its authorized calls')
        if (grant.inspection_reserve or 0) >= grant.additional_calls:
            raise CadError('CAD inspection reserve leaves no construction calls')
        failures = len(self.state['failures']) + self.state.get('inspection_repairs', 0)
        if (grant.contract_sha256 != self.store.contract
                or grant.definition_sha256 != digest(self.definition.model_dump(mode='json'))
                or grant.document_id != self.store.root.name
                or grant.engine_sha256 != self.store.engine_build
                or grant.baseline_decisions > self.state['decisions']
                or grant.baseline_failures > failures):
            raise CadError('CAD continuation scope or baseline changed')
        identity = digest(grant.model_dump(mode='json', exclude_none=True))
        recorded = self.state.get('continuation_sha256')
        if recorded is not None and recorded != identity:
            if (grant.previous_authorization_sha256 != recorded
                    or grant.baseline_decisions != self.state['decisions']
                    or grant.baseline_failures != failures):
                raise CadError('CAD continuation authorization changed')
        history = self.state.setdefault('continuation_authorizations', {})
        if identity not in history:
            history[identity] = grant.model_dump(mode='json')
        self.state['continuation_sha256'] = identity
        self.active_allowance = grant
        self.save()
        return grant

    def repair_limit(self):
        grant = self.continuation()
        return (max(self.definition.max_repairs, grant.baseline_failures) + grant.additional_calls
                if grant else self.definition.max_repairs)

    async def emit(self, stage, detail):
        if self.progress:
            await self.progress(stage, detail)

    async def supply_topology(self, session):
        """Read current solid topology locally before asking for another decision."""
        chain = self.store.active()
        if not chain:
            return
        current = chain[-1]
        design = self.store.observations(current)['design']
        for body in design['bodies']:
            key = 'body_topology:' + body['name']
            cached = self.state['observations'].get(key)
            if cached and cached.get('checkpoint') == current.id:
                continue
            value = await session.tool('body_topology', {'body': body['name']})
            if value.get('body') != body['name']:
                raise CadError('CAD topology observation belongs to another body')
            self.state['observations'][key] = {'checkpoint': current.id,
                'source': 'runtime_native_read', 'result': value}
        self.save()

    async def decide(self, trace, packet, **request):
        """Retain the exact text decision inputs and provider outcome locally."""
        record = {'status': 'running', 'packet': packet,
                  'system': request['messages'][0]['content'],
                  'model': request['model'], 'max_tokens': request['max_tokens'],
                  'temperature': request['temperature'], 'image_count': len(self.images)}
        self.store._write(trace, record)
        from .llm.call_trace import trace_call
        from .llm.usage import capture_usage
        started = time.monotonic()
        try:
            # Share transport diagnostics with the Front Brain. The call ID ties
            # setup and generation timing to this exact retained decision.
            with capture_usage() as usage, trace_call(self.provider, 'cad.construction.decision',
                    correlation={'document_id': self.store.root.name,
                                 'checkpoint_id': packet['base_checkpoint'], 'decision_id': trace.stem},
                    records=usage) as call:
                record['call_id'] = call.call_id
                self.store._write(trace, record)
                raw = await self.provider.chat_complete(**request)
        except BaseException as error:
            self.store._write(trace, {**record, 'status': 'interrupted',
                                     'error_type': type(error).__name__, 'error': str(error)[:2000],
                                     'duration_ms': round((time.monotonic() - started) * 1000, 2)})
            from .cad_resources import CadBudgetExceeded
            self.state['recovery'] = {'kind': 'budget' if isinstance(error, CadBudgetExceeded) else 'provider',
                'checkpoint': packet['base_checkpoint']}
            self.save()
            raise
        self.store._write(trace, {**record, 'status': 'returned', 'response': raw,
                                 'duration_ms': round((time.monotonic() - started) * 1000, 2)})
        return raw

    async def finalize_decision(self, trace, packet, **request):
        """Spend conclusion reserve on a transition with no mutation authority."""
        from .cad_resources import inference_phase
        request['max_tokens'] = 1024
        request['tool_schema'] = decision_tool_schema(ClosingDecision.json_schema())
        request['messages'][0] = {'role':'system','content':
            'The authorized construction share is exhausted. Inspect the retained CAD evidence and '
            'return complete to request independent whole-part inspection, or blocked with the exact '
            'remaining issue. This phase permits no geometry change, ancestor revision or tool action. '
            'A complete decision establishes no validation claim: independent checks still govern delivery. '
            'Use the current base_checkpoint. Return one JSON decision matching '
            + 'the supplied native response schema. Wrap the response in decision.'}
        token = inference_phase.set('inspection')
        try:
            return await self.decide(trace, packet, **request)
        finally:
            inference_phase.reset(token)

    def groups(self):
        groups = []
        for checkpoint in self.store.active():
            value = self.store._read(self.store.directory / checkpoint.id / 'proposal.json')
            if digest(value) != checkpoint.proposal_sha256:
                raise CadError('CAD retained execution proposal changed')
            groups.append(ExecutionGroup.model_validate(value))
        return groups

    def failure_context(self):
        """Recover exact historical inputs using the retained attempt fingerprint."""
        result = []
        legacy = [f for f in self.state['failures'] if not f.get('proposal_ref')]
        proposals = {}
        if legacy:
            paths = list(self.store.directory.glob('*/proposal.json'))
            if len(paths) > 256:
                raise CadError('CAD failure provenance exceeds its inspection envelope')
            wanted = {f.get('fingerprint') for f in legacy}
            for path in paths:
                if path.parent.is_symlink() or len(path.parent.name) != 32:
                    continue
                if not (path.parent / 'failure.json').is_file():
                    continue
                group = ExecutionGroup.model_validate(self.store._read(path))
                fingerprint = group_fingerprint(group)
                if fingerprint in wanted:
                    proposals.setdefault(fingerprint, (path, group))
        for failure in self.state['failures']:
            item = {**failure, 'scope': 'historical_attempt',
                    'applicability': 'Compare the exact inputs and base state before applying this diagnostic to a new strategy.'}
            found = proposals.get(failure.get('fingerprint'))
            if failure.get('proposal_ref'):
                from pathlib import PurePosixPath
                ref = PurePosixPath(failure['proposal_ref'])
                if (len(ref.parts) != 3 or ref.parts[0] != 'execution-checkpoints'
                        or len(ref.parts[1]) != 32 or any(c not in '0123456789abcdef' for c in ref.parts[1])
                        or ref.parts[2] != 'proposal.json'):
                    raise CadError('CAD failed proposal identity changed')
                path = self.store.root / str(ref)
                if path.parent.is_symlink():
                    raise CadError('CAD failed proposal identity changed')
                value = self.store._read(path)
                if digest(value) != failure.get('proposal_sha256'):
                    raise CadError('CAD failed proposal changed')
                found = (path, ExecutionGroup.model_validate(value))
            if found:
                path, group = found
                if group_fingerprint(group) != failure.get('fingerprint'):
                    raise CadError('CAD failed proposal differs from its attempt fingerprint')
                item['attempt'] = {'base_checkpoint': group.base_checkpoint,
                    'proposal_ref': path.relative_to(self.store.root).as_posix(),
                    'proposal_sha256': digest(group.model_dump(mode='json')),
                    'commands': [c.model_dump(mode='json') for c in group.commands],
                    'provenance': 'fingerprint_matched_native_attempt'}
            else:
                item['attempt'] = {'provenance': 'unavailable'}
            diagnostic = failure.get('diagnostic', {})
            observation_ref = diagnostic.get('observation_ref')
            if observation_ref:
                # Intermediate gates retain the native warning in a separate
                # hash-bound record. Give repairs its precise cause and scope.
                import hashlib
                expected = (path.parent / 'rejected-observations.json'
                            if found else None)
                if (expected is None or observation_ref != expected.relative_to(self.store.root).as_posix()
                        or expected.is_symlink()):
                    raise CadError('CAD rejected observation identity changed')
                observations = self.store._read(expected)
                if hashlib.sha256(expected.read_bytes()).hexdigest() != diagnostic.get('observation_sha256'):
                    raise CadError('CAD rejected observation changed')
                item['native_feature_diagnostics'] = [
                    {key: feature.get(key) for key in
                     ('name', 'type', 'error', 'warning', 'suppressed', 'rolled_back', 'boolean_diagnostics')}
                    for feature in observations.get('design', {}).get('timeline', [])
                    if feature.get('error') or feature.get('warning')
                    or feature.get('suppressed') or feature.get('rolled_back')]
            result.append(item)
        return result

    def construction(self):
        groups = self.groups()
        if not groups:
            raise CadError('CAD completion requires constructed native geometry')
        commands, cuts = [], []
        for group in groups:
            for intent in group.cut_intents:
                cuts.append(intent.model_copy(update={'command_index': intent.command_index + len(commands)}))
            commands.extend(group.commands)
        return CadConstruction(title=self.definition.title, commands=tuple(commands),
            workflow=groups[-1].workflow, cut_intents=tuple(cuts), max_repairs=self.definition.max_repairs)

    def offline_diagnostics(self):
        """Retain scoped operator evidence across reference and revision decisions."""
        import hashlib
        records = self.state.get('offline_diagnostics', [])
        if len(records) > 8:
            raise CadError('CAD offline diagnosis envelope exceeded')
        result = []
        for record in records:
            name = record.get('name', '')
            if (not name.startswith('offline-diagnosis-') or not name.endswith('.json')
                    or '/' in name or '\\' in name):
                raise CadError('CAD offline diagnosis identity changed')
            path = self.store.directory / name
            if path.is_symlink():
                raise CadError('CAD offline diagnosis identity changed')
            value = self.store._read(path)
            if (hashlib.sha256(path.read_bytes()).hexdigest() != record.get('sha256')
                    or value.get('contract_sha256') != self.store.contract):
                raise CadError('CAD offline diagnosis scope changed')
            result.append(value)
        return result

    async def check_step(self, proposal, observations):
        sketches = {item.get('name') for item in observations['design']['sketches']}
        # Limit solver checks to constructed profiles; retain the complete
        # workflow for all global parameter and provenance checks.
        current_intent = proposal.workflow.model_copy(update={
            'sketches': tuple(item for item in proposal.workflow.sketches if item.name in sketches)})
        errors = current_intent.diagnostics(observations['design'], observations['parameter_graph'],
                                           self.definition.drawing)
        # A functional workflow can declare future history and bodies. Every
        # observed sketch and active feature still needs valid design intent.
        future_inventory = {'Native history differs from the named feature inventory',
                            'Native bodies differ from the named body inventory',
                            'Native sketch inventory differs from the declared sketches'}
        errors = [error for error in errors if error not in future_inventory]
        actual = observations['design']
        for key, declared in [('sketches', {item.name for item in proposal.workflow.sketches}),
                              ('timeline', {item.name for item in proposal.workflow.features}),
                              ('bodies', set(proposal.workflow.bodies))]:
            missing = {item.get('name') for item in actual[key]} - declared
            if missing:
                errors.append(f'Observed {key} contains undeclared construction objects: ' +
                              ', '.join(sorted(str(name) for name in missing)))
        return errors

    def packet(self):
        from .cad_native_compat import construction_guidance
        from .cad_resources import command_capacity
        from .cad_context import decision_observations
        chain = self.store.active()
        current = chain[-1] if chain else None
        groups = self.groups()
        grant = self.active_allowance
        ceiling = max(self.max_decisions, grant.decision_ceiling or 0) if grant else self.max_decisions
        remaining = min(ceiling - self.state['decisions'],
            grant.baseline_decisions + grant.additional_calls - (grant.inspection_reserve or 0) - self.state['decisions']) if grant else ceiling - self.state['decisions']
        # Reuse the hash-verified evidence collected when the head was accepted.
        # Additional observations apply only to that exact native checkpoint.
        evidence = self.store.observations(current) if current else None
        observations = ({'inspect_design:': {'checkpoint': current.id,
                            'source': 'accepted_checkpoint', 'result': evidence['design']},
                         'parameter_graph:': {'checkpoint': current.id,
                            'source': 'accepted_checkpoint', 'result': evidence['parameter_graph']}}
                        if current else {})
        observations.update({key: value for key, value in self.state['observations'].items()
                             if value.get('checkpoint') == (current.id if current else None)})
        current_design = decision_design(evidence['design']) if current else None
        return {'definition': self.definition.model_dump(mode='json'),
            'execution_authorization': self.authorization.model_dump(mode='json') if self.authorization else None,
            'engine_sha256': self.store.engine_build,
            'native_compatibility': construction_guidance(self.store.engine, self.store.engine_build),
            'base_checkpoint': current.id if current else None,
            'accepted_groups': [{'checkpoint': c.id, 'id': g.id, 'purpose': g.purpose}
                                for c, g in zip(chain, groups)],
            'accepted_workflow': groups[-1].workflow.model_dump(mode='json') if groups else None,
            'current_design': current_design,
            'pending_obligations': evidence.get('unresolved_obligations', []) if evidence else [],
            'construction_questions': {'origin': 'model_execution_group',
                'group': groups[-1].id if groups else None,
                'authority': 'Planning questions that may be answered, revised or replaced using evidence; final acceptance remains defined by the confirmed definition and runtime checks.',
                'items': evidence.get('unresolved_obligations', []) if evidence else []},
            'observation_coverage': {
                'inspect_design': 'Sketch planes, solver state, feature names/types and existing bodies; datum axis frames are absent.',
                'parameter_graph': 'Parameter dependencies, cycles and expression errors.',
                'feature_definition': 'Native definition and expression inputs for one named feature; referenced features can be inspected separately. Resolved datum frames are absent.',
                'body_topology': 'Faces and edges of an existing solid body.',
                'precise_geometry': 'STEP-backed existing solid geometry; construction axes and planes are excluded.'},
            'observations': decision_observations(observations, current_design), 'feedback': self.state['feedback'],
            'geometry_record_encoding': 'A columnar-records-v1 value represents exact records. Each group has columns and rows; zip columns with each row. positions gives each record original position. Native IDs, coordinates, precision and nested values are preserved. A $ref such as #/current_design/params points to identical data already present in this packet.',
            'last_action': self.state.get('last_action'),
            'protocol_diagnostics': self.state.get('protocol_diagnostics', []),
            'failures': self.failure_context(),
            'offline_diagnostics': self.offline_diagnostics(),
            'inspection_history': self.state.get('inspection_history', []),
            'unverified_requirements': [d.id for d in self.definition.drawing.dimensions if d.critical],
            'command_reference': list(self.reference),
            'available_commands': sorted(getattr(self.reference, 'catalog', {})),
            'retrieved_reference': self.reference.retrieved() if hasattr(self.reference, 'retrieved') else None,
            'remaining_decisions': max(0, remaining),
            'runtime_capacity': {'cumulative_commands': command_capacity.get(),
                'commands_used': sum(len(group.commands) for group in groups),
                'cumulative_cut_intents': 16,
                'cut_intents_used': sum(len(group.cut_intents) for group in groups),
                'inspection_call_reserve': (grant.inspection_reserve or 0) if grant else 0}}

    def retained_execution(self, decision_number):
        """Load a paid execution response bound to the current native prefix."""
        if type(decision_number) is not int or not 1 <= decision_number <= self.state['decisions']:
            raise CadError('Invalid retained CAD decision number')
        record = self.store._read(self.store.directory / f'decision-{decision_number}.json')
        packet = record.get('packet', {})
        chain = self.store.active()
        head = chain[-1].id if chain else None
        if (record.get('status') != 'returned'
                or packet.get('definition') != self.definition.model_dump(mode='json')
                or packet.get('engine_sha256') != self.store.engine_build
                or packet.get('execution_authorization') != self.packet()['execution_authorization']
                or packet.get('base_checkpoint') != head):
            raise CadError('Retained CAD response scope or checkpoint changed')
        decision = Decision.validate_python(parse_decision_response(record['response']))
        if not isinstance(decision, Execute) or decision.base_checkpoint != head or decision.group.base_checkpoint != head:
            raise CadError('Retained CAD replay requires an execution at its exact checkpoint')
        return record['response'], digest(record)

    async def run(self, session, *, replay_decision=None):
        # A fresh process opens the last complete accepted state. An interrupted
        # candidate never supplies topology to subsequent model decisions.
        await self.store.recover(session)
        replay = self.retained_execution(replay_decision) if replay_decision is not None else None
        if len(self.state['failures']) + self.state.get('inspection_repairs', 0) > self.repair_limit():
            raise CadError('CAD progressive repair allowance exhausted; accepted checkpoints retained')
        if self.state.get('completed'):
            session.cut_safety_reports = [report for checkpoint in self.store.active()
                for report in self.store.observations(checkpoint)['cut_safety']]
            return self.construction()
        while True:
            grant = self.continuation()
            ceiling = max(self.max_decisions, grant.decision_ceiling or 0) if grant else self.max_decisions
            if replay is None and self.state['decisions'] >= ceiling:
                self.state['recovery'] = {'kind': 'budget', 'checkpoint': self.packet()['base_checkpoint']}
                self.save()
                raise CadError('CAD progressive decision allowance exhausted; accepted checkpoints retained')
            if replay is None and grant and self.state['decisions'] >= grant.baseline_decisions + grant.additional_calls:
                self.state['recovery'] = {'kind': 'budget', 'checkpoint': self.packet()['base_checkpoint']}
                self.save()
                raise CadError('CAD continuation call allowance exhausted; accepted checkpoints retained')
            finalizing = bool(replay is None and grant and (grant.inspection_reserve or 0) > 0 and
                self.state['decisions'] >= grant.baseline_decisions + grant.additional_calls - grant.inspection_reserve)
            await self.supply_topology(session)
            packet = self.packet()
            if finalizing:
                packet['decision_phase'] = 'finalization'
                packet['allowed_operations'] = ['complete','blocked']
                packet['remaining_decisions'] = ceiling - self.state['decisions']
            content = json.dumps(packet, ensure_ascii=False, allow_nan=False, separators=(',',':'))
            if len(content.encode()) > 256_000:
                raise CadError('CAD progressive context exceeds its evidence envelope')
            self.state['decisions'] += 0 if replay is not None else 1
            self.save()
            trace = self.store.directory / f'decision-{self.state["decisions"]}.json'
            if replay is None:
                self.store._write(trace, {'status': 'reserved', 'packet': packet})
            await self.emit('cad_deciding', {'phase': 'deciding', 'decisions': self.state['decisions']})
            decide = self.finalize_decision if finalizing else self.decide
            if replay is not None:
                async def decide(*args, **kwargs):
                    return replay[0]
            raw = await decide(trace, packet, model=self.model or 'default', stream=False,
                max_tokens=8192, temperature=0.1, tool_schema=decision_tool_schema(Decision.json_schema()), messages=[{'role': 'system', 'content':
                'Construct the confirmed CAD definition progressively in SolidCraft 0.28.0, mm/deg. '
                'execution_authorization is supplied by the runtime after checking the recorded user decision. '
                'When its status is confirmed, approval has already been given for this exact definition and '
                'candidate. An original request to propose a contract before execution has been fulfilled; '
                'continue construction within that scope. Approval adds no missing dimensions or capabilities. '
                'last_action records completed runtime actions. retrieved_reference contains the native '
                'descriptions already returned; use them without requesting the same descriptions again. '
                'Keep earlier protocol corrections in protocol_diagnostics when preparing the next group. '
                'observations already includes the accepted checkpoint design and parameter graph. '
                'The runtime also supplies current native body_topology for every existing body. '
                'Use the supplied topology to select faces and edges directly. '
                'Use those results directly. pending_obligations records the last group\'s remaining work. '
                'construction_questions identifies those items as the model\'s own planning questions. '
                'Evaluate their necessity against the confirmed definition and actual tool requirements. '
                'A planning question can be revised or answered by a justified derivation or a qualified '
                'construction method; it does not create a new contractual measurement requirement. '
                'Preserve every confirmed requirement and runtime safety check. Distinguish measured '
                'values from deductions. Historical failures apply to their recorded attempted commands '
                'and base checkpoint; compare those inputs with the proposed strategy, including '
                'argument representations and native references. A changed input alone does not '
                'prove the new operation succeeds. '
                'Each new observation must state the specific question it can answer; consult '
                'observation_coverage first. feature_definition reads one existing feature\'s native '
                'definition and inputs, including referenced construction planes or axes. '
                'Resolved datum frames are not exposed by these tools; distinguish definitions and '
                'derived geometry from direct measurement. Solid STEP measurements cannot establish '
                'a construction axis orientation. Repeated reads at the same checkpoint are rejected. '
                'Each execution group supplies the full workflow inventory. accepted_workflow preserves '
                'the exact accepted declarations and provenance. Retain all its driving parameters '
                'unchanged when extending the workflow; omitting them is rejected before execution. '
                'Use the supplied native response schema. Wrap the response in decision. '
                'Encode each command.params as a JSON object string. The runtime decodes it before '
                'validating the command and its cut intent. '
                'Use the exact current base_checkpoint on every decision and execution group. '
                'Group commands with known inputs. End a group at sketch.finish and inspect the solver '
                'before using its profile. Request actual body_topology before selecting newly created '
                'faces or edges. Run each fillet/chamfer separately and name it directly with params.name; '
                'a separate timeline.rename is unnecessary. Reference native schemas and guides '
                'when needed. Use precise_geometry for STEP-backed measurements before further modeling '
                'when exact volume, bounds or local surface evidence is needed. Provide complete named '
                'parametric workflow intent, independent driving '
                'constraints, groups and body names; future features may be declared. The runtime imports '
                'workflow parameters. Every sketch is also a history feature: include its name in '
                'workflow.features and the owning group.features as well as group.sketches. '
                'Preserve all confirmed dimensions and hypotheses. Every removal '
                'needs a local-index cut_intent, explicit targets, feature/dimension provenance, and '
                'opening/stop planes checked against actual material. Native fillet/chamfer are finishing '
                'features. For curved pipe/flange union defects consider an outer union then a guarded '
                'continuous bore. Preserve observed corrections across failures. Tool discovery and '
                'observations perform no mutation. Revise an ancestor explicitly when needed; its suffix '
                'will be invalidated. Complete requests independent final inspection; all requirements '
                'remain unverified until measured. Report blocked when requirements or native capability '
                'prevent progress. runtime_capacity specifies the authorized cumulative command capacity; '
                'each execution group remains limited to 64 commands. Reserve inspection calls for final checks.'},
                {'role': 'user', 'content': [{'type': 'text', 'text': content}, *self.images]}])
            try:
                decision = (ClosingDecision if finalizing else Decision).validate_python(parse_decision_response(raw))
                expected = packet['base_checkpoint']
                if decision.base_checkpoint != expected:
                    raise ValueError('Decision references a stale checkpoint')
                self.state['feedback'] = None
                if isinstance(decision, Blocked):
                    self.state['recovery'] = {'kind': 'unknown', 'checkpoint': expected}
                    self.state['last_action'] = {'operation': 'blocked', 'status': 'blocked',
                        'checkpoint': expected, 'reason': decision.reason}
                    self.save()
                    raise CadError('CAD construction blocked: ' + decision.reason)
                if isinstance(decision, Reference):
                    if not hasattr(self.reference, 'describe'):
                        raise ValueError('Native CAD reference loader is unavailable')
                    if not decision.commands and not decision.skills:
                        raise ValueError('A reference request requires commands or skills')
                    retrieved = self.reference.retrieved()
                    known = {item['id'] for item in retrieved.get('command_reference', [])}
                    if (set(decision.commands) <= known
                            and set(decision.skills) <= set(retrieved.get('skill_reference', {}))):
                        raise ValueError('Requested native references are already in retrieved_reference; '
                                         'use the returned descriptions for the next decision')
                    await self.emit('cad_discovering', {'phase': 'discovering'})
                    await self.reference.describe(decision.commands, decision.skills)
                    self.state['last_action'] = {'operation': 'reference', 'status': 'completed',
                        'commands': list(decision.commands), 'skills': list(decision.skills),
                        'result_field': 'retrieved_reference'}
                elif isinstance(decision, Observe):
                    key = observation_key(decision, packet['current_design'])
                    if key in packet['observations']:
                        raise ValueError('Observation already available at this checkpoint in observations[' +
                                         key + ']; use the retained result for the next decision')
                    await self.emit('cad_observing', {'phase': 'observing'})
                    if decision.tool == 'feature_definition':
                        value = await session.tool('execute', {'command': 'timeline.inspect',
                                                              'params': {'feature': decision.feature}})
                        if value.get('name') != decision.feature:
                            raise CadError('CAD feature observation belongs to another feature')
                    elif decision.tool == 'body_topology':
                        names = {body['name'] for body in (packet['current_design'] or {}).get('bodies', [])}
                        if decision.body not in names:
                            raise ValueError('Topology observation requires an existing body')
                        value = await session.tool('body_topology', {'body': decision.body})
                        if value.get('body') != decision.body:
                            raise CadError('CAD topology observation belongs to another body')
                    elif decision.tool == 'parameter_graph':
                        value = await session.tool('execute', {'command': 'parameters.graph', 'params': {}})
                    elif decision.tool == 'precise_geometry':
                        if not (packet['current_design'] or {}).get('bodies'):
                            raise ValueError('Precise geometry requires a constructed solid')
                        revisions = [int(path.name.split('-')[1]) for path in self.store.root.glob('revision-*')
                                     if path.name.split('-')[1].isdigit()]
                        capture = await session.capture(self.store.root.name, self.store.root.name,
                                                        max([0, *revisions]) + 1)
                        value = {'measurement_scope': 'whole_document', 'requested_body': decision.body,
                                 'geometry': capture.geometry.model_dump(mode='json'),
                                 'bodies': capture.measurements['bodies']}
                    else:
                        value = await session.tool('inspect_design')
                    self.state['observations'][key] = {
                        'checkpoint': expected, 'question': decision.question, 'result': value}
                    self.state['last_action'] = {'operation': 'observe', 'tool': decision.tool,
                        'status': 'completed', 'checkpoint': expected, 'result_field': 'observations'}
                elif isinstance(decision, Revise):
                    if decision.checkpoint is not None:
                        await self.store.recover(session, decision.checkpoint)
                    self.store.rewind(decision.checkpoint)
                    if decision.checkpoint is None:
                        await session.close()
                        await session.__aenter__()
                        await self.store.recover(session)
                    self.state['observations'] = {}
                    self.state['last_action'] = {'operation': 'revise', 'status': 'completed',
                                                 'checkpoint': decision.checkpoint}
                    await self.emit('cad_revising', {'phase': 'revising', 'reason': decision.reason,
                                                   'checkpoint': decision.checkpoint})
                elif isinstance(decision, Complete):
                    construction = self.construction()
                    design = await session.tool('inspect_design')
                    graph = await session.tool('execute', {'command': 'parameters.graph', 'params': {}})
                    errors = construction.workflow.diagnostics(design, graph, self.definition.drawing)
                    if errors:
                        raise ValueError('Construction remains incomplete: ' + '; '.join(errors))
                    session.cut_safety_reports = [report for checkpoint in self.store.active()
                        for report in self.store.observations(checkpoint)['cut_safety']]
                    self.state['completed'] = True
                    self.state['recovery'] = {'kind': 'inspection', 'checkpoint': expected}
                    self.save()
                    return construction
                else:
                    group = decision.group
                    if group.base_checkpoint != expected:
                        raise ValueError('Execution group references a stale checkpoint')
                    if group.id in {g.id for g in self.groups()}:
                        raise ValueError('Execution group identity is already accepted; revise its ancestor explicitly')
                    prior_groups = self.groups()
                    if prior_groups:
                        parameters = {p.name: p for p in group.workflow.parameters}
                        missing = [p.name for p in prior_groups[-1].workflow.parameters if p.name not in parameters]
                        if missing:
                            raise ValueError('Missing accepted workflow parameters: ' + ', '.join(missing) +
                                '. Retain their exact declarations from accepted_workflow.parameters; '
                                'each group supplies the complete inventory.')
                        for parameter in prior_groups[-1].workflow.parameters:
                            candidate = parameters.get(parameter.name)
                            fields = ('expression', 'unit', 'source_dimension', 'dependencies')
                            if any(getattr(candidate, field) != getattr(parameter, field) for field in fields):
                                raise ValueError('Changing an accepted driving parameter requires ancestor revision: ' +
                                                 parameter.name)
                        sketches = {s['name'] for s in packet['current_design']['sketches']}
                        if any(c.command == 'sketch.edit' and c.params.get('sketch') in sketches for c in group.commands):
                            raise ValueError('Editing an accepted sketch requires revision before its construction')
                    errors = boundary_diagnostics(group)
                    if errors:
                        raise ValueError('; '.join(errors))
                    for command in group.commands:
                        if command.command in {'solid.fillet', 'solid.chamfer', 'solid.shell', 'solid.draft'}:
                            body = command.params.get('body')
                            observed = self.state['observations'].get('body_topology:' + str(body))
                            if not observed or observed['checkpoint'] != expected:
                                raise ValueError('Topology-dependent operation requires body_topology for its explicit body at this checkpoint')
                    count = sum(len(g.commands) for g in self.groups()) + len(group.commands)
                    from .cad_resources import command_capacity
                    if count > command_capacity.get():
                        raise ValueError('Cumulative CAD construction exceeds the runtime-authorized capacity')
                    if sum(len(g.cut_intents) for g in self.groups()) + len(group.cut_intents) > 16:
                        raise ValueError('Cumulative CAD construction exceeds 16 cut intents; group compatible profiles within the confirmed scope')
                    from .cad_cut_contracts import validate_cut_intents
                    from .cad_native_compat import native_input_diagnostics
                    native_errors = native_input_diagnostics(
                        [command.model_dump(exclude={'schema_version'}) for command in group.commands],
                        self.store.engine)
                    if native_errors:
                        raise ValueError('; '.join(native_errors))
                    validate_cut_intents(group.commands, group.cut_intents, self.definition.drawing)
                    fingerprint = group_fingerprint(group)
                    observation_digest = digest(self.state['observations'])
                    offline = self.offline_diagnostics()
                    if offline:
                        observation_digest = digest({'observations': self.state['observations'],
                                                     'offline_diagnostics': offline})
                    if any(f['fingerprint'] == fingerprint and f['observations'] == observation_digest
                           for f in self.state['failures']):
                        raise ValueError('An identical failed group requires new evidence or a changed strategy')
                    try:
                        await self.store.execute(session, group, validate=self.check_step, progress=self.progress)
                    except (CadCommandError, CadTimeoutError) as error:
                        self.state['recovery'] = {'kind': 'geometry', 'checkpoint': expected}
                        diagnostic = getattr(error, 'result', {'failed': {'error': str(error)}})
                        evidence = self.store.directory / f'model-failure-{len(self.state["failures"])}.json'
                        self.store._write(evidence, diagnostic)
                        attempted = self.store._read(self.store.attempt)
                        attempt_id = attempted.get('attempt', '')
                        if (attempted.get('state') != 'failed' or len(attempt_id) != 32
                                or any(c not in '0123456789abcdef' for c in attempt_id)):
                            raise CadError('CAD failed execution has no retained proposal') from error
                        self.state['failures'].append({'fingerprint': fingerprint,
                            'proposal_ref': f'execution-checkpoints/{attempt_id}/proposal.json',
                            'proposal_sha256': digest(group.model_dump(mode='json')),
                            'observations': observation_digest, 'group': group.id,
                            'evidence_ref': evidence.relative_to(self.store.root).as_posix(),
                            'diagnostic': {key: value for key, value in diagnostic.get('failed', {}).items()
                                           if key != 'actual_operand_geometry'}})
                        self.state['last_action'] = {'operation': 'execute', 'status': 'failed',
                            'group': group.id, 'evidence_ref': evidence.relative_to(self.store.root).as_posix()}
                        self.save()
                        if self.active_allowance and self.active_allowance.stop_on_new_error:
                            raise CadError('CAD native attempt rejected; retained diagnostics require inspection before another model call') from error
                        if len(self.state['failures']) + self.state.get('inspection_repairs', 0) > self.repair_limit():
                            raise CadError('CAD progressive repair allowance exhausted') from error
                        await session.close()
                        session.observations = []
                        session.cut_safety_reports = []
                        await session.__aenter__()
                        await self.store.recover(session)
                        self.state['feedback'] = str(error)
                        await self.emit('cad_repairing', {'phase': 'repairing', 'diagnostic': str(error)})
                    else:
                        self.state['observations'] = {}
                        self.state['last_action'] = {'operation': 'execute', 'status': 'accepted',
                            'group': group.id, 'checkpoint': self.store.active()[-1].id}
                        # Each accepted checkpoint retains its complete native
                        # trace. Keep the live transport's window local to the
                        # next group while the driver bounds total decisions.
                        session.observations = []
                        session.cut_safety_reports = []
            except ValueError as error:
                if replay is not None:
                    raise CadError('Retained CAD replay rejected: ' + str(error)) from error
                self.state['recovery'] = {'kind': 'response_validation',
                    'checkpoint': packet['base_checkpoint'], 'decision': self.state['decisions']}
                if packet['feedback'] == str(error)[:4000]:
                    raise CadError('Repeated invalid CAD decision: ' + str(error)[:2000]) from error
                self.state['feedback'] = str(error)[:4000]
                self.state['last_action'] = {'operation': 'proposal', 'status': 'rejected',
                    'checkpoint': packet['base_checkpoint'], 'diagnostic': str(error)[:2000]}
                history = self.state.setdefault('protocol_diagnostics', [])
                diagnostic = {'checkpoint': packet['base_checkpoint'], 'diagnostic': str(error)[:2000]}
                if diagnostic not in history:
                    history.append(diagnostic)
                    self.state['protocol_diagnostics'] = history[-16:]
                await self.emit('cad_proposal_rejected', {'phase': 'deciding', 'diagnostic': str(error)[:2000]})
                if self.active_allowance and self.active_allowance.stop_on_new_error:
                    self.save()
                    raise CadError('CAD proposal rejected; retained diagnostics require inspection before another model call') from error
            self.save()
            if replay is not None:
                if self.state.get('last_action', {}).get('status') != 'accepted':
                    raise CadError('Retained CAD replay did not produce an accepted checkpoint')
                self.state.setdefault('replayed_decisions', []).append({
                    'decision': replay_decision, 'record_sha256': replay[1],
                    'checkpoint': self.store.active()[-1].id})
                self.state['recovery'] = {'kind': 'interrupted', 'checkpoint': self.store.active()[-1].id}
                self.save()
                return self.construction()

    def request_repair(self, checks, context):
        """Return measured failures to the same step controller and checkpoint chain."""
        repairs = self.state.get('inspection_repairs', 0) + 1
        if repairs + len(self.state['failures']) > self.repair_limit():
            raise CadError('CAD progressive repair allowance exhausted')
        self.state.update(completed=False, inspection_repairs=repairs,
            feedback={'inspection_checks': [item.model_dump(mode='json') for item in checks],
                      'candidate_context': context})
        self.state.setdefault('inspection_history', []).append(self.state['feedback'])
        self.save()
