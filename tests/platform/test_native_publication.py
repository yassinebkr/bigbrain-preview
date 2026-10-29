"""Native cases run independently of the application's legacy OS imports."""

import ctypes
import importlib.util
import os
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('native_publication',
    Path(__file__).parents[2] / 'bigbrain/native_publication.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


@pytest.fixture
def publication(tmp_path):
    backend = native.publication_backend()
    recovery = tmp_path / '.bigbrain-recovery'
    recovery.mkdir()
    source, candidate = tmp_path / 'main.txt', recovery / 'candidate'
    source.write_bytes(b'original\n')
    candidate.write_bytes(b'candidate\n')
    return backend, source, candidate, backend.preservation_path(candidate)


def test_replacement_preserves_actual_displaced_bytes(publication):
    backend, source, candidate, preserved = publication
    source.write_bytes(b'external edit\n')
    backend.replace_preserving(source, candidate, preserved)
    assert source.read_bytes() == b'candidate\n'
    assert preserved.read_bytes() == b'external edit\n'


def test_concurrent_creation_is_preserved(publication):
    backend, source, candidate, _ = publication
    with pytest.raises(OSError):
        backend.create(source, candidate)
    assert source.read_bytes() == b'original\n'
    assert candidate.read_bytes() == b'candidate\n'


def test_creation_into_empty_destination(publication):
    backend, source, candidate, _ = publication
    destination = source.with_name('new.txt')
    backend.create(destination, candidate)
    assert destination.read_bytes() == b'candidate\n'
    assert not candidate.exists()


def test_retirement_preserves_content_and_refuses_backup_collision(publication):
    backend, source, candidate, preserved = publication
    preserved = candidate.with_name('retired')
    backend.retire(source, preserved)
    assert not source.exists()
    assert preserved.read_bytes() == b'original\n'
    source.write_bytes(b'later edit\n')
    with pytest.raises(OSError):
        backend.retire(source, preserved)
    assert source.read_bytes() == b'later edit\n'
    assert preserved.read_bytes() == b'original\n'


def test_already_open_editor_remains_recoverable(publication):
    backend, source, candidate, preserved = publication
    data = b'late editor save\n'
    if os.name == 'nt':
        from ctypes import wintypes
        api = backend.api
        handle = api.CreateFileW(str(source), 0xC0000000, 0x7, None, 3, 0x80, None)
        assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
        api.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                  ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        api.WriteFile.restype = wintypes.BOOL
        api.SetEndOfFile.argtypes = [wintypes.HANDLE]
        api.SetEndOfFile.restype = wintypes.BOOL
        api.FlushFileBuffers.argtypes = [wintypes.HANDLE]
        api.FlushFileBuffers.restype = wintypes.BOOL
        try:
            backend.replace_preserving(source, candidate, preserved)
            written = wintypes.DWORD()
            buffer = ctypes.create_string_buffer(data)
            assert api.WriteFile(handle, buffer, len(data), ctypes.byref(written), None)
            assert written.value == len(data)
            assert api.SetEndOfFile(handle)
            assert api.FlushFileBuffers(handle)
        finally:
            api.CloseHandle(handle)
    else:
        with source.open('r+b', buffering=0) as editor:
            backend.replace_preserving(source, candidate, preserved)
            editor.write(data)
            editor.truncate()
            os.fsync(editor.fileno())
    assert source.read_bytes() == b'candidate\n'
    assert preserved.read_bytes() == data


def test_symlink_directory_is_refused(publication, tmp_path):
    backend, source, candidate, _ = publication
    real = tmp_path / 'outside'
    real.mkdir()
    alias = tmp_path / 'alias'
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip('Directory symlink creation unavailable on this Windows account')
    with pytest.raises(OSError):
        backend.create(alias / 'new.txt', candidate)
    assert not (real / 'new.txt').exists()
    assert candidate.read_bytes() == b'candidate\n'


def test_missing_source_preserves_candidate(publication):
    backend, source, candidate, preserved = publication
    source.unlink()
    with pytest.raises(OSError):
        backend.replace_preserving(source, candidate, preserved)
    assert candidate.read_bytes() == b'candidate\n'
    assert not source.exists()


def test_unsupported_platform_stops_explicitly(monkeypatch):
    monkeypatch.setattr(native.sys, 'platform', 'unsupported-test-host')
    with pytest.raises(OSError, match='Linux and Windows'):
        native.publication_backend()


def test_replaced_directory_anchor_is_refused(publication, tmp_path):
    backend, source, candidate, _ = publication
    holder = tmp_path / 'holder'
    holder.mkdir()
    anchors = {str(holder): backend.directory_identity(holder)}
    holder.rename(tmp_path / 'old-holder')
    holder.mkdir()
    with pytest.raises(OSError, match='identity changed'):
        backend.create(holder / 'new.txt', candidate, anchors=anchors)
    assert not (holder / 'new.txt').exists()
    assert candidate.read_bytes() == b'candidate\n'
