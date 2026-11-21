"""Qualify native rigid assembly persistence on a disposable enclosure fixture."""

import argparse
import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from bigbrain.cad_contracts import CadDelivery, CriterionObservation
from bigbrain.cad_store import CadStore
from bigbrain.solidcraft import CadError, SolidCraftSession

async def main(fixture_directory=None):
    with tempfile.TemporaryDirectory(prefix='cad-assembly-') as folder:
        store = CadStore(Path(folder))
        session_id = 'assembly-probe'
        document_id = store.create(session_id)
        root = store.directory(document_id)
        async with SolidCraftSession(root, timeout=30) as session:
            async def command(operation, **params):
                return await session.tool('execute', {'command': operation, 'params': params})

            async def component(name):
                await command('component.activate', component='root')
                return await command('component.create', name=name)

            def box(name, size, corner):
                return command('solid.box', length=size[0], width=size[1], height=size[2],
                               corner=corner, body_name=name)

            await command('parameters.import', text=json.dumps([
                {'name': 'lip_width', 'expression': '55.5 mm', 'unit': 'mm'},
                {'name': 'head_width', 'expression': '4 mm', 'unit': 'mm'},
            ]))
            base = await component('Enclosure')
            await box('Base', [60, 40, 2], [0, 0, 0])
            for name, size, corner in [
                ('Front', [60, 2, 12], [0, 0, 2]), ('Back', [60, 2, 12], [0, 38, 2]),
                ('Left', [2, 36, 12], [0, 2, 2]), ('Right', [2, 36, 12], [58, 2, 2]),
            ]:
                await box(name, size, corner)
            lid = await component('Lid')
            await box('Cover', [60, 40, 2], [0, 0, 14])
            await box('LocatingLip', ['lip_width', 35.5, 1], [2.25, 2.25, 13])
            fastener = await component('Fastener')
            await box('Head', ['head_width', 4, 2], [5, 5, 16])
            await command('component.activate', component='root')
            copies = [await command('occurrence.copy', component=fastener['component'], translate=offset)
                      for offset in ([46, 0, 0], [0, 26, 0], [46, 26, 0])]
            if any(item['component'] != fastener['component'] for item in copies):
                raise RuntimeError('Fastener occurrences must share their definition')
            for occurrence in [lid, fastener, *copies]:
                await command('joint.as_built', type='rigid', a=base['occurrence'], b=occurrence['occurrence'])
            path = root / 'assembly.sc'
            await session.tool('save', {'path': str(path)})
            await session.tool('open', {'path': str(path)})
            inventory = (await command('component.list'))['components']
            occurrences = [item for definition in inventory for item in definition['occurrences']]
            expected_offsets = ([0, 0, 0], [46, 0, 0], [0, 26, 0], [46, 26, 0])
            expected_placements = {item['occurrence']: offset for item, offset
                                   in zip([fastener, *copies], expected_offsets, strict=True)}
            placements = {item['id']: item['transform'][3][:3] for item in occurrences
                          if item['component'] == fastener['component']}
            if len(occurrences) != 6 or placements != expected_placements:
                raise RuntimeError('Reopened assembly did not preserve the six occurrence placements')
            original_joints = await command('joint.list')
            revisions = []
            for width in (4, 5):
                if width == 5:
                    await command('parameters.change', name='head_width', expression='5 mm')
                    edited = root / 'edited' / path.name
                    edited.parent.mkdir()
                    await session.tool('save', {'path': str(edited)})
                    await session.tool('open', {'path': str(edited)})
                if (await command('component.list'))['components'] != inventory:
                    raise RuntimeError('Editing the fastener changed the assembly inventory or placements')
                joints = await command('joint.list')
                clearance = await command('inspect.clearance', skip_within='occurrence', clearance=0.5)
                if (len(joints['joints']) != 5 or joints != original_joints
                        or any(joints[key] for key in ('conflicts', 'errors', 'floating'))):
                    raise RuntimeError('Reopened assembly has changed or unresolved joints')
                if clearance['overlaps'] or clearance['unchecked'] or clearance['truncated']:
                    raise RuntimeError('Assembly interference inspection did not qualify every pair')
                # Measure the locating lip against the four enclosure walls.
                fit = await command('inspect.clearance', bodies=['LocatingLip'],
                                    against=['Front', 'Back', 'Left', 'Right'], clearance=0.5)
                gaps = [pair['distance_mm'] for pair in fit['near']]
                if (len(gaps) != 4 or any(abs(gap - .25) > 1e-6 for gap in gaps)
                        or fit['overlaps'] or fit['unchecked'] or fit['truncated']):
                    raise RuntimeError(f'Expected a 0.25 mm locating gap at all four walls: {fit}')
                heads = [item for item in (await session.tool('measure'))['bodies']
                         if item['name'].startswith('Head')]
                if len(heads) != 4 or any(abs(item['volume_mm3'] - width * 8) > 1e-6 for item in heads):
                    raise RuntimeError(f'Expected four fastener heads of volume {width * 8} mm³')
                revisions.append({'width_mm': width, 'head_volumes_mm3': [item['volume_mm3'] for item in heads],
                                  'clearance': clearance, 'locating_gaps_mm': gaps})
            await command('parameters.change', name='lip_width', expression='56 mm')
            collision = await command('inspect.clearance', bodies=['LocatingLip'],
                                      against=['Right'], clearance=0.5)
            overlaps = collision['overlaps']
            if (len(overlaps) != 1 or abs(overlaps[0]['volume_mm3'] - 8.875) > 1e-6
                    or collision['unchecked'] or collision['truncated']):
                raise RuntimeError(f'Expected the enlarged lip to overlap the right wall: {collision}')
            # Keep invalid constraints on the disposable session and verify diagnostics.
            await session.tool('open', {'path': str(edited)})
            try:
                await command('joint.as_built', type='rigid', a=base['occurrence'], b='MissingOccurrence')
            except CadError as error:
                if 'MissingOccurrence' not in str(error):
                    raise
                missing_reference = str(error)
            else:
                raise RuntimeError('SolidCraft accepted a joint with a missing occurrence')
            if await command('joint.list') != original_joints:
                raise RuntimeError('Missing occurrence changed the assembly joints')
            conflicting = await command('joint.create', name='Conflicting lid placement', type='rigid',
                a={'occurrence': base['occurrence'], 'point': [0, 0, 0]},
                b={'occurrence': lid['occurrence'], 'point': [10, 0, 0]})
            if not conflicting['conflicts']:
                raise RuntimeError('SolidCraft did not report the conflicting lid placement')
            await command('joint.edit', joint='Conflicting lid placement', suppressed=True)
            if (await command('joint.list'))['conflicts']:
                raise RuntimeError('Suppressing the incompatible joint did not resolve the conflict')
            await session.tool('open', {'path': str(edited)})
            capture = await session.capture(document_id, document_id, 1)
            if capture.assembly is None or len(capture.assembly.occurrences) != 6:
                raise RuntimeError('BigBrain capture did not retain all assembly occurrences')
            by_id = {item.id: item for item in capture.assembly.occurrences}
            for occurrence_id, (x, y, z) in expected_placements.items():
                bounds = by_id[occurrence_id].world_bounds_mm
                expected = ((x + 5, y + 5, z + 16), (x + 10, y + 9, z + 18))
                if bounds is None or any(abs(actual - target) > 1e-6
                        for corner, reference in zip(bounds, expected, strict=True)
                        for actual, target in zip(corner, reference, strict=True)):
                    raise RuntimeError(f'Incorrect selection bounds for occurrence {occurrence_id}: {bounds}')
            source = capture.document.native.sha256
            evidence = root / 'revision-1' / 'assembly-qualification.json'
            evidence.write_text(json.dumps({
                'source_sha256': source, 'components': inventory,
                'joints': original_joints, 'fit': revisions[-1],
            }, allow_nan=False), encoding='utf-8')
            criteria = {
                'assembly-occurrences': ('Occurrences', 'Six occurrences with verified placements.'),
                'assembly-joints': ('Liaisons', 'Five rigid joints with no conflicts or floating occurrences.'),
                'assembly-fit': ('Ajustement', 'Four 0.25 mm locating gaps and zero interferences.'),
            }
            checks = tuple(CriterionObservation(criterion_id=identity, label=label,
                source_sha256=source, evidence_ref=evidence.relative_to(root).as_posix(),
                status='passed', diagnostic=diagnostic)
                for identity, (label, diagnostic) in criteria.items())
            delivery = CadDelivery(specification_id='enclosure-assembly-qualification',
                required_criteria=tuple(criteria), required_exports=('step', 'stl'),
                document=capture.document, geometry=capture.geometry, checks=checks)
            store.publish(session_id, capture, delivery=delivery, title='Enclosure assembly')
            reopened = CadStore(Path(folder)).view(document_id, session_id)
            if (reopened['assembly'] != capture.assembly.model_dump(mode='json')
                    or reopened['delivery_status'] != 'ready'
                    or len(reopened['checks']) != len(checks)):
                raise RuntimeError('Reopened revision did not preserve the assembly and its checks')
            if fixture_directory is not None:
                fixture = fixture_directory / document_id
                shutil.copytree(root, fixture)
                print(f'Atelier fixture: {fixture}', flush=True)
            print(json.dumps({'components': inventory, 'joints': original_joints, 'revisions': revisions, 'collision': collision,
                              'missing_reference': missing_reference, 'conflicts': conflicting['conflicts']}), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture-directory', type=Path, help='Retain a copy for the Atelier browser fixture.')
    asyncio.run(main(parser.parse_args().fixture_directory))
