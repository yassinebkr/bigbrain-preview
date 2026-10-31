"""Desktop handoff keeps published CAD bytes immutable and bounds launches."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from bigbrain.cad_desktop import CadDesktop
from bigbrain.solidcraft import CadError


def test_gui_uses_verified_copy_and_argument_array(tmp_path, monkeypatch):
    gui = tmp_path / 'SolidCraft GUI'
    gui.touch()
    monkeypatch.setattr('bigbrain.cad_desktop.desktop_executable', lambda: gui)
    store = Mock()
    store.artifact.return_value = (None, b'published CAD bytes')
    store.authorize.return_value = tmp_path
    process = Mock()
    process.poll.return_value = None
    launch = Mock(return_value=process)
    monkeypatch.setattr('bigbrain.cad_desktop.subprocess.Popen', launch)
    desktop = CadDesktop()
    result = desktop.open(store, 'doc', 'session', 2)
    assert result['status'] == 'requested'
    store.artifact.assert_called_once_with('doc', 'session', 2, 'native')
    args = launch.call_args.args[0]
    assert args[0] == str(gui)
    copy = Path(args[1])
    assert copy.read_bytes() == b'published CAD bytes'
    assert copy.parent.parent == tmp_path and copy.parent.name.startswith('desktop-')
    copy.write_bytes(b'external edit')
    assert store.artifact.return_value[1] == b'published CAD bytes'
    desktop.processes = [process] * 4
    with pytest.raises(CadError, match='Four CAD'):
        desktop.open(store, 'doc', 'session', 2)


def test_failed_gui_launch_cleans_only_new_copy(tmp_path, monkeypatch):
    monkeypatch.setattr('bigbrain.cad_desktop.desktop_executable', lambda: tmp_path / 'gui')
    store = Mock()
    store.artifact.return_value = (None, b'original')
    store.authorize.return_value = tmp_path
    monkeypatch.setattr('bigbrain.cad_desktop.subprocess.Popen', Mock(side_effect=OSError('launch error')))
    with pytest.raises(CadError, match='launch failed'):
        CadDesktop().open(store, 'doc', 'session', 1)
    assert list(tmp_path.iterdir()) == []


def test_hash_failure_prevents_copy_and_launch(tmp_path, monkeypatch):
    monkeypatch.setattr('bigbrain.cad_desktop.desktop_executable', lambda: tmp_path / 'gui')
    store = Mock()
    store.artifact.side_effect = CadError('hash changed')
    launch = Mock()
    monkeypatch.setattr('bigbrain.cad_desktop.subprocess.Popen', launch)
    with pytest.raises(CadError, match='hash changed'):
        CadDesktop().open(store, 'doc', 'session', 1)
    launch.assert_not_called()
    assert list(tmp_path.iterdir()) == []
