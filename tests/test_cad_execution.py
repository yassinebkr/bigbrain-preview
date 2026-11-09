"""Checkpoint publication, failure recovery and conservative replay boundaries."""

from copy import deepcopy
import asyncio
import json

import pytest

from bigbrain.cad_execution import CadExecutionStore, ExecutionGroup
from bigbrain.solidcraft import CadError, SolidCraftSession


def group(base=None, *, name='base'):
    return ExecutionGroup.model_validate({
        'id': name, 'purpose': 'Build base envelope', 'base_checkpoint': base,
        'commands': [{'command': 'solid.box', 'params': {
            'length': 10, 'width': 10, 'height': 5, 'body_name': 'Base', 'name': 'Base'}}],
        'workflow': {'features': [{'name': 'Base', 'purpose': 'Base envelope'}],
            'bodies': ['Base'], 'groups': [{'name': 'Part', 'features': ['Base'], 'bodies': ['Base']}],
            'primitive_reason': 'A rectangular envelope is the intended native primitive.'},
        'unresolved_obligations': ['overall-dimensions'],
    })


async def accept(proposal, observations):
    return []


def test_pending_obligations_accept_bounded_descriptions():
    from pydantic import ValidationError

    payload = group().model_dump()
    description = 'Final independent verification of dimensions and local details. ' * 4
    payload['unresolved_obligations'] = [description]
    result = ExecutionGroup.model_validate(payload)
    assert result.unresolved_obligations == (description,)
    assert ExecutionGroup.model_validate_json(result.model_dump_json()) == result
    for invalid in ('', 'x' * 1001):
        payload['unresolved_obligations'] = [invalid]
        with pytest.raises(ValidationError):
            ExecutionGroup.model_validate(payload)
    payload['unresolved_obligations'] = ['pending'] * 65
    with pytest.raises(ValidationError):
        ExecutionGroup.model_validate(payload)
    payload['unresolved_obligations'] = ['pending']
    payload['id'] = 'x' * 161
    with pytest.raises(ValidationError):
        ExecutionGroup.model_validate(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['recover', 'execute'])
async def test_same_version_different_build_rejected_before_native_access(tmp_path, action):
    store, session = CadExecutionStore(tmp_path, 'a' * 64), Session(tmp_path)
    first = await store.execute(session, group(), validate=accept)
    before = store.head.read_bytes()
    other = Session(tmp_path)
    other.engine_sha256 = 'f' * 64
    with pytest.raises(CadError, match='executable changed'):
        if action == 'recover':
            await CadExecutionStore(tmp_path, 'a' * 64).recover(other)
        else:
            await store.execute(other, group(first.id), validate=accept)
    assert other.mutations == 0 and other.design['bodies'] == []
    assert store.head.read_bytes() == before
    await CadExecutionStore(tmp_path, 'a' * 64).recover(Session(tmp_path))


@pytest.mark.asyncio
async def test_legacy_checkpoint_preserved_without_implicit_rebinding(tmp_path):
    store, session = CadExecutionStore(tmp_path, 'a' * 64), Session(tmp_path)
    first = await store.execute(session, group(), validate=accept)
    store.engine_identity.unlink()
    before = store.head.read_bytes()
    with pytest.raises(CadError, match='legacy checkpoint'):
        await CadExecutionStore(tmp_path, 'a' * 64).recover(Session(tmp_path))
    assert store.head.read_bytes() == before
    assert (tmp_path / first.native.path).is_file()
    assert not store.engine_identity.exists()


@pytest.mark.asyncio
async def test_missing_fingerprint_rejected_before_first_mutation(tmp_path):
    session = Session(tmp_path)
    session.engine_sha256 = None
    with pytest.raises(CadError, match='executable fingerprint'):
        await CadExecutionStore(tmp_path, 'a' * 64).execute(session, group(), validate=accept)
    assert session.mutations == 0


class Session:
    version = '0.28.0'
    engine_sha256 = 'e' * 64
    cut_safety_reports = []
    observations = []

    def __init__(self, root):
        self.root = root
        self.design = {'params': [], 'timeline': [], 'sketches': [], 'bodies': []}
        self.mutations = 0

    async def construct(self, commands, workflow, **kwargs):
        self.mutations += 1
        self.design['bodies'].append({'name': f'Body{self.mutations}'})

    async def tool(self, name, arguments=None):
        if name == 'inspect_design':
            return deepcopy(self.design)
        if name == 'execute':
            return {'nodes': [], 'edges': [], 'errors': [], 'cycles': []}
        if name == 'body_topology':
            return {'body': arguments['body'], 'faces': [], 'edges': []}
        if name == 'save':
            from pathlib import Path
            Path(arguments['path']).write_text(json.dumps(self.design))
            return {}
        raise AssertionError(name)

    def _artifact(self, path, format):
        return SolidCraftSession._artifact(self, path, format)

    @property
    def scratch(self):
        return self.root

    async def reopen(self, artifact):
        actual = self._artifact(self.root / artifact.path, artifact.format)
        if actual.sha256 != artifact.sha256:
            raise CadError('CAD revision changed before reopening')
        self.design = json.loads((self.root / artifact.path).read_text())


@pytest.mark.asyncio
async def test_failed_checks_keep_prefix_and_require_recovery(tmp_path):
    store, session = CadExecutionStore(tmp_path, 'a' * 64), Session(tmp_path)
    first = await store.execute(session, group(), validate=accept)

    async def reject(*args):
        return ['neighboring material was removed']

    with pytest.raises(CadError, match='neighboring material'):
        await store.execute(session, group(first.id, name='bad'), validate=reject)
    assert [item.id for item in store.active()] == [first.id]
    with pytest.raises(CadError, match='requires recovery'):
        await store.execute(session, group(first.id), validate=accept)
    fresh = Session(tmp_path)
    await store.recover(fresh)
    second = await store.execute(fresh, group(first.id, name='repaired'), validate=accept)
    assert second.parent == first.id


@pytest.mark.asyncio
async def test_rewind_preserves_evidence_and_rejects_descendant_base(tmp_path):
    store, session = CadExecutionStore(tmp_path, 'a' * 64), Session(tmp_path)
    first = await store.execute(session, group(), validate=accept)
    second = await store.execute(session, group(first.id, name='second'), validate=accept)
    store.rewind(first.id)
    assert (tmp_path / second.native.path).exists()
    with pytest.raises(CadError, match='stale base'):
        await store.execute(session, group(second.id), validate=accept)
    # Live state also has to be restored before replacement work can execute.
    with pytest.raises(CadError, match='changed since'):
        await store.execute(session, group(first.id), validate=accept)
    await store.recover(session)
    replacement = await store.execute(session, group(first.id, name='replacement'), validate=accept)
    assert [item.id for item in store.active()] == [first.id, replacement.id]


@pytest.mark.asyncio
async def test_checkpoint_evidence_and_contract_are_bound(tmp_path):
    store, session = CadExecutionStore(tmp_path, 'a' * 64), Session(tmp_path)
    first = await store.execute(session, group(), validate=accept)
    with pytest.raises(CadError, match='contract or engine'):
        CadExecutionStore(tmp_path, 'b' * 64).active()
    evidence = tmp_path / first.evidence_ref
    evidence.write_text(evidence.read_text() + ' ')
    with pytest.raises(CadError, match='evidence changed'):
        await store.recover(session)


@pytest.mark.asyncio
async def test_interrupted_head_publication_requires_recovery(tmp_path, monkeypatch):
    store, session = CadExecutionStore(tmp_path, 'a' * 64), Session(tmp_path)
    first = await store.execute(session, group(), validate=accept)
    write = store._write

    def interrupted(path, value):
        if path == store.head:
            raise OSError('simulated interrupted manifest publication')
        write(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(store, '_write', interrupted)
        with pytest.raises(OSError, match='interrupted manifest'):
            await store.execute(session, group(first.id), validate=accept)
    assert [item.id for item in store.active()] == [first.id]
    await store.recover(session)
    assert len(session.design['bodies']) == 1


@pytest.mark.asyncio
async def test_cancelled_initial_group_requires_fresh_empty_recovery(tmp_path):
    store, session = CadExecutionStore(tmp_path, 'a' * 64), Session(tmp_path)

    async def cancelled(*args):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await store.execute(session, group(), validate=cancelled)
    assert store.active() == []
    with pytest.raises(CadError, match='empty native document'):
        await store.recover(session)
    fresh = Session(tmp_path)
    assert await store.recover(fresh) is None
    await store.execute(fresh, group(), validate=accept)


@pytest.mark.asyncio
async def test_native_bytes_are_checked_during_checkpoint_recovery(tmp_path):
    store, session = CadExecutionStore(tmp_path, 'a' * 64), Session(tmp_path)
    first = await store.execute(session, group(), validate=accept)
    path = tmp_path / first.native.path
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(CadError, match='changed before reopening'):
        await store.recover(Session(tmp_path))


@pytest.mark.asyncio
async def test_native_execution_checkpoint_round_trip(tmp_path, cad_native_engine):
    store = CadExecutionStore(tmp_path, 'a' * 64)

    async def checked(proposal, observations):
        return proposal.workflow.diagnostics(observations['design'], observations['parameter_graph'])

    async with SolidCraftSession(tmp_path) as native:
        checkpoint = await store.execute(native, group(), validate=checked)
    async with SolidCraftSession(tmp_path) as recovered:
        assert (await store.recover(recovered)).id == checkpoint.id
        capture = await recovered.capture('a' * 32, 'a' * 32, 1)
        assert capture.geometry.volume_mm3 == pytest.approx(500, abs=0.001)
