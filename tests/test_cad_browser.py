"""Durable browser CAD recovery and ownership regression cases."""

import pytest

from bigbrain.cad_browser import BrowserCadBridge, BridgeConflict, digest


@pytest.fixture
def bridge(tmp_path):
    bridge = BrowserCadBridge(tmp_path)
    bridge.initialize(b'original')
    bridge.connect({'build': '0.28.0-test'})
    bridge.control('resume', 0, digest(b'original'))
    return bridge


def enqueue(bridge, operation='op1'):
    state = bridge.state()
    return bridge.enqueue(operation, state['revision'], state['hash'], 'parameters.change',
                          {'name': 'width', 'expression': '61 mm'})


def test_duplicate_delivery_and_restart(bridge):
    enqueue(bridge)
    generation = bridge.state()['generation']
    bridge.claim(generation)
    receipt = bridge.accept('op1', generation, b'edited', {'value': 61})
    assert bridge.accept('op1', generation, b'edited', {'value': 61}) == receipt
    # Losing the acknowledgement then restarting the Python process preserves it.
    restarted = BrowserCadBridge(bridge.root)
    assert restarted.enqueue('op1', 0, digest(b'original'), 'parameters.change',
                             {'name': 'width', 'expression': '61 mm'})['status'] == 'accepted'
    assert restarted.state()['revision'] == 1
    assert restarted.checkpoint() == b'edited'
    assert restarted.checkpoint(0) == b'original'
    assert restarted.checkpoint(1) == b'edited'
    result = restarted.result('op1')
    assert result['revision'] == 1
    assert result['observation']['checkpointHash'] == digest(b'edited')
    with pytest.raises(BridgeConflict):
        bridge.accept('op1', generation, b'different bytes', {'value': 61})


def test_interruption_restores_base_and_fences_old_client(bridge):
    enqueue(bridge)
    old = bridge.state()['generation']
    first = bridge.claim(old)
    bridge.connect({'build': '0.28.0-test'})
    new = bridge.state()['generation']
    with pytest.raises(BridgeConflict):
        bridge.accept('op1', old, b'edited', {})
    second = bridge.claim(new)
    assert second['id'] == first['id']
    assert second['baseHash'] == digest(bridge.checkpoint())
    bridge.accept('op1', new, b'edited', {})
    assert bridge.state()['revision'] == 1


def test_pause_drains_then_manual_save_then_resume(bridge):
    enqueue(bridge)
    generation = bridge.state()['generation']
    bridge.claim(generation)
    state = bridge.control('pause', 0, digest(b'original'))
    assert state['owner'] == 'agent' and state['pause']
    with pytest.raises(BridgeConflict):
        bridge.save_manual(generation, 0, digest(b'original'), b'manual')
    bridge.accept('op1', generation, b'edited', {})
    assert bridge.state()['owner'] == 'user'
    bridge.save_manual(generation, 1, digest(b'edited'), b'manual')
    assert bridge.checkpoint(1) == b'edited'
    assert bridge.checkpoint(2) == b'manual'
    with pytest.raises(BridgeConflict):
        bridge.control('resume', 1, digest(b'edited'))
    bridge.control('resume', 2, digest(b'manual'))
    enqueue(bridge, 'op2')
    assert bridge.claim(generation)['baseHash'] == digest(b'manual')


def test_stop_rejects_inflight_and_preserves_checkpoint(bridge):
    enqueue(bridge)
    generation = bridge.state()['generation']
    bridge.claim(generation)
    bridge.control('stop', 0, digest(b'original'))
    with pytest.raises(BridgeConflict):
        bridge.accept('op1', generation, b'edited', {})
    assert bridge.checkpoint() == b'original'
    assert bridge.state()['operations'][0]['status'] == 'cancelled'


def test_changed_operation_build_and_stale_revision_rejected(bridge):
    enqueue(bridge)
    with pytest.raises(BridgeConflict):
        bridge.enqueue('op1', 0, digest(b'original'), 'solid.box', {})
    with pytest.raises(BridgeConflict):
        bridge.connect({'build': 'another-build'})
    with pytest.raises(BridgeConflict):
        bridge.enqueue('op2', 9, digest(b'original'), 'solid.box', {})
    with pytest.raises(ValueError):
        bridge.enqueue('op3', 0, digest(b'original'), 'file.open', {'path': '/etc/passwd'})


def test_pause_during_disconnect_and_failed_geometry(bridge):
    enqueue(bridge)
    generation = bridge.state()['generation']
    bridge.claim(generation)
    bridge.control('pause', 0, digest(b'original'))
    state = bridge.connect({'build': '0.28.0-test'})
    assert state['owner'] == 'user' and not state['pause']
    assert state['operations'][0]['status'] == 'cancelled'
    bridge.control('resume', 0, digest(b'original'))
    enqueue(bridge, 'op2')
    bridge.claim(state['generation'])
    bridge.fail('op2', state['generation'], 'native reconstruction failed')
    assert bridge.state()['owner'] == 'user'
    assert bridge.checkpoint() == b'original'
