"""Rebuild a retained CAD checkpoint chain in a disposable native document."""

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path
from bigbrain.cad_execution import CadExecutionStore, ExecutionGroup, digest
from bigbrain.solidcraft import SolidCraftSession
from bigbrain.cad_sections import CadSection
from bigbrain.cad_step import inspect_step
from bigbrain.cad_step_sections import inspect_step_sections

async def replay_checkpoints(root, engine, reference_step, sections_path=None):
    head = json.loads((root / 'execution-checkpoints/head.json').read_text())
    source = CadExecutionStore(root, head['contract_sha256'], head['engine_version'])
    with tempfile.TemporaryDirectory(prefix='cad-command-replay-') as directory:
        replay = CadExecutionStore(Path(directory), source.contract, source.engine)
        parent = None
        differences = []
        async with SolidCraftSession(replay.root, executable=engine, timeout=60) as session:
            for step, record in enumerate(source.active(), 1):
                raw = source._read(source.directory / record.id / 'proposal.json')
                if digest(raw) != record.proposal_sha256 or raw['base_checkpoint'] != record.parent:
                    raise ValueError(f'CAD proposal identity changed at step {step}')
                proposal = ExecutionGroup.model_validate({**raw, 'base_checkpoint': parent})
                expected = source.observations(record)

                async def validate(_proposal, observed):
                    observed = json.loads(json.dumps(observed))
                    for values in (expected, observed):
                        # Every replay writes its cut evidence into a fresh directory.
                        for report in values['cut_safety']:
                            report.pop('evidence_ref', None)
                    if observed["cut_safety"] != expected.get("cut_safety"):
                        differences.append(step)
                        print(f'Cut evidence differs at group {step}', flush=True)
                    return [f"{key} differs at step {step}" for key in sorted(observed.keys() - {"cut_safety"})
                            if observed[key] != expected.get(key)]

                # The controller scopes evidence to the next command group.
                session.observations = []
                session.cut_safety_reports = []
                start = time.monotonic()
                rebuilt = await replay.execute(session, proposal, validate=validate)
                parent = rebuilt.id
                print(step, round(time.monotonic() - start, 2), flush=True)

            if reference_step is not None:
                bodies = (await session.tool('measure'))['bodies']
                export = replay.root / 'rebuilt.step'
                await session.tool('export', {'path': str(export), 'format': 'step'})
                observed = inspect_step(export, bodies)
                baseline = inspect_step(reference_step, bodies)
                if observed != baseline:
                    raise ValueError('Reconstructed STEP metrology differs from the reference')
                print(f'STEP metrology matched at {observed["volume_mm3"]:.9f} mm³', flush=True)
                if sections_path is not None:
                    retained = json.loads(sections_path.read_text(encoding='utf-8'))
                    probes = [CadSection.model_validate(item['criterion']) for item in retained]
                    expected = inspect_step_sections(reference_step, probes)
                    observed = inspect_step_sections(export, probes)
                    if observed != expected or any(item.get('error') for item in observed.values()):
                        raise ValueError('Reconstructed STEP section probes differ or are inconclusive')
                    print(f'{len(probes)} STEP section probes matched', flush=True)
        if differences:
            raise ValueError(f"Cut evidence differs at groups {differences}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document', type=Path)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--reference-step', type=Path)
    parser.add_argument('--reference-sections', type=Path)
    args = parser.parse_args()
    if args.reference_sections is not None and args.reference_step is None:
        parser.error('--reference-sections requires --reference-step')
    asyncio.run(replay_checkpoints(args.document, args.engine, args.reference_step, args.reference_sections))
