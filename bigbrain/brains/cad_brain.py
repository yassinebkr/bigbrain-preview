"""Headless CAD worker with measured criteria and conversation-owned artifacts."""

import asyncio
import json
import time
import tempfile
import uuid
from pathlib import Path

from .base import BaseBrain
from ..cad_contracts import CadDelivery, CriterionObservation
from ..cad_planning import CadPlan, draft_cad_plan, draft_cad_repair, refine_cad_sampling
from ..cad_store import CadStore
from ..solidcraft import CadError, CadCommandError, CadTimeoutError, SolidCraftSession, solidcraft_executable
from ..cad_stages import CadDefinition, CadConstruction, draft_construction, inspect_candidate, reproduced_defect_is_repairable


async def prepare_cad_plan(provider, payload, *, model=None, defer_construction=False, require_workflow=True):
    """Inspect an edit target before proposing its exact bounded recipe."""
    solidcraft_executable()  # Missing native capability fails before inference.
    store = CadStore()
    document_id = payload.get('document_id')
    context = None
    drawing = None
    if payload.get('drawing') is not None:
        from ..cad_drawings import DrawingSpecification
        drawing = DrawingSpecification.model_validate(payload['drawing']).require_resolved()
    images = []
    if drawing is not None and drawing.sources:
        from ..front.cad_context import drawing_image_blocks
        if not getattr(getattr(provider, 'entry', None), 'vision', False):
            raise CadError('CAD drawing planning requires a vision-capable model')
        images = drawing_image_blocks(drawing, payload.get('session_id'))
    if defer_construction and drawing is not None and not document_id:
        return CadDefinition(title=drawing.title, objective=payload['user_request'], drawing=drawing)
    if document_id:
        view = store.view(document_id, payload.get('session_id'))
        if view['document']['revision'] != payload.get('base_revision'):
            raise CadError('CAD revision changed; inspect the latest piece before planning')
        from ..cad_contracts import CadRevision
        document = CadRevision.model_validate(view['document'])
        async with SolidCraftSession(store.directory(document_id)) as session:
            await session.reopen(document.native)
            context = {'geometry': view['geometry'], 'design': await session.tool('inspect_design')}
    # Read the installed engine documentation for the available sketch and
    # feature operations before proposing their parameters.
    reference = await cad_command_reference()
    return await draft_cad_plan(provider, payload['user_request'], context=context, model=model,
                                drawing=drawing, command_reference=reference, images=images,
                                require_workflow=require_workflow)


async def cad_command_reference():
    from ..cad_tool_reference import CadCommandCatalog
    commands = {'solid.box', 'solid.cylinder', 'solid.extrude', 'solid.chamfer', 'solid.fillet',
                'sketch.create', 'sketch.line', 'sketch.arc.three_point', 'sketch.circle.center',
                'sketch.rectangle.two_point', 'sketch.rectangle.rounded', 'sketch.finish', 'parameters.change',
                'sketch.draw.dimensioned', 'sketch.dimension', 'timeline.rename', 'body.rename', 'parameters.rename'}
    with tempfile.TemporaryDirectory(prefix='bigbrain-cad-catalog-') as scratch:
        async with SolidCraftSession(Path(scratch)) as session:
            catalog = await session.tool('list_commands')
            reference = [{'id': item['id'], 'params': item['params']}
                         for item in catalog if item['id'] in commands or item['id'].startswith('sketch.constraint.')]
    async def load_native_reference(names, skills):
        # Keep discovery read-only and separate from the candidate's design state.
        with tempfile.TemporaryDirectory(prefix='bigbrain-cad-reference-') as scratch:
            async with SolidCraftSession(Path(scratch)) as session:
                descriptions = [await session.tool('describe_command', {'id': name}) for name in names]
                guides = {name: await session.tool('skill_reference', {'skill': name, 'file': 'SKILL.md'})
                          for name in skills}
        return {'command_reference': descriptions, 'skill_reference': guides}
    return CadCommandCatalog(reference, catalog, loader=load_native_reference)


class CadBrain(BaseBrain):
    """Construct and measure owned CAD against the confirmed contract revision."""

    def __init__(self, name, bus, workspace=None, *, llm_provider=None, model=None):
        super().__init__(name, bus, workspace)
        self.llm_provider, self.model = llm_provider, model

    async def handle_message(self, message):
        return None

    async def handle_task(self, message):
        payload = message.payload or {}
        if payload.get('type') != 'model_cad':
            raise CadError('CAD worker requires a model_cad task')
        from ..verification.evidence import default_repository
        reference = payload.get('contract_revision') or {}
        spec = default_repository().load_spec(reference.get('design_id', ''), reference.get('revision', 0))
        approval = spec.metadata.get('approval', {}) if spec else {}
        if (not spec or approval.get('decision') != 'approved'
                or approval.get('plan_id') != payload.get('_resume_approval_plan', payload.get('_plan_id'))):
            raise CadError('CAD execution requires this run’s confirmed contract revision')
        recorded = spec.metadata.get('cad') or {}
        # Recipe, edit target and original revision derive from the stored
        # contract. A worker payload cannot expand the confirmed operation.
        definition = CadDefinition.model_validate(recorded['definition']) if recorded.get('definition') else None
        plan = CadPlan.model_validate(recorded['plan']) if definition is None else None
        session_id = payload.get('session_id')
        if not session_id or recorded.get('session_id') != session_id:
            raise CadError('CAD contract conversation scope mismatch')
        if definition is not None and (recorded.get('document_id') or self.llm_provider is None):
            raise CadError('A confirmed new CAD definition requires its construction provider')
        store = CadStore()
        from ..cad_runs import CadRunCheckpoint
        checkpoint = CadRunCheckpoint(store, spec, session_id)
        retained = checkpoint.load() if definition else None
        document_id = recorded.get('document_id') or (retained['document_id'] if retained else store.create(session_id))
        if payload.get('_resume_document_id') and (not retained or payload['_resume_document_id'] != document_id):
            raise CadError('CAD continuation document identity changed')
        root = store.authorize(document_id, session_id)
        previous = None
        if recorded.get('document_id'):
            previous = store.view(document_id, session_id)
            if previous['document']['revision'] != recorded.get('base_revision'):
                raise CadError('CAD piece changed after contract confirmation')
        base = previous['document']['revision'] if previous else 0
        sequence, started = 0, time.monotonic()
        execution_state = None
        evidence_manifest = None
        presentation_context = {'session_id': session_id,
            **{target: payload[source] for target, source in (
                ('task_id', '_plan_id'), ('subtask_id', '_subtask_id')) if payload.get(source)}}

        async def progress(status, stage, view=None, diagnostic=None):
            nonlocal sequence, evidence_manifest
            sequence += 1
            from ..cad_live import retain_progress, working_checkpoint
            state = {'stage': stage, 'cad': {
                'schema_version': '1.0', 'document_id': document_id, 'title': plan.title if plan else definition.title,
                'sequence': sequence, 'status': status, 'elapsed_seconds': time.monotonic() - started,
                'snapshot': view, 'diagnostic': diagnostic, 'execution': execution_state,
                'working': working_checkpoint(store, document_id, session_id)}}
            retain_progress(store, document_id, session_id, presentation_context, state)
            from ..cad_evidence import begin_evidence, finish_evidence
            repository = default_repository()
            if evidence_manifest is None:
                evidence_manifest = begin_evidence(repository, spec, presentation_context, document_id)
            if status in {'ready', 'failed', 'cancelled'}:
                evidence_manifest = finish_evidence(repository, evidence_manifest, state)
                await self.send_event('verification.run_recorded', {
                    'run_id': evidence_manifest.run_id, 'verdict': evidence_manifest.verdict,
                    'stages': [{'name': item.name, 'status': item.status} for item in evidence_manifest.stages]})
            await self.send_progress(state)

        execution_lock = root / '.cad-execution'
        try:
            driver = None
            progressive = bool(definition and (not retained or retained['kind'] == 'progressive'
                or (root / 'execution-checkpoints/head.json').exists()))
            execution_lock.mkdir()
        except FileExistsError as error:
            raise CadError('CAD execution is active or requires interrupted-state inspection') from error
        try:
            from ..cad_resources import authorized_capacity, command_capacity, inference_phase
            capacity_token = command_capacity.set(authorized_capacity(root, checkpoint.digest, definition) if definition else 64)
            phase_token = inference_phase.set('construction')
        except BaseException:
            execution_lock.rmdir()
            raise
        try:
            history = []
            for path in sorted(root.glob('command-failure-*.json'), key=lambda item: item.stat().st_mtime)[-8:]:
                if path.stat().st_size > 2_000_000:
                    continue
                failure = json.loads(path.read_text())['engine_result']['failed']
                compact = {key: value for key, value in failure.items() if key != 'actual_operand_geometry'}
                history.append({'evidence_ref': path.name, 'observed_failure': compact})
            async with asyncio.timeout(definition.execution_seconds if definition else 120):
                if definition is not None:
                    from ..front.cad_context import drawing_image_blocks
                    images = drawing_image_blocks(definition.drawing, session_id)
                    reference = await cad_command_reference()
                    if progressive:
                        from ..cad_execution import CadExecutionStore, digest
                        from ..cad_controller import CadConstructionDriver
                        async def step_progress(stage, detail):
                            nonlocal execution_state
                            chain = driver.store.active()
                            execution_state = {
                                'phase': detail.get('phase', 'checkpoint' if stage == 'cad_group_checkpoint' else 'executing'),
                                'current_step': (None if stage == 'cad_revising' else
                                    detail.get('purpose', (execution_state or {}).get('current_step'))),
                                'accepted_steps': len(chain), 'checkpoint': chain[-1].id if chain else None,
                                'decisions': driver.state['decisions']}
                            await progress('modeling', stage, previous, detail.get('diagnostic'))
                        driver = CadConstructionDriver(self.llm_provider, definition, reference, images,
                            CadExecutionStore(root, checkpoint.digest), model=self.model, progress=step_progress,
                            authorization={'status': 'confirmed', 'contract_sha256': checkpoint.digest,
                                'definition_sha256': digest(definition.model_dump(mode='json')),
                                'design_id': spec.design_id, 'revision': spec.revision,
                                'approval_plan_id': approval['plan_id'], 'document_id': document_id})
                        checkpoint.save(document_id, definition, kind='progressive')
                        await progress('modeling', 'cad_construction_planning')
                    elif retained:
                        model = CadConstruction if retained['kind'] == 'construction' else CadPlan
                        plan = model.model_validate(retained['recipe'])
                        if isinstance(plan, CadPlan) and plan.drawing != definition.drawing:
                            raise CadError('CAD continuation definition changed')
                        await progress('modeling', 'cad_checkpoint_restored')
                    else:
                        await progress('modeling', 'cad_construction_planning')
                        plan = await draft_construction(self.llm_provider, definition, reference, images, model=self.model)
                        checkpoint.save(document_id, plan, kind='construction')
                for attempt in range((definition.max_repairs if progressive else plan.max_repairs) + 1):
                    inference_phase.set('construction')
                    await progress('modeling', 'cad_modeling' if attempt == 0 else 'cad_repairing', previous)
                    # Progressive repairs recover their accepted prefix. Legacy
                    # edits reopen the retained revision; failed evidence stays separate.
                    async with SolidCraftSession(root, timeout=120) as session:
                        if previous:
                            from ..cad_contracts import CadRevision
                            previous_document = CadRevision.model_validate(previous['document'])
                            if previous_document.engine_sha256 != session.engine_sha256:
                                raise CadError('CAD retained revision requires its original executable fingerprint; '
                                               'preserve it and start a new candidate')
                            await session.reopen(previous_document.native)
                        try:
                            if progressive:
                                plan = await driver.run(session)
                                checkpoint.save(document_id, plan, kind='construction')
                            else:
                                if plan.workflow and plan.workflow.parameters:
                                    await session.batch([plan.workflow.parameter_command()])
                                await session.construct(
                                    [item.model_dump(exclude={'schema_version'}) for item in plan.commands], plan.workflow,
                                    cut_intents=plan.cut_intents, enforce_cut_safety=True)
                            retained_cut_safety = None
                            if previous:
                                old_revision = previous['document']['revision']
                                old_safety = root / f'revision-{old_revision}' / 'cut-safety.json'
                                if old_safety.exists():
                                    from ..cad_cut_safety import revalidate_parameter_edit
                                    retained_cut_safety = await revalidate_parameter_edit(
                                        session, previous['document']['native']['sha256'], old_safety)
                            if plan.workflow:
                                design = await session.tool('inspect_design')
                                graph = await session.tool('execute', {'command': 'parameters.graph', 'params': {}})
                                issues = plan.workflow.diagnostics(design, graph,
                                    definition.drawing if isinstance(plan, CadConstruction) else plan.drawing)
                                if issues:
                                    raise CadCommandError({'failed': {'stage': 'design_quality', 'diagnostics': issues}})
                                old_native = root / previous['document']['native']['path'] if previous else None
                                await plan.workflow.arrange(session, design, existing_native=old_native)
                        except (CadCommandError, CadTimeoutError) as error:
                            diagnostic = {'attempt': attempt, 'engine_result': error.result,
                                          'observations': session.observations}
                            failure_path = root / f'command-failure-{uuid.uuid4().hex}.json'
                            failure_path.write_text(json.dumps(diagnostic, allow_nan=False), encoding='utf-8')
                            history.append({'evidence_ref': failure_path.name, 'observed_failure': {
                                key: value for key, value in error.result.get('failed', {}).items()
                                if key != 'actual_operand_geometry'}})
                            if progressive or attempt == plan.max_repairs or self.llm_provider is None:
                                raise
                            # The next attempt opens a new isolated session from
                            # the approved original, regardless of batch rollback.
                            await session.close()
                            await progress('checking', 'cad_repair_diagnosis', previous, str(error))
                            if isinstance(plan, CadConstruction):
                                plan = await draft_construction(self.llm_provider, definition, reference, images,
                                    model=self.model, previous=plan, diagnostic=error.result.get('failed'),
                                    diagnostic_history=history[-8:])
                                checkpoint.save(document_id, plan, kind='construction')
                            else:
                                plan = await draft_cad_repair(self.llm_provider, plan, (), model=self.model,
                                                             command_diagnostic=error.result.get('failed'))
                            continue
                        await progress('checking', 'cad_checking', previous)
                        revisions = [int(path.name.split('-')[1]) for path in root.glob('revision-*')
                                     if path.name.split('-')[1].isdigit()]
                        revision = max([base, *revisions]) + 1
                        capture = await session.capture(document_id, document_id, revision)
                        quality = None
                        if plan.workflow:
                            design = await session.tool('inspect_design')
                            issues = plan.workflow.saved_diagnostics(root / capture.document.native.path, design)
                            quality = CriterionObservation(criterion_id='design-quality', label='Paramètres, esquisses et historique',
                                source_sha256=capture.document.native.sha256,
                                evidence_ref=f'revision-{revision}/design-quality.json',
                                status='failed' if issues else 'passed',
                                diagnostic=' ; '.join(issues)[:2000] if issues else 'Native parameters, solver state, named history and saved groups verified.')
                            (root / f'revision-{revision}' / 'design-quality.json').write_text(json.dumps({
                                'source_sha256': capture.document.native.sha256,
                                'workflow': plan.workflow.model_dump(mode='json'), 'design': design, 'parameter_graph': graph,
                                'diagnostics': issues}, allow_nan=False), encoding='utf-8')
                        if isinstance(plan, CadConstruction):
                            inference_phase.set('inspection')
                            # Inspection uses the captured geometry. Its targets
                            # still derive from the confirmed definition.
                            await progress('checking', 'cad_inspection_planning')
                            evidence = root / f'revision-{revision}'
                            topology = capture.measurements['bodies']
                            observations = {'source_sha256': capture.document.native.sha256,
                                'geometry': capture.geometry.model_dump(mode='json'), 'topology': topology}
                            (evidence / 'inspection-input.json').write_text(
                                json.dumps(observations, allow_nan=False), encoding='utf-8')
                            plan = await inspect_candidate(self.llm_provider, definition, plan, observations,
                                model=self.model, stop_on_error=bool(progressive and driver.active_allowance
                                    and driver.active_allowance.stop_on_new_error))
                            checkpoint.save(document_id, plan, kind='inspection')
                            (evidence / 'inspection-plan.json').write_text(plan.model_dump_json(), encoding='utf-8')
                        checks = tuple(item.observe(capture.geometry) for item in plan.criteria)
                        cut_safety = session.cut_safety_reports
                        if cut_safety or retained_cut_safety:
                            safety = {'source_sha256': capture.document.native.sha256,
                                'construction_commands': [item.model_dump(exclude={'schema_version'}) for item in plan.commands],
                                'cut_intents': [item.model_dump(mode='json') for item in plan.cut_intents],
                                'reports': cut_safety, 'retained_validation': retained_cut_safety}
                            if retained_cut_safety:
                                prefix = retained_cut_safety['construction_commands']
                                safety['construction_commands'] = prefix + safety['construction_commands']
                                safety['cut_intents'] = retained_cut_safety['cut_intents'] + [
                                    {**item, 'command_index': item['command_index'] + len(prefix)}
                                    for item in safety['cut_intents']]
                            (root / f'revision-{revision}' / 'cut-safety.json').write_text(
                                json.dumps(safety, allow_nan=False), encoding='utf-8')
                            checks += (CriterionObservation(criterion_id='cut-safety', label='Préservation autour des découpes',
                                source_sha256=capture.document.native.sha256, evidence_ref=f'revision-{revision}/cut-safety.json',
                                status='passed', diagnostic='Dépassements des outils vérifiés sur la matière et les paramètres de cette révision.'),)
                        if quality is not None:
                            checks += (quality,)
                        evidence = root / f'revision-{revision}'
                        measured_sections, measured_cylinders = {}, {}
                        if plan.cylinders or plan.vertices:
                            topology_evidence = {}
                            for body in dict.fromkeys(item.body for item in (*plan.cylinders, *plan.vertices)):
                                topology_evidence[body] = capture.measurements['bodies'][body]
                            (evidence / 'topology.json').write_text(json.dumps({
                                'source_sha256': capture.document.native.sha256,
                                'step_sha256': capture.measurements['step_sha256'],
                                'method': capture.measurements['method'],
                                'capabilities': capture.measurements['capabilities'],
                                'bodies': topology_evidence}, allow_nan=False), encoding='utf-8')
                            measured_cylinders = {item.id: item.observe(topology_evidence[item.body],
                                source_sha256=capture.document.native.sha256,
                                evidence_ref=f'revision-{revision}/topology.json') for item in (*plan.cylinders, *plan.vertices)}
                            checks += tuple(measured_cylinders.values())
                        if plan.sections:
                            from ..cad_sections import read_triangles, observe_section
                            if capture.geometry.body_count != 1:
                                raise CadError('Section verification requires one closed body')
                            artifact = next(item for item in capture.document.exports if item.format == 'stl')
                            if session._artifact(root / artifact.path, 'stl').sha256 != artifact.sha256:
                                raise CadError('CAD surface changed before section verification')
                            triangles = await asyncio.to_thread(read_triangles, root / artifact.path)
                            sampling_attempts = []
                            for sampling_attempt in range(2):
                                section_evidence, section_checks = [], []
                                for section in plan.sections:
                                    observation, actual = await asyncio.to_thread(observe_section,
                                        section, triangles, source_sha256=capture.document.native.sha256,
                                        evidence_ref=f'revision-{revision}/sections.json')
                                    section_checks.append(observation)
                                    measured_sections[section.id] = actual
                                    section_evidence.append({'criterion': section.model_dump(mode='json'),
                                        'observed_intervals_mm': actual, 'surface_sha256': artifact.sha256})
                                sampling_attempts.append({'sections': section_evidence,
                                    'observations': [item.model_dump(mode='json') for item in section_checks]})
                                (evidence / 'sampling-attempts.json').write_text(
                                    json.dumps(sampling_attempts, allow_nan=False), encoding='utf-8')
                                if (sampling_attempt or self.llm_provider is None or
                                        not any(item.status == 'inconclusive' for item in section_checks)):
                                    break
                                await progress('checking', 'cad_sampling_diagnosis', previous,
                                    'Ajustement local des sondages sur une frontière, cotes et tolérances conservées.')
                                plan = await refine_cad_sampling(self.llm_provider, plan, section_checks, model=self.model)
                            checks += tuple(section_checks)
                            (evidence / 'sections.json').write_text(json.dumps(section_evidence, allow_nan=False), encoding='utf-8')
                        if plan.measurements:
                            checks += tuple(item.observe(plan, capture.geometry, measured_sections,
                                measured_cylinders, evidence_ref=f'revision-{revision}/requirements.json')
                                for item in plan.measurements)
                            (evidence / 'requirements.json').write_text(json.dumps({
                                'drawing': plan.drawing.model_dump(mode='json'),
                                'methods': [item.model_dump(mode='json') for item in plan.measurements],
                                'source_sha256': capture.document.native.sha256,
                                'observations': [item.model_dump(mode='json') for item in checks
                                    if item.criterion_id in {method.id for method in plan.measurements}]},
                                allow_nan=False), encoding='utf-8')
                        (evidence / 'engine-observations.json').write_text(
                            json.dumps(session.observations, allow_nan=False), encoding='utf-8')
                        (evidence / 'criterion-observations.json').write_text(
                            json.dumps([item.model_dump(mode='json') for item in checks]), encoding='utf-8')
                    failed = [item for item in checks if item.status != 'passed']
                    if not failed:
                        break
                    if attempt == plan.max_repairs or not reproduced_defect_is_repairable(plan, checks) or self.llm_provider is None:
                        raise CadError('Critères CAO non satisfaits : ' + ' ; '.join(item.diagnostic for item in failed)[:800])
                    await progress('checking', 'cad_repair_diagnosis', previous,
                                   'Correction de géométrie à partir des mesures, critères conservés.')
                    candidate_context = {'source_sha256': capture.document.native.sha256,
                            'geometry': capture.geometry.model_dump(mode='json'),
                            'native_design': design if plan.workflow else None,
                            'topology': topology_evidence if plan.cylinders or plan.vertices else {},
                            'sections': measured_sections}
                    if progressive:
                        driver.request_repair(checks, candidate_context)
                        checkpoint.save(document_id, definition, kind='progressive')
                    else:
                        plan = await draft_cad_repair(self.llm_provider, plan, checks, model=self.model,
                            candidate_context=candidate_context)
                    if definition and not progressive:
                        checkpoint.save(document_id, plan, kind='inspection')
                delivery = CadDelivery(specification_id=f'{spec.design_id}:{spec.revision}',
                    required_criteria=tuple(item.id for item in (*plan.criteria, *plan.sections, *plan.cylinders, *plan.vertices, *plan.measurements))
                                      + (('design-quality',) if plan.workflow else ())
                                      + (('cut-safety',) if any(item.criterion_id == 'cut-safety' for item in checks) else ()), required_exports=('step', 'stl'),
                    document=capture.document, geometry=capture.geometry, checks=checks)
                view = store.publish(session_id, capture, delivery=delivery, base_revision=base, title=plan.title)
                await progress('ready', 'cad_ready', view)
                return {'success': True, 'result_kind': 'cad', 'runnable': False,
                    'delivery_status': 'ready', 'cad': view,
                    'message': f'Pièce créée et vérifiée : {plan.title}. L’aperçu, les dimensions et les exports sont disponibles dans l’Atelier.'}
        except asyncio.CancelledError:
            if driver is not None:
                chain = driver.store.active()
                driver.state['recovery'] = {'kind': 'inspection' if driver.state.get('completed') else 'interrupted',
                    'checkpoint': chain[-1].id if chain else None}
                driver.save()
            await progress('cancelled', 'cad_cancelled', previous, 'Travail CAO arrêté ; la révision précédente est conservée.')
            raise
        except Exception as error:
            if driver is not None and driver.state.get('completed'):
                chain = driver.store.active()
                driver.state['recovery'] = {'kind': 'inspection', 'checkpoint': chain[-1].id if chain else None}
                driver.save()
            diagnostic = str(error)[:1000] or type(error).__name__
            await progress('failed', 'cad_failed', previous, diagnostic)
            return {'success': False, 'result_kind': 'cad', 'delivery_status': 'incomplete',
                    'runnable': False, 'error': diagnostic}
        finally:
            command_capacity.reset(capacity_token)
            inference_phase.reset(phase_token)
            execution_lock.rmdir()
