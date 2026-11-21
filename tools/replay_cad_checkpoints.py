"""Rebuild a retained CAD checkpoint chain in a disposable native document."""

import argparse
import asyncio
import hashlib
import json
import re
import tempfile
import time
from pathlib import Path
from zipfile import ZipFile
from bigbrain.cad_execution import CadExecutionStore, ExecutionGroup, digest
from bigbrain.solidcraft import SolidCraftSession
from bigbrain.cad_sections import CadSection
from bigbrain.cad_step import inspect_step
from bigbrain.cad_step_sections import inspect_step_sections

CACHE_ENTRIES = {'cache/model.json', 'cache/thumbnail.json', 'cache/thumbnail.png'}
CUTTER_NAME = re.compile(rb"(?<=MANIFOLD_SOLID_BREP\(')CutSafetyTool_[0-9a-f]{12}(?=')")


def cut_serialization_matches(original_root, rebuilt_root, original, rebuilt):
    """Compare cut inputs after binding each file to its own recorded hash."""
    digest_fields = {'before_native_sha256', 'cutter_sha256'}
    ignored = digest_fields | {'evidence_ref'}
    if {k: v for k, v in original.items() if k not in ignored} != {
            k: v for k, v in rebuilt.items() if k not in ignored}:
        return False

    def verified(root, report, name, field):
        path = (root / report['evidence_ref']).parent / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Cut evidence path is outside its document')
        if hashlib.sha256(path.read_bytes()).hexdigest() != report[field]:
            raise ValueError(f'Cut evidence digest changed: {name}')
        return path

    if not all(digest_fields <= report.keys() for report in (original, rebuilt)):
        return False
    with (ZipFile(verified(original_root, original, 'before.sc', 'before_native_sha256')) as old,
          ZipFile(verified(rebuilt_root, rebuilt, 'before.sc', 'before_native_sha256')) as new):
        names = set(old.namelist()) - CACHE_ENTRIES
        if (len(old.namelist()) != len(set(old.namelist()))
                or len(new.namelist()) != len(set(new.namelist()))
                or 'document.json' not in names or names != set(new.namelist()) - CACHE_ENTRIES
                or any(old.read(name) != new.read(name) for name in names)):
            return False
    old_step = verified(original_root, original, 'cutter.step', 'cutter_sha256').read_bytes()
    new_step = verified(rebuilt_root, rebuilt, 'cutter.step', 'cutter_sha256').read_bytes()
    return CUTTER_NAME.sub(b'CutSafetyTool', old_step) == CUTTER_NAME.sub(b'CutSafetyTool', new_step)


async def replay_checkpoints(root, engine, reference_step, sections_path=None, *, require_identical_cut_bytes=False):
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
                    retained_cuts, rebuilt_cuts = expected['cut_safety'], observed['cut_safety']
                    if len(retained_cuts) != len(rebuilt_cuts):
                        differences.append(step)
                    else:
                        for old, new in zip(retained_cuts, rebuilt_cuts, strict=True):
                            comparable = {k: v for k, v in old.items() if k != 'evidence_ref'} == {
                                k: v for k, v in new.items() if k != 'evidence_ref'}
                            if comparable:
                                continue
                            if cut_serialization_matches(root, replay.root, old, new):
                                if require_identical_cut_bytes:
                                    differences.append(step)
                                print(f'Cut serialization differs at group {step}; native and STEP content matched',
                                      flush=True)
                            else:
                                differences.append(step)
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
    parser.add_argument('--require-identical-cut-bytes', action='store_true')
    args = parser.parse_args()
    if args.reference_sections is not None and args.reference_step is None:
        parser.error('--reference-sections requires --reference-step')
    asyncio.run(replay_checkpoints(args.document, args.engine, args.reference_step, args.reference_sections,
        require_identical_cut_bytes=args.require_identical_cut_bytes))
