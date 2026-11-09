"""Native pre-mutation safety checks for overrun cutters and protected material."""

import json

import pytest
from pydantic import ValidationError

from bigbrain.cad_cut_contracts import CutBoundary, CutIntent, validate_cut_intents
from bigbrain.cad_cut_safety import guarded_cut
from bigbrain.solidcraft import CadCommandError, CadError, SolidCraftSession, solidcraft_executable


def intent(*, blind=False, stop=10, target='Plate'):
    return CutIntent.model_validate({
        'id': 'bore', 'feature_id': 'bore', 'dimension_ids': ['bore_diameter'],
        'command_index': 0, 'targets': [target], 'kind': 'blind' if blind else 'through',
        'boundaries': [
            {'label': 'entry', 'origin_mm': [5, 5, 0], 'outward_normal': [0, 0, -1], 'role': 'opening'},
            {'label': 'end', 'origin_mm': [5, 5, stop], 'outward_normal': [0, 0, 1],
             'role': 'stop' if blind else 'opening'},
        ]})


def cutter(height=14):
    return {'command': 'solid.cylinder', 'params': {
        'radius': 2, 'height': height, 'base': [5, 5, -2],
        'operation': 'cut', 'targets': ['Plate'], 'name': 'Bore'}}


def box(name, corner, size):
    return {'command': 'solid.box', 'params': {
        'corner': corner, 'length': size[0], 'width': size[1], 'height': size[2],
        'body_name': name, 'operation': 'new'}}


def test_cut_intent_requires_limits_targets_and_provenance():
    with pytest.raises(ValueError, match='Every removal'):
        validate_cut_intents([cutter()], [])
    with pytest.raises(ValueError, match='exact explicit'):
        validate_cut_intents([cutter()], [intent(target='Other')])
    data = intent().model_dump()
    data['boundaries'] = data['boundaries'][:1]
    with pytest.raises(ValidationError, match='two opening'):
        CutIntent.model_validate(data)
    data = intent(blind=True).model_dump()
    data['kind'] = 'through'
    with pytest.raises(ValidationError):
        CutIntent.model_validate(data)
    with pytest.raises(ValidationError, match='unit outward'):
        CutBoundary(label='bad', origin_mm=(0, 0, 0), outward_normal=(0, 0, 2), role='opening')


@pytest.fixture
def engine():
    try:
        return solidcraft_executable()
    except CadError:
        pytest.skip('Installed SolidCraft required for native cutter checks')


def test_cut_feature_diagnostic_identifies_drawing_provenance():
    from types import SimpleNamespace
    drawing = SimpleNamespace(dimensions=[SimpleNamespace(id='bore_diameter',feature_id='passage')])
    with pytest.raises(ValueError, match="use one of.*passage.*command.params.name"):
        validate_cut_intents([cutter()], [intent()], drawing)
    corrected = intent().model_copy(update={'feature_id':'passage'})
    validate_cut_intents([cutter()], [corrected], drawing)


@pytest.mark.asyncio
async def test_safe_cut_executes_after_independent_checks(tmp_path, engine):
    async with SolidCraftSession(tmp_path, executable=engine) as session:
        await session.batch([box('Plate', [0, 0, 0], [10, 10, 10])])
        report = await guarded_cut(session, cutter(), intent())
        assert report['status'] == 'passed' and report['executed']
        assert all(item['material_intersection_mm3'] <= 1e-9 for item in report['geometry']['boundaries'])
        measured = await session.tool('measure')
        import math
        assert measured['total']['volume_mm3'] == pytest.approx(1000 - math.pi * 4 * 10, rel=1e-4)


@pytest.mark.asyncio
@pytest.mark.parametrize('obstacle', ['other_body', 'same_body_rib', 'thin_wall'])
@pytest.mark.parametrize('aligned', [False, True])
async def test_cut_overrun_preserves_obstacle_before_mutation(tmp_path, engine, obstacle, aligned):
    async with SolidCraftSession(tmp_path, executable=engine) as session:
        commands = [box('Plate', [0, 0, 0], [10, 10, 10])]
        if obstacle == 'same_body_rib':
            commands += [box('Side', [0, 0, 9], [1, 10, 4]),
                         box('Rib', [0, 4, 11], [10, 2, 1]),
                         {'command': 'solid.combine', 'params': {
                             'target': 'Plate', 'tools': ['Side', 'Rib'], 'operation': 'join'}}]
        else:
            commands += [box('Obstacle', [4, 4, 11], [2, 2, 0.01 if obstacle == 'thin_wall' else 2])]
        await session.batch(commands)
        before = await session.tool('inspect_design')
        data = intent().model_dump(mode='json')
        if aligned:
            for boundary in data['boundaries']:
                boundary['alignment_tolerance_mm'] = 0.05
                boundary['origin_mm'][2] -= 0.001
        with pytest.raises(CadCommandError, match='protected material'):
            await guarded_cut(session, cutter(), CutIntent.model_validate(data))
        after = await session.tool('inspect_design')
        # Saving a probe snapshot updates native file metadata. Every geometric,
        # solver, parameter, timeline and selection field must remain identical.
        metadata = {'dirty', 'path', 'name', 'revision'}
        assert {key: value for key, value in after.items() if key not in metadata} == {
            key: value for key, value in before.items() if key not in metadata}
        reports = list((tmp_path / '.cut-safety').glob('*/inspection.json'))
        assert reports and json.loads(reports[0].read_text())['executed'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('offset,passes', [(0.001, True), (0.1, False)])
async def test_measured_opening_alignment_is_bounded(tmp_path, engine, offset, passes):
    async with SolidCraftSession(tmp_path, executable=engine) as session:
        await session.batch([box('Plate', [0, 0, 0], [10, 10, 10])])
        data = intent().model_dump(mode='json')
        for boundary in data['boundaries']:
            boundary['alignment_tolerance_mm'] = 0.05
            boundary['origin_mm'][2] -= offset
        proposed = CutIntent.model_validate(data)
        if passes:
            report = await guarded_cut(session, cutter(), proposed)
            assert report['executed']
            assert all(row['alignment']['distance_mm'] == pytest.approx(offset)
                       for row in report['geometry']['boundaries'])
        else:
            with pytest.raises(CadCommandError, match='no measured planar opening'):
                await guarded_cut(session, cutter(), proposed)
            assert (await session.tool('measure'))['total']['volume_mm3'] == pytest.approx(1000)


@pytest.mark.asyncio
async def test_shorter_extension_clears_other_body(tmp_path, engine):
    async with SolidCraftSession(tmp_path, executable=engine) as session:
        await session.batch([box('Plate', [0, 0, 0], [10, 10, 10]),
                             box('Obstacle', [4, 4, 13], [2, 2, 2])])
        assert (await guarded_cut(session, cutter(), intent()))['executed']
        measured = await session.tool('inspect_design')
        assert next(body for body in measured['bodies'] if body['name'] == 'Obstacle')['volume_mm3'] == pytest.approx(8)


@pytest.mark.asyncio
async def test_blind_overrun_is_rejected(tmp_path, engine):
    async with SolidCraftSession(tmp_path, executable=engine) as session:
        await session.batch([box('Plate', [0, 0, 0], [10, 10, 10])])
        with pytest.raises(CadCommandError, match='blind stop'):
            await guarded_cut(session, cutter(height=9), intent(blind=True, stop=6))
        assert (await session.tool('measure'))['total']['volume_mm3'] == pytest.approx(1000)


@pytest.mark.asyncio
async def test_correct_blind_depth_preserves_floor(tmp_path, engine):
    async with SolidCraftSession(tmp_path, executable=engine) as session:
        await session.batch([box('Plate', [0, 0, 0], [10, 10, 10])])
        report = await guarded_cut(session, cutter(height=8), intent(blind=True, stop=6))
        assert report['executed']
        import math
        assert (await session.tool('measure'))['total']['volume_mm3'] == pytest.approx(1000 - math.pi * 4 * 6, rel=1e-4)


@pytest.mark.asyncio
async def test_unknown_native_length_reference_blocks_before_cut(tmp_path, engine):
    async with SolidCraftSession(tmp_path, executable=engine) as session:
        await session.batch([box('Plate', [0, 0, 0], [10, 10, 10])])
        data = intent().model_dump()
        data['boundaries'][0]['origin_mm'] = ['missing/2', 5, 0]
        with pytest.raises(CadCommandError, match='declared native length'):
            await guarded_cut(session, cutter(), CutIntent.model_validate(data))
        assert (await session.tool('measure'))['total']['volume_mm3'] == pytest.approx(1000)


@pytest.mark.asyncio
async def test_parameter_edit_requires_fresh_geometry_check(tmp_path, engine):
    async with SolidCraftSession(tmp_path, executable=engine) as session:
        await session.batch([
            {'command': 'parameters.change', 'params': {'name': 'gap', 'expression': '14 mm'}},
            box('Plate', [0, 0, 0], [10, 10, 10]), box('Obstacle', [4, 4, 'gap'], [2, 2, 2])])
        first = await guarded_cut(session, cutter(), intent(), execute=False)
        assert first['status'] == 'passed' and not first['executed']
        await session.tool('set_parameter', {'name': 'gap', 'value': '11 mm'})
        with pytest.raises(CadCommandError, match='protected material'):
            await guarded_cut(session, cutter(), intent())
        assert next(body for body in (await session.tool('inspect_design'))['bodies'] if body['name'] == 'Plate')['volume_mm3'] == pytest.approx(1000)


@pytest.mark.asyncio
async def test_unresolved_opening_blocks_cut(tmp_path, engine):
    async with SolidCraftSession(tmp_path, executable=engine) as session:
        await session.batch([box('Plate', [0, 0, 0], [10, 10, 10])])
        with pytest.raises(CadCommandError, match='outward material boundary'):
            await guarded_cut(session, cutter(), intent(stop=12))


@pytest.mark.asyncio
async def test_inconclusive_inspector_preserves_candidate(tmp_path, engine, monkeypatch):
    def inconclusive(*args):
        raise ValueError('Cut safety intersection is inconclusive')
    monkeypatch.setattr('bigbrain.cad_cut_safety.inspect_overruns', inconclusive)
    async with SolidCraftSession(tmp_path, executable=engine) as session:
        await session.batch([box('Plate', [0, 0, 0], [10, 10, 10])])
        with pytest.raises(CadCommandError, match='inconclusive'):
            await guarded_cut(session, cutter(), intent())
        assert (await session.tool('measure'))['total']['volume_mm3'] == pytest.approx(1000)


@pytest.mark.asyncio
async def test_worker_parameter_edit_keeps_last_safe_delivery(tmp_path, engine):
    from bigbrain.brains.cad_brain import CadBrain
    from bigbrain.bus.bus import MessageBus
    from bigbrain.cad_store import CadStore
    from bigbrain.verification.evidence import default_repository
    from tests.test_cad_integration import prepared, task
    commands = [
        {'command': 'parameters.change', 'params': {'name': 'gap', 'expression': '14 mm'}},
        box('Plate', [0, 0, 0], [10, 10, 10]), box('Obstacle', [4, 4, 'gap'], [2, 2, 2]), cutter()]
    guard = intent().model_copy(update={'command_index': 3})
    def recipe(steps, height, guards=()):
        return {'title': 'Guarded plate', 'commands': steps,
                'cut_intents': [item.model_dump(mode='json') for item in guards],
                'criteria': [{'id': 'bounds', 'label': 'Envelope', 'metric': 'dimensions_mm',
                              'expected': [10, 10, height]}]}
    bus = MessageBus(tmp_path / 'bus', auth=None)
    worker = CadBrain('cad_brain', bus)
    try:
        plan, spec, _ = await prepared(bus, recipe(commands, 16, [guard]))
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        first = await worker.handle_task(task(plan, confirmed))
        assert first['success'], first
        assert any(check['criterion_id'] == 'cut-safety' for check in first['cad']['checks'])
        document = first['cad']['document']['document_id']
        edit = [{'command': 'parameters.change', 'params': {'name': 'gap', 'expression': '11 mm'}}]
        plan, spec, _ = await prepared(bus, recipe(edit, 13), document_id=document, revision=1)
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        second = await worker.handle_task(task(plan, confirmed))
        assert second['success'] is False and second['delivery_status'] == 'incomplete'
        assert 'protected material' in second['error']
        retained = CadStore().view(document, 'session-cad')
        assert retained['document'] == first['cad']['document']
    finally:
        await bus.close()
