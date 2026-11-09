"""Configured CAD storage relocation and unchanged artifact integrity gates."""
import hashlib
import os

import pytest

from bigbrain.cad_contracts import CadRevision, CadArtifact
from bigbrain.cad_store import CadStore
from bigbrain.solidcraft import CadError


def relocated_store(tmp_path, monkeypatch):
    actual = tmp_path / 'disk'
    actual.mkdir()
    configured = tmp_path / 'configured'
    configured.symlink_to(actual, target_is_directory=True)
    store = CadStore(configured)
    doc = store.create('session')
    file = store.directory(doc) / 'part.sc'
    file.write_bytes(b'owned native artifact')
    artifact = CadArtifact(path='part.sc', format='solidcraft', size_bytes=file.stat().st_size,
                           sha256=hashlib.sha256(file.read_bytes()).hexdigest())
    revision = CadRevision(project_id=doc, document_id=doc, revision=1,
                           engine_version='0.28.0', native=artifact, exports=())
    monkeypatch.setattr(store, 'view', lambda *args: {'document': revision.model_dump(mode='json')})
    return store, configured, actual, doc, file


def test_configured_storage_link_is_pinned_and_artifact_remains_readable(tmp_path, monkeypatch):
    store, configured, actual, doc, file = relocated_store(tmp_path, monkeypatch)
    assert store.root == actual.resolve()
    assert store.artifact(doc, 'session', 1, 'native')[1] == file.read_bytes()
    other = tmp_path / 'other'
    other.mkdir()
    configured.unlink()
    configured.symlink_to(other, target_is_directory=True)
    assert store.artifact(doc, 'session', 1, 'native')[1] == file.read_bytes()
    with pytest.raises(CadError, match='another conversation'):
        store.artifact(doc, 'other-session', 1, 'native')


@pytest.mark.parametrize('change', ['symlink', 'hardlink', 'size', 'bytes', 'document_link'])
def test_relocated_store_preserves_inner_identity_guards(tmp_path, monkeypatch, change):
    store, _, _, doc, file = relocated_store(tmp_path, monkeypatch)
    if change == 'document_link':
        original = store.directory(doc)
        moved = original.with_name('moved')
        original.rename(moved)
        original.symlink_to(moved, target_is_directory=True)
    elif change in {'symlink', 'hardlink'}:
        moved = file.with_name('other.sc')
        file.rename(moved)
        if change == 'symlink':
            file.symlink_to(moved)
        else:
            os.link(moved, file)
    elif change == 'size':
        file.write_bytes(b'changed')
    else:
        file.write_bytes(b'x' * file.stat().st_size)
    with pytest.raises(CadError):
        store.artifact(doc, 'session', 1, 'native')
