"""Qualify native rigid assembly persistence on a disposable enclosure fixture."""

import asyncio
import json
import tempfile
from pathlib import Path
from bigbrain.solidcraft import CadError, SolidCraftSession

async def main():
    with tempfile.TemporaryDirectory(prefix='cad-assembly-') as folder:
        root = Path(folder)
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
            original_joints = await command('joint.list')
            revisions = []
            for width in (4, 5):
                if width == 5:
                    await command('parameters.change', name='head_width', expression='5 mm')
                    edited = root / 'wider-heads.sc'
                    await session.tool('save', {'path': str(edited)})
                    await session.tool('open', {'path': str(edited)})
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
            print(json.dumps({'joints': original_joints, 'revisions': revisions, 'collision': collision,
                              'missing_reference': missing_reference, 'conflicts': conflicting['conflicts']}), flush=True)

if __name__ == '__main__':
    asyncio.run(main())
