"""Headless CAD worker with measured criteria and conversation-owned artifacts."""

import asyncio
import json
import time

from .base import BaseBrain
from ..cad_contracts import CadDelivery
from ..cad_planning import CadPlan, draft_cad_plan
from ..cad_store import CadStore
from ..solidcraft import CadError, SolidCraftSession, solidcraft_executable


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
    return await draft_cad_plan(provider, payload['user_request'], context=context, model=model, drawing=drawing)


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
                await progress('modeling', 'cad_modeling', previous)
                async with SolidCraftSession(root) as session:
                    if previous:
                        from ..cad_contracts import CadRevision
                        await session.reopen(CadRevision.model_validate(previous['document']).native)
                    await session.batch([item.model_dump(exclude={'schema_version'}) for item in plan.commands])
                    await progress('checking', 'cad_checking', previous)
                    # Incomplete captures remain available for diagnosis. Allocate
                    # a fresh folder after an interrupted capture.
                    revisions = [int(path.name.split('-')[1]) for path in root.glob('revision-*')
                                 if path.name.split('-')[1].isdigit()]
                    revision = max([base, *revisions]) + 1
                    capture = await session.capture(document_id, document_id, revision)
                    checks = tuple(item.observe(capture.geometry) for item in plan.criteria)
                    evidence = root / f'revision-{revision}'
                    (evidence / 'engine-observations.json').write_text(
                        json.dumps(session.observations, allow_nan=False), encoding='utf-8')
                    (evidence / 'criterion-observations.json').write_text(
                        json.dumps([item.model_dump(mode='json') for item in checks]), encoding='utf-8')
                    failed = [item.diagnostic for item in checks if item.status != 'passed']
                    if failed:
                        raise CadError('Critères CAO non satisfaits : ' + ' ; '.join(failed)[:800])
                    delivery = CadDelivery(specification_id=f'{spec.design_id}:{spec.revision}',
                        required_criteria=tuple(item.id for item in plan.criteria), required_exports=('step', 'stl'),
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
