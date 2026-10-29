"""Manual release is version-bound, permission-scoped and interruption-safe."""

import hashlib
import json

import pytest

from bigbrain.local_projects import ProjectAccessError, ProjectRegistry
from bigbrain.local_project_patches import apply_patch_set
from bigbrain.local_project_recovery import project_transactions
from bigbrain.local_project_retention import inspect_retention, release_retention, retained_journals, read_retention


def fixture(tmp_path, rights=('read', 'write', 'execute', 'delete')):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'main.py').write_bytes(b'original\n')
    registry = ProjectRegistry(tmp_path / 'registry' / 'registry.json')
    project = registry.attach(source, rights)
    result = apply_patch_set(registry, project['id'], 1, [{
        'path': 'main.py', 'sha256': hashlib.sha256(b'original\n').hexdigest(),
        'content': 'candidate\n'}])
    return source, registry, project, result['transactionId']


def inspect(registry, project, transaction):
    return inspect_retention(registry, project['id'], project['revision'], transaction)


def release(registry, project, transaction, snapshot, confirmed=True):
    return release_retention(registry, project['id'], project['revision'], transaction, snapshot['token'], confirmed)


def test_release_keeps_sources_and_foreign_files_and_scrubs_preimages(tmp_path):
    source, registry, project, transaction = fixture(tmp_path)
    (source / 'user.txt').write_bytes(b'keep user file\n')
    snapshot = inspect(registry, project, transaction)
    assert snapshot['bytes'] == len(b'original\n')
    assert release(registry, project, transaction, snapshot)['state'] == 'released'
    assert (source / 'main.py').read_bytes() == b'candidate\n'
    assert (source / 'user.txt').read_bytes() == b'keep user file\n'
    assert (source / '.bigbrain-recovery/.owner.json').exists()
    assert retained_journals(registry, project) == []
    assert project_transactions(registry, project) == []
    state = json.loads((registry.path.parent / 'transactions' / (transaction + '.json')).read_text())
    assert state['files']['main.py']['before'] is None
    assert state['files']['main.py']['before_sha256'] == hashlib.sha256(b'original\n').hexdigest()
    with registry.access(project['id'], 1, 'execute'):
        pass


def test_confirmation_and_deletion_grant_are_required(tmp_path):
    source, registry, project, transaction = fixture(tmp_path, ('read', 'write'))
    snapshot = inspect(registry, project, transaction)
    with pytest.raises(ProjectAccessError, match='confirmation'):
        release(registry, project, transaction, snapshot, False)
    with pytest.raises(ProjectAccessError, match='grant'):
        release(registry, project, transaction, snapshot)
    assert (source / snapshot['files'][0]['artifact']).read_bytes() == b'original\n'


def test_changed_inventory_is_preserved_and_requires_resolution(tmp_path):
    source, registry, project, transaction = fixture(tmp_path)
    snapshot = inspect(registry, project, transaction)
    retained = source / snapshot['files'][0]['artifact']
    retained.write_bytes(b'late editor write\n')
    with pytest.raises(ProjectAccessError):
        release(registry, project, transaction, snapshot)
    assert not inspect(registry, project, transaction)['eligible']
    assert retained.read_bytes() == b'late editor write\n'
    assert (source / 'main.py').read_bytes() == b'candidate\n'


def test_open_editor_pauses_release_and_can_be_inspected_then_resumed(tmp_path):
    source, registry, project, transaction = fixture(tmp_path)
    snapshot = inspect(registry, project, transaction)
    with (source / snapshot['files'][0]['artifact']).open('r+b', buffering=0) as editor:
        with pytest.raises(OSError):
            release(registry, project, transaction, snapshot)
        editor.write(b'editor still owns this file\n')
        editor.truncate()
    assert project_transactions(registry, project)[0]['state'] == 'retention_pending'
    with pytest.raises(ProjectAccessError, match='recovery'):
        with registry.access(project['id'], 1, 'execute'):
            pass
    remaining = inspect(registry, project, transaction)
    assert read_retention(registry, project['id'], 1, transaction,
                          remaining['files'][0]['artifact'])['content'] == 'editor still owns this file\n'
    assert release(registry, project, transaction, remaining)['state'] == 'released'
    assert (source / 'main.py').read_bytes() == b'candidate\n'


def test_interrupt_after_retirement_keeps_discoverable_versions(tmp_path, monkeypatch):
    from bigbrain.project_transaction import ProjectTransaction
    source, registry, project, transaction = fixture(tmp_path)
    snapshot = inspect(registry, project, transaction)
    original = ProjectTransaction._save
    class Interrupted(BaseException):
        pass
    def interrupt(self, state):
        if any(item['status'] == 'retired' for item in state.get('retention', {}).get('moves', [])):
            raise Interrupted()
        return original(self, state)
    monkeypatch.setattr(ProjectTransaction, '_save', interrupt)
    with pytest.raises(Interrupted):
        release(registry, project, transaction, snapshot)
    monkeypatch.setattr(ProjectTransaction, '_save', original)
    remaining = inspect(registry, project, transaction)
    assert remaining['bytes'] == len(b'original\n')
    assert (source / remaining['files'][0]['artifact']).read_bytes() == b'original\n'
    assert release(registry, project, transaction, remaining)['state'] == 'released'


def test_revocation_and_cross_project_access_preserve_artifacts(tmp_path):
    source, registry, project, transaction = fixture(tmp_path)
    snapshot = inspect(registry, project, transaction)
    other = tmp_path / 'other'
    other.mkdir()
    other_project = registry.attach(other, ('read', 'delete'))
    with pytest.raises(ProjectAccessError, match='different project'):
        inspect(registry, other_project, transaction)
    registry.change(project['id'], 1, state='revoked')
    with pytest.raises(ProjectAccessError, match='grant'):
        release(registry, project, transaction, snapshot)
    assert (source / snapshot['files'][0]['artifact']).exists()


def test_artifacts_appearing_during_release_require_another_confirmation(tmp_path, monkeypatch):
    from bigbrain.native_publication import LinuxPublication
    source, registry, project, transaction = fixture(tmp_path)
    snapshot = inspect(registry, project, transaction)
    original = LinuxPublication.release_preserved
    def recreated(self, path, expected, *, anchors=None):
        original(self, path, expected, anchors=anchors)
        (source / snapshot['files'][0]['artifact']).write_bytes(b'new retained version\n')
    monkeypatch.setattr(LinuxPublication, 'release_preserved', recreated)
    with pytest.raises(ProjectAccessError, match='Additional retained'):
        release(registry, project, transaction, snapshot)
    assert (source / snapshot['files'][0]['artifact']).read_bytes() == b'new retained version\n'
    assert project_transactions(registry, project)[0]['state'] == 'retention_pending'


def test_forged_retained_path_is_refused(tmp_path):
    source, registry, project, transaction = fixture(tmp_path)
    journal = registry.path.parent / 'transactions' / (transaction + '.json')
    state = json.loads(journal.read_text())
    state['publications'][0]['preserved'] = '../foreign.txt'
    journal.write_text(json.dumps(state))
    with pytest.raises(ProjectAccessError, match='namespace'):
        inspect(registry, project, transaction)
    assert (source / 'main.py').read_bytes() == b'candidate\n'


@pytest.mark.asyncio
async def test_http_release_requires_current_inventory_and_explicit_confirmation(tmp_path):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from bigbrain.web.local_projects_api import setup_local_project_routes
    source, registry, project, transaction = fixture(tmp_path)
    app = web.Application()
    setup_local_project_routes(app, registry=registry)
    async with TestClient(TestServer(app)) as client:
        headers = {'Origin': str(client.make_url('')).rstrip('/'), 'X-BigBrain-Local': '1'}
        request = {'projectId': project['id'], 'revision': 1, 'transactionId': transaction}
        response = await client.post('/api/local-projects/inspect-retention', json=request, headers=headers)
        snapshot = await response.json()
        assert response.status == 200 and snapshot['eligible']
        response = await client.post('/api/local-projects/release-retention',
            json={**request, 'token': snapshot['token']}, headers=headers)
        assert response.status == 400
        assert (source / snapshot['files'][0]['artifact']).exists()
        response = await client.post('/api/local-projects/release-retention',
            json={**request, 'token': snapshot['token'], 'confirmed': True}, headers=headers)
        assert response.status == 200
        assert (await response.json())['state'] == 'released'
        assert (source / 'main.py').read_bytes() == b'candidate\n'


def test_interruption_after_unlink_can_close_the_authorized_release(tmp_path, monkeypatch):
    from bigbrain.project_transaction import ProjectTransaction
    source, registry, project, transaction = fixture(tmp_path)
    snapshot = inspect(registry, project, transaction)
    original = ProjectTransaction._save
    class Interrupted(BaseException):
        pass
    def interrupt(self, state):
        if any(item['status'] == 'released' for item in state.get('retention', {}).get('moves', [])):
            raise Interrupted()
        return original(self, state)
    monkeypatch.setattr(ProjectTransaction, '_save', interrupt)
    with pytest.raises(Interrupted):
        release(registry, project, transaction, snapshot)
    monkeypatch.setattr(ProjectTransaction, '_save', original)
    remaining = inspect(registry, project, transaction)
    assert remaining['files'] == []
    assert release(registry, project, transaction, remaining)['state'] == 'released'
    assert (source / 'main.py').read_bytes() == b'candidate\n'
