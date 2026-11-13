"""Durable intermediate CAD states and conservative chronological recovery."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import uuid
from typing import Annotated

from pydantic import Field

from .cad_contracts import CadArtifact, Contract, Hash, Identity
from .cad_planning import CadCommand
from .cad_cut_contracts import CutIntent, validate_cut_intents
from .cad_workflow import CadWorkflow
from .solidcraft import CadCommandError, CadError


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class ExecutionGroup(Contract):
    """Commands bound to an observed native state and confirmed requirements."""

    id: Identity
    purpose: str = Field(min_length=3, max_length=500)
    base_checkpoint: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    commands: tuple[CadCommand, ...] = Field(min_length=1, max_length=64)
    cut_intents: tuple[CutIntent, ...] = Field(default=(), max_length=16)
    workflow: CadWorkflow
    # Obligations describe remaining evidence; native identities keep their
    # separate short-name limit. Bound descriptions in decision packets.
    unresolved_obligations: tuple[Annotated[str, Field(min_length=1, max_length=1000)], ...] = Field(default=(), max_length=64)


class ExecutionCheckpoint(Contract):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')
    parent: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    contract_sha256: Hash
    engine_version: Identity
    engine_sha256: Hash
    proposal_sha256: Hash
    native: CadArtifact
    mesh: CadArtifact | None = None
    evidence_ref: str
    evidence_sha256: Hash


def design_identity(design):
    """Bind recovery to native object identities, parameters and solver state."""
    required = ('params', 'timeline', 'sketches', 'bodies')
    if not isinstance(design, dict) or any(not isinstance(design.get(k), list) for k in required):
        raise CadError('CAD intermediate design observation is incomplete')
    return {key: ([{field: value for field, value in item.items() if field != 'ms'}
                   for item in design[key]] if key == 'timeline' else design[key])
            for key in required}


class CadExecutionStore:
    """Persist native states under the worker's existing exclusive execution lock.

    A head update is the publication point. Interrupted writes leave unreferenced
    files available for diagnosis. The platform filesystem provides os.replace;
    callers keep one worker owner for the document, as CadBrain already requires.
    """

    def __init__(self, root: Path, contract_sha256: str, engine_version='0.28.0'):
        self.root = Path(root).resolve(strict=True)
        if (not self.root.is_dir() or not isinstance(contract_sha256, str)
                or len(contract_sha256) != 64 or any(c not in '0123456789abcdef' for c in contract_sha256)):
            raise CadError('CAD execution requires an owned root and contract digest')
        self.contract = contract_sha256
        self.engine = engine_version
        self.directory = self.root / 'execution-checkpoints'
        self.directory.mkdir(exist_ok=True)
        if self.directory.is_symlink():
            raise CadError('CAD checkpoint directory identity changed')
        self.head = self.directory / 'head.json'
        self.attempt = self.directory / 'attempt.json'
        self.engine_identity = self.directory / 'engine.json'
        self.engine_build = None

    def _bind_engine(self, session):
        """Bind every launch before reopening or mutating an accepted document."""
        build = getattr(session, 'engine_sha256', None)
        if (session.version != self.engine or not isinstance(build, str)
                or len(build) != 64 or any(c not in '0123456789abcdef' for c in build)):
            raise CadError('CAD execution requires a matching engine and executable fingerprint')
        identity = {'engine_version': self.engine, 'engine_sha256': build}
        if self.engine_identity.exists():
            if self._read(self.engine_identity) != identity:
                raise CadError('CAD checkpoint executable changed; preserve this run and start a new candidate')
        elif self.head.exists():
            raise CadError('CAD legacy checkpoint has no executable fingerprint; preserve it and start a new candidate')
        else:
            self._write(self.engine_identity, identity)
        self.engine_build = build

    def _write(self, path, value):
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    def _read(self, path):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4_000_000:
            raise CadError('CAD checkpoint record is unavailable or exceeds its size limit')
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise CadError('CAD checkpoint record cannot be read') from error

    def active(self):
        if not self.head.exists():
            return []
        value = self._read(self.head)
        if not self.engine_identity.exists():
            raise CadError('CAD legacy checkpoint has no executable fingerprint; preserve it and start a new candidate')
        engine = self._read(self.engine_identity)
        if (not isinstance(engine, dict) or engine.get('engine_version') != self.engine
                or not isinstance(engine.get('engine_sha256'), str)
                or len(engine['engine_sha256']) != 64
                or any(c not in '0123456789abcdef' for c in engine['engine_sha256'])
                or (self.engine_build is not None and engine['engine_sha256'] != self.engine_build)
                or value.get('engine_sha256') != engine['engine_sha256']):
            raise CadError('CAD checkpoint executable identity changed')
        self.engine_build = engine['engine_sha256']
        if value.get('contract_sha256') != self.contract or value.get('engine_version') != self.engine:
            raise CadError('CAD checkpoint contract or engine changed')
        identities = value.get('active')
        if not isinstance(identities, list) or len(identities) > 256 or len(set(identities)) != len(identities):
            raise CadError('Invalid CAD checkpoint chain')
        chain = []
        for identity in identities:
            # Validate IDs before using them in filesystem paths.
            if not isinstance(identity, str) or len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity):
                raise CadError('Invalid CAD checkpoint identity')
            record = ExecutionCheckpoint.model_validate(self._read(self.directory / (identity + '.json')))
            if (record.id != identity or record.contract_sha256 != self.contract
                    or record.engine_version != self.engine
                    or record.engine_sha256 != self.engine_build
                    or record.parent != (chain[-1].id if chain else None)):
                raise CadError('CAD checkpoint lineage changed')
            chain.append(record)
        return chain

    def observations(self, checkpoint):
        expected = f'execution-checkpoints/{checkpoint.id}/observations.json'
        if checkpoint.evidence_ref != expected:
            raise CadError('CAD checkpoint evidence identity changed')
        path = self.root / expected
        if path.parent.is_symlink() or path.is_symlink():
            raise CadError('CAD checkpoint evidence identity changed')
        value = self._read(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != checkpoint.evidence_sha256:
            raise CadError('CAD checkpoint evidence changed')
        return value

    async def recover(self, session, identity=None):
        self._bind_engine(session)
        chain = self.active()
        if not chain:
            if identity is not None or session.version != self.engine:
                raise CadError('CAD recovery requires an accepted checkpoint or a fresh matching engine')
            actual = design_identity(await session.tool('inspect_design'))
            if (actual['bodies'] or actual['sketches'] or actual['timeline']
                    or any(not item.get('model') for item in actual['params'])):
                raise CadError('CAD initial recovery requires an empty native document')
            self._write(self.attempt, {'state': 'recovered', 'checkpoint': None})
            return None
        record = next((item for item in chain if item.id == identity), None) if identity else chain[-1]
        if record is None:
            raise CadError('CAD recovery checkpoint is outside the active lineage')
        if session.version != record.engine_version:
            raise CadError('CAD recovery engine changed')
        expected = self.observations(record)
        await session.reopen(record.native)
        actual = design_identity(await session.tool('inspect_design'))
        if actual != expected['design']:
            raise CadError('CAD reopened design differs from its accepted state')
        self._write(self.attempt, {'state': 'recovered', 'checkpoint': record.id})
        return record

    async def execute(self, session, proposal: ExecutionGroup, *, validate, progress=None):
        """Promote only after native observations satisfy the supplied step checks.

        The mandatory validator belongs to the controller/measurement policy.
        Its empty diagnostic list establishes intermediate acceptance. Final
        delivery remains governed by the separate complete-part checks.
        """
        self._bind_engine(session)
        chain = self.active()
        current = chain[-1].id if chain else None
        if proposal.base_checkpoint != current or session.version != self.engine:
            raise CadError('CAD execution proposal has a stale base or engine')
        if self.attempt.exists() and self._read(self.attempt).get('state') in {'running', 'failed'}:
            raise CadError('CAD candidate requires recovery after interrupted or failed execution')
        if chain:
            expected = self.observations(chain[-1])['design']
            if design_identity(await session.tool('inspect_design')) != expected:
                raise CadError('CAD candidate changed since its accepted checkpoint')
        else:
            initial = design_identity(await session.tool('inspect_design'))
            if (initial['bodies'] or initial['sketches'] or initial['timeline']
                    or any(not item.get('model') for item in initial['params'])):
                raise CadError('CAD initial execution requires an empty native document')
        commands = [item.model_dump(exclude={'schema_version'}) for item in proposal.commands]
        validate_cut_intents(commands, proposal.cut_intents)
        identity = uuid.uuid4().hex
        folder = self.directory / identity
        folder.mkdir()
        proposal_value = proposal.model_dump(mode='json')
        self._write(folder / 'proposal.json', proposal_value)
        self._write(self.attempt, {'state': 'running', 'attempt': identity, 'base': current})
        if progress:
            await progress('cad_group_started', {'id': proposal.id, 'purpose': proposal.purpose,
                                                 'base_checkpoint': current})
        try:
            if proposal.workflow.parameters:
                await session.batch([proposal.workflow.parameter_command()])
            await session.construct(commands, proposal.workflow, cut_intents=proposal.cut_intents,
                                    enforce_cut_safety=True)
            design = design_identity(await session.tool('inspect_design'))
            graph = await session.tool('execute', {'command': 'parameters.graph', 'params': {}})
            observations = {'design': design, 'parameter_graph': graph,
                'cut_safety': list(session.cut_safety_reports),
                'unresolved_obligations': list(proposal.unresolved_obligations)}
            errors = await validate(proposal, observations)
            if errors:
                # Preserve the actual rejected state before recovery restores
                # the accepted head, including native-generated object names.
                observations['native_observations'] = list(session.observations)
                rejected = folder / 'rejected-observations.json'
                self._write(rejected, observations)
                raise CadCommandError({'failed': {'stage': 'intermediate_checks', 'diagnostics': errors,
                    'observation_ref': rejected.relative_to(self.root).as_posix(),
                    'observation_sha256': hashlib.sha256(rejected.read_bytes()).hexdigest(),
                    'observed_inventory': {key: [item.get('name') for item in design[key]]
                                           for key in ('sketches', 'timeline', 'bodies')}}})
            native_path = folder / 'part.sc'
            await session.tool('save', {'path': str(native_path)})
            native = session._artifact(native_path, 'solidcraft')
            mesh = None
            if design['bodies']:
                # Export the already evaluated geometry once. Solid previews can
                # then display the checkpoint without evaluating its history.
                mesh_path = folder / 'part.stl'
                await session.tool('export', {'path': str(mesh_path), 'format': 'stl'})
                mesh = session._artifact(mesh_path, 'stl').model_copy(
                    update={'source_sha256': native.sha256})
            observations['native_observations'] = list(session.observations)
            evidence = folder / 'observations.json'
            self._write(evidence, observations)
            record = ExecutionCheckpoint(id=identity, parent=current,
                contract_sha256=self.contract, engine_version=self.engine,
                engine_sha256=self.engine_build,
                proposal_sha256=digest(proposal_value), native=native, mesh=mesh,
                evidence_ref=evidence.relative_to(self.root).as_posix(),
                evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest())
            self._write(self.directory / (identity + '.json'), record.model_dump(mode='json'))
            self._write(self.head, {'contract_sha256': self.contract, 'engine_version': self.engine,
                                   'engine_sha256': self.engine_build,
                                   'active': [item.id for item in chain] + [identity]})
            self._write(self.attempt, {'state': 'accepted', 'checkpoint': identity})
        except BaseException as error:
            # Pre-publication failures preserve the accepted prefix. Publication
            # failures require rereading the head and recovery before mutation.
            self._write(folder / 'failure.json', {'type': type(error).__name__, 'diagnostic': str(error)[:4000]})
            self._write(self.attempt, {'state': 'failed', 'attempt': identity, 'base': current})
            raise
        if progress:
            await progress('cad_group_checkpoint', {'id': proposal.id, 'checkpoint': identity,
                'purpose': proposal.purpose, 'unresolved_obligations': list(proposal.unresolved_obligations)})
        return record

    def rewind(self, identity):
        """Retain the accepted prefix; preserve the invalidated suffix as evidence."""
        chain = self.active()
        index = -1 if identity is None else next((i for i, item in enumerate(chain) if item.id == identity), None)
        if index is None:
            raise CadError('CAD revision target is outside the active lineage')
        self._write(self.directory / ('invalidation-' + uuid.uuid4().hex + '.json'), {
            'base': identity, 'invalidated': [item.id for item in chain[index + 1:]]})
        self._write(self.head, {'contract_sha256': self.contract, 'engine_version': self.engine,
                               'engine_sha256': self.engine_build,
                               'active': [item.id for item in chain[:index + 1]]})
