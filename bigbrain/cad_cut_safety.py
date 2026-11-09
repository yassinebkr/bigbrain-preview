"""Pre-mutation cut checks using native cutter geometry and independent intersections."""

import asyncio
import hashlib
import json
import math
from pathlib import Path
import shutil
import uuid

from .cad_cut_geometry import inspect_overruns


async def guarded_cut(session, command, intent, parameter_names=(), *, execute=True):
    from .solidcraft import CadCommandError, CadError, SolidCraftSession
    root = session.scratch / '.cut-safety' / uuid.uuid4().hex
    root.mkdir(parents=True)
    record = {'intent': intent.model_dump(mode='json'), 'command': command, 'status': 'checking',
              'executed': False, 'evidence_ref': (root / 'inspection.json').relative_to(session.scratch).as_posix()}
    attempted = False
    try:
        design = await session.tool('inspect_design', {'measure': False, 'sketches': False})
        names = {body['name'] for body in design['bodies']}
        if not set(intent.targets) <= names:
            raise ValueError('Cut target identity is unavailable in the candidate')
        limits = []
        evaluated = {}
        for boundary in intent.boundaries:
            point = []
            for coordinate in boundary.origin_mm:
                if isinstance(coordinate, str):
                    if coordinate not in evaluated:
                        try:
                            result = await session.tool('execute', {'command': 'expr.evaluate', 'params': {
                                'expression': coordinate, 'kind': 'length'}})
                        except CadError as error:
                            raise ValueError('Cut boundary expression requires declared native length parameters: ' + str(error)) from error
                        if not result.get('ok') or result.get('error') or not set(result.get('references', [])) <= set(parameter_names):
                            raise ValueError('Cut boundary expression requires declared native length parameters')
                        evaluated[coordinate] = result['value']
                    coordinate = evaluated[coordinate]
                if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)) or not math.isfinite(coordinate):
                    raise ValueError('Cut boundary coordinates must evaluate to finite native lengths')
                point.append(coordinate)
            limits.append({**boundary.model_dump(exclude={'schema_version'}), 'origin_mm': point})
        material = root / 'material.step'
        cutter = root / 'cutter.step'
        consumed = set(command['params'].get('tools', [])) if command['command'] == 'solid.combine' else set()
        if consumed & set(intent.targets) or not consumed <= names:
            raise ValueError('Cut tool/target identities overlap or are unavailable')
        record.update(engine_version=session.version, targets=list(intent.targets),
                      material_bodies=sorted(names - consumed), consumed_tools=sorted(consumed))
        await session.tool('export', {'path': str(material), 'format': 'step', 'bodies': sorted(names - consumed)})
        if consumed:
            await session.tool('export', {'path': str(cutter), 'format': 'step', 'bodies': sorted(consumed)})
        else:
            supported = {'solid.box', 'solid.cylinder', 'solid.sphere', 'solid.cone', 'solid.torus',
                         'solid.extrude', 'solid.revolve', 'solid.sweep', 'solid.loft', 'solid.pipe'}
            if command['command'] not in supported:
                raise ValueError('Cut safety requires an explicit solid cutter; use a scoped cylinder/profile cut')
            snapshot = root / 'before.sc'
            await session.tool('save', {'path': str(snapshot)})
            record['before_native_sha256'] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
            probe_root = root / 'probe'
            probe_root.mkdir()
            shutil.copyfile(snapshot, probe_root / 'input.sc')
            async with SolidCraftSession(probe_root, executable=session.executable, timeout=session.timeout) as probe:
                await probe.tool('open', {'path': str(probe_root / 'input.sc')})
                params = {key: value for key, value in command['params'].items()
                          if key not in {'targets', 'participants', 'operation', 'name', 'body_name'}}
                body = 'CutSafetyTool_' + uuid.uuid4().hex[:12]
                params.update(operation='new', body_name=body, name=body)
                await probe.batch([{'command': command['command'], 'params': params}])
                await probe.tool('export', {'path': str(probe_root / 'cutter.step'), 'format': 'step', 'bodies': [body]})
                shutil.copyfile(probe_root / 'cutter.step', cutter)
        record['geometry'] = await asyncio.to_thread(inspect_overruns, material, cutter, limits)
        record['material_sha256'] = hashlib.sha256(material.read_bytes()).hexdigest()
        record['cutter_sha256'] = hashlib.sha256(cutter.read_bytes()).hexdigest()
        record['status'] = 'passed'
        # Geometry generation above only changes the probe. Mutate the candidate
        # after all end-limit intersections have been accepted.
        if execute:
            if command['command'] == 'solid.cone':
                record['actual_operand_geometry'] = {
                    'source_sha256': record.get('before_native_sha256'),
                    'topology': [await session.tool('body_topology', {'body': name})
                                 for name in intent.targets]}
            attempted = True
            await session.batch([command])
        record['executed'] = execute
    except Exception as error:
        record.update(status='failed', diagnostic=str(error), executed=None if attempted else False)
        if hasattr(error, 'result') and record.get('actual_operand_geometry'):
            error.result['failed']['actual_operand_geometry'] = record['actual_operand_geometry']
        if isinstance(error, (ValueError, ImportError)):
            raise CadCommandError({'failed': {'stage': 'cut_safety', 'intent': intent.id, 'diagnostics': [str(error)]}}) from error
        raise
    finally:
        (root / 'inspection.json').write_text(json.dumps(record, indent=2, allow_nan=False))
    return record


async def revalidate_parameter_edit(session, previous_native_sha256, safety_path):
    """Replay retained cut construction with current parameters in a private session."""
    from .cad_cut_contracts import CutIntent
    from .solidcraft import CadError, SolidCraftSession
    source = json.loads(Path(safety_path).read_text())
    if source.get('source_sha256') != previous_native_sha256:
        raise CadError('Retained cut safety belongs to a different native revision')
    observed = await session.tool('inspect_design', {'measure': False, 'sketches': False})
    parameters = [{key: item[key] for key in ('name', 'expression', 'unit')}
                  for item in observed['params'] if not item.get('model')]
    commands, indices = [], {}
    for index, command in enumerate(source['construction_commands']):
        if command['command'].startswith('parameters.'):
            continue
        indices[index] = len(commands)
        commands.append(command)
    intents = [CutIntent.model_validate({**item, 'command_index': indices[item['command_index']]})
               for item in source['cut_intents']]
    root = session.scratch / '.cut-safety' / ('edit-' + uuid.uuid4().hex)
    root.mkdir(parents=True)
    async with SolidCraftSession(root, executable=session.executable, timeout=session.timeout) as probe:
        if parameters:
            await probe.batch([{'command': 'parameters.import', 'params': {'text': json.dumps(parameters)}}])
        await probe.construct(commands, cut_intents=intents, enforce_cut_safety=True)
        return {'previous_source_sha256': previous_native_sha256,
                'parameters': parameters, 'reports': probe.cut_safety_reports,
                'construction_commands': commands,
                'cut_intents': [item.model_dump(mode='json') for item in intents]}
