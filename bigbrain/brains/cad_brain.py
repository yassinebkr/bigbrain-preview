"""Headless CAD worker with measured criteria and conversation-owned artifacts."""

import asyncio
import json
import time
import tempfile
import uuid
from pathlib import Path

from .base import BaseBrain
from ..cad_contracts import CadDelivery
from ..cad_planning import CadPlan, draft_cad_plan, draft_cad_repair
from ..cad_store import CadStore
from ..solidcraft import CadError, CadCommandError, SolidCraftSession, solidcraft_executable


async def prepare_cad_plan(provider, payload, *, model=None):
    """Inspect an edit target before proposing its exact bounded recipe."""
    solidcraft_executable()  # Missing native capability fails before inference.
    store = CadStore()
    document_id = payload.get('document_id')
    context = None
    drawing = None
    if payload.get('drawing') is not None:
        from ..cad_drawings import DrawingSpecification
        drawing = DrawingSpecification.model_validate(payload['drawing']).require_resolved()
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
    commands = {'solid.box', 'solid.cylinder', 'solid.extrude', 'solid.chamfer', 'solid.fillet',
                'sketch.create', 'sketch.line', 'sketch.arc.three_point', 'sketch.circle.center',
                'sketch.rectangle.two_point', 'sketch.rectangle.rounded', 'sketch.finish', 'parameters.change'}
    with tempfile.TemporaryDirectory(prefix='bigbrain-cad-catalog-') as scratch:
        async with SolidCraftSession(Path(scratch)) as session:
            catalog = await session.tool('list_commands')
            reference = [{'id': item['id'], 'params': item['params']}
                         for item in catalog if item['id'] in commands]
    return await draft_cad_plan(provider, payload['user_request'], context=context, model=model,
                                drawing=drawing, command_reference=reference)


class CadBrain(BaseBrain):
    """Execute the recipe recorded in the user's immutable contract revision."""

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
                or approval.get('plan_id') != payload.get('_plan_id')):
            raise CadError('CAD execution requires this run’s confirmed contract revision')
        recorded = spec.metadata.get('cad') or {}
        # Recipe, edit target and original revision derive from the stored
        # contract. A worker payload cannot expand the confirmed operation.
        plan = CadPlan.model_validate(recorded['plan'])
        session_id = payload.get('session_id')
        if not session_id or recorded.get('session_id') != session_id:
            raise CadError('CAD contract conversation scope mismatch')
        store = CadStore()
        document_id = recorded.get('document_id') or store.create(session_id)
        root = store.authorize(document_id, session_id)
        previous = None
        if recorded.get('document_id'):
            previous = store.view(document_id, session_id)
            if previous['document']['revision'] != recorded.get('base_revision'):
                raise CadError('CAD piece changed after contract confirmation')
        base = previous['document']['revision'] if previous else 0
        sequence, started = 0, time.monotonic()

        async def progress(status, stage, view=None, diagnostic=None):
            nonlocal sequence
            sequence += 1
            await self.send_progress({'stage': stage, 'cad': {
                'schema_version': '1.0', 'document_id': document_id, 'title': plan.title,
                'sequence': sequence, 'status': status, 'elapsed_seconds': time.monotonic() - started,
                'snapshot': view, 'diagnostic': diagnostic}})

        try:
            async with asyncio.timeout(120):
                for attempt in range(plan.max_repairs + 1):
                    await progress('modeling', 'cad_modeling' if attempt == 0 else 'cad_repairing', previous)
                    # Each repair starts from the approved original. Failed
                    # candidates remain separate captured evidence revisions.
                    async with SolidCraftSession(root) as session:
                        if previous:
                            from ..cad_contracts import CadRevision
                            await session.reopen(CadRevision.model_validate(previous['document']).native)
                        try:
                            await session.batch([item.model_dump(exclude={'schema_version'}) for item in plan.commands])
                        except CadCommandError as error:
                            diagnostic = {'attempt': attempt, 'engine_result': error.result,
                                          'observations': session.observations}
                            (root / f'command-failure-{uuid.uuid4().hex}.json').write_text(
                                json.dumps(diagnostic, allow_nan=False), encoding='utf-8')
                            if attempt == plan.max_repairs or self.llm_provider is None:
                                raise
                            # The next attempt opens a new isolated session from
                            # the approved original, regardless of batch rollback.
                            await session.close()
                            await progress('checking', 'cad_repair_diagnosis', previous, str(error))
                            plan = await draft_cad_repair(self.llm_provider, plan, (), model=self.model,
                                                         command_diagnostic=error.result.get('failed'))
                            continue
                        await progress('checking', 'cad_checking', previous)
                        revisions = [int(path.name.split('-')[1]) for path in root.glob('revision-*')
                                     if path.name.split('-')[1].isdigit()]
                        revision = max([base, *revisions]) + 1
                        capture = await session.capture(document_id, document_id, revision)
                        checks = tuple(item.observe(capture.geometry) for item in plan.criteria)
                        evidence = root / f'revision-{revision}'
                        if plan.sections:
                            from ..cad_sections import read_triangles, observe_section
                            if capture.geometry.body_count != 1:
                                raise CadError('Section verification requires one closed body')
                            artifact = next(item for item in capture.document.exports if item.format == 'stl')
                            if session._artifact(root / artifact.path, 'stl').sha256 != artifact.sha256:
                                raise CadError('CAD surface changed before section verification')
                            triangles = await asyncio.to_thread(read_triangles, root / artifact.path)
                            section_evidence = []
                            for section in plan.sections:
                                observation, actual = await asyncio.to_thread(observe_section,
                                    section, triangles, source_sha256=capture.document.native.sha256,
                                    evidence_ref=f'revision-{revision}/sections.json')
                                checks += (observation,)
                                section_evidence.append({'criterion': section.model_dump(mode='json'),
                                    'observed_intervals_mm': actual, 'surface_sha256': artifact.sha256})
                            (evidence / 'sections.json').write_text(json.dumps(section_evidence, allow_nan=False), encoding='utf-8')
                        (evidence / 'engine-observations.json').write_text(
                            json.dumps(session.observations, allow_nan=False), encoding='utf-8')
                        (evidence / 'criterion-observations.json').write_text(
                            json.dumps([item.model_dump(mode='json') for item in checks]), encoding='utf-8')
                    failed = [item for item in checks if item.status != 'passed']
                    if not failed:
                        break
                    if attempt == plan.max_repairs or any(item.status == 'inconclusive' for item in failed) or self.llm_provider is None:
                        raise CadError('Critères CAO non satisfaits : ' + ' ; '.join(item.diagnostic for item in failed)[:800])
                    await progress('checking', 'cad_repair_diagnosis', previous,
                                   'Correction de géométrie à partir des mesures, critères conservés.')
                    plan = await draft_cad_repair(self.llm_provider, plan, checks, model=self.model)
                delivery = CadDelivery(specification_id=f'{spec.design_id}:{spec.revision}',
                    required_criteria=tuple(item.id for item in (*plan.criteria, *plan.sections)), required_exports=('step', 'stl'),
                    document=capture.document, geometry=capture.geometry, checks=checks)
                view = store.publish(session_id, capture, delivery=delivery, base_revision=base, title=plan.title)
                await progress('ready', 'cad_ready', view)
                return {'success': True, 'result_kind': 'cad', 'runnable': False,
                    'delivery_status': 'ready', 'cad': view,
                    'message': f'Pièce créée et vérifiée : {plan.title}. L’aperçu, les dimensions et les exports sont disponibles dans l’Atelier.'}
        except asyncio.CancelledError:
            await progress('cancelled', 'cad_cancelled', previous, 'Travail CAO arrêté ; la révision précédente est conservée.')
            raise
        except Exception as error:
            diagnostic = str(error)[:1000] or type(error).__name__
            await progress('failed', 'cad_failed', previous, diagnostic)
            return {'success': False, 'result_kind': 'cad', 'delivery_status': 'incomplete',
                    'runnable': False, 'error': diagnostic}
