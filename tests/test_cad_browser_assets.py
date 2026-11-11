"""Qualified build admission and retained document lineage checks."""

import hashlib
import json

import pytest

from bigbrain.cad_browser import BrowserCadBridge, BridgeConflict
from bigbrain.web.cad_browser_assets import BrowserCadAssets


def test_pinned_browser_build_and_tampered_asset(tmp_path, monkeypatch):
    assets = {'index.html': b'<html>fixture</html>', 'engine.wasm': b'wasm-fixture'}
    for name, data in assets.items():
        (tmp_path / name).write_bytes(data)
    manifest = tmp_path / 'manifest.json'
    data = {'source_tag':'v0.28.0', 'source_commit':'ee6b85605a32948bcbd9ae437a564cab826689ec',
            'patches':[], 'assets':{name:hashlib.sha256(value).hexdigest() for name,value in assets.items()}}
    manifest.write_text(json.dumps(data))
    monkeypatch.setenv('BIGBRAIN_SOLIDCRAFT_WEB_DIR', str(tmp_path))
    monkeypatch.setenv('BIGBRAIN_SOLIDCRAFT_WEB_MANIFEST', str(manifest))
    assert BrowserCadAssets().capability()['available']
    (tmp_path / 'engine.wasm').write_bytes(b'changed')
    assert not BrowserCadAssets().capability()['available']
    data['patches'] = ['unqualified-helix']
    manifest.write_text(json.dumps(data))
    assert not BrowserCadAssets().capability()['available']


def test_editor_retains_manual_branch_and_rejects_changed_publication(tmp_path):
    bridge = BrowserCadBridge(tmp_path)
    bridge.initialize(b'published')
    bridge.connect({'build':'0.28.0'})
    state = bridge.state()
    bridge.save_manual(state['generation'], 0, state['hash'], b'manual')
    bridge.initialize(b'published')
    assert bridge.checkpoint() == b'manual'
    with pytest.raises(BridgeConflict):
        bridge.initialize(b'new publication')
    assert bridge.checkpoint() == b'manual'


def test_hosted_build_requires_both_worker_assets(tmp_path, monkeypatch):
    assets = {'index.html': b'viewer', 'engine.wasm': b'viewer-wasm',
              'worker/bigbrain_worker_probe.js': b'worker-module'}
    manifest = tmp_path / 'manifest.json'
    monkeypatch.setenv('BIGBRAIN_SOLIDCRAFT_WEB_DIR', str(tmp_path))
    monkeypatch.setenv('BIGBRAIN_SOLIDCRAFT_WEB_MANIFEST', str(manifest))

    def capability():
        for name, content in assets.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        manifest.write_text(json.dumps({
            'source_tag': 'v0.28.0', 'source_commit': 'ee6b85605a32948bcbd9ae437a564cab826689ec',
            'patches': ['bigbrain-hosted-cache-v1'],
            'assets': {name: hashlib.sha256(content).hexdigest() for name, content in assets.items()},
        }))
        return BrowserCadAssets().capability()

    assert not capability()['available']
    assets['worker/bigbrain_worker_probe_bg.wasm'] = b'worker-wasm'
    result = capability()
    assert result['available']
    assert result['worker'] == f"/static/cad-geometry-worker.mjs?build={result['build']}"
