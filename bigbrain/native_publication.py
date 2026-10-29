"""Native preservation primitives used by the shared publication journal.

Callers authorize project scope and persist intent before invoking an operation.
Every error requires inspection of recorded paths, since native replacement and
durability failures can leave recoverable intermediate states.
"""

from contextlib import ExitStack, contextmanager
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


def _operands(*paths):
    values = tuple(Path(path).absolute() for path in paths)
    if any('..' in path.parts or not path.name or path.name in {'.', '..'} for path in values):
        raise ValueError('Publication requires explicit file paths')
    if len(set(values)) != len(values):
        raise ValueError('Publication operands must be distinct')
    return values


class LinuxPublication:
    """Descriptor-relative exchange and destination-exclusive rename."""

    platform = 'linux'

    def __init__(self):
        library = ctypes.CDLL(None, use_errno=True)
        try:
            self._renameat2 = library.renameat2
        except AttributeError as exc:
            raise OSError(errno.ENOSYS, 'Recoverable publication requires renameat2') from exc
        self._renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                                   ctypes.c_char_p, ctypes.c_uint]
        self._renameat2.restype = ctypes.c_int

    @contextmanager
    def _directory(self, path, anchors=None):
        with ExitStack() as stack:
            descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
            stack.callback(os.close, descriptor)
            current = Path('/')
            for part in path.parts[1:]:
                current /= part
                descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                     dir_fd=descriptor)
                stack.callback(os.close, descriptor)
                info = os.fstat(descriptor)
                expected = (anchors or {}).get(str(current))
                if expected is not None and tuple(expected) != (info.st_dev, info.st_ino):
                    raise OSError(errno.ESTALE, 'Publication directory identity changed', str(current))
            yield descriptor

    def directory_identity(self, path):
        with self._directory(Path(path).absolute()) as descriptor:
            info = os.fstat(descriptor)
            return [info.st_dev, info.st_ino]

    def preservation_path(self, candidate):
        # Exchange retains the displaced live object at the candidate's old name.
        return Path(candidate).absolute()

    def _rename(self, source, destination, flags, anchors=None):
        source, destination = _operands(source, destination)
        with self._directory(source.parent, anchors) as source_fd, self._directory(destination.parent, anchors) as dest_fd:
            if self._renameat2(source_fd, os.fsencode(source.name), dest_fd,
                               os.fsencode(destination.name), flags):
                number = ctypes.get_errno()
                raise OSError(number, os.strerror(number), str(destination))
            # Flush errors occur after mutation; the journal reconciles both names.
            os.fsync(source_fd)
            os.fsync(dest_fd)

    def replace_preserving(self, destination, candidate, preserved, *, anchors=None):
        if Path(preserved).absolute() != self.preservation_path(candidate):
            raise ValueError('Linux exchange preserves the original at the candidate path')
        self._rename(candidate, destination, 2, anchors)  # RENAME_EXCHANGE

    def create(self, destination, candidate, *, anchors=None):
        self._rename(candidate, destination, 1, anchors)  # RENAME_NOREPLACE

    def retire(self, destination, preserved, *, anchors=None):
        self._rename(destination, preserved, 1, anchors)

    def release_preserved(self, path, expected, *, anchors=None):
        """Delete an inspected private artifact through an isolated lease holder."""
        request = json.dumps({'path': str(Path(path).absolute()), 'expected': expected,
                              'anchors': anchors or {}})
        try:
            result = subprocess.run([sys.executable, '-I', __file__, '--release-linux'],
                input=request, text=True, capture_output=True, timeout=8)
        except subprocess.TimeoutExpired as error:
            raise OSError(errno.ETIMEDOUT, 'Retained release helper exceeded its time limit') from error
        if result.returncode:
            raise OSError(errno.EBUSY, 'Retained release refused: ' + result.stdout.strip()[:500])


class WindowsPublication:
    """Replacement with backup and destination-exclusive same-volume moves."""

    platform = 'win32'

    def __init__(self):
        from ctypes import wintypes
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        self.api.CreateFileW.restype = wintypes.HANDLE
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.api.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        self.api.GetFileInformationByHandle.restype = wintypes.BOOL
        self.api.ReplaceFileW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR,
            wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
        self.api.ReplaceFileW.restype = wintypes.BOOL
        self.api.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        self.api.MoveFileExW.restype = wintypes.BOOL
        self.api.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                     ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        self.api.ReadFile.restype = wintypes.BOOL
        self.api.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                       ctypes.c_void_p, wintypes.DWORD]
        self.api.SetFileInformationByHandle.restype = wintypes.BOOL

        class FileInformation(ctypes.Structure):
            _fields_ = [('attributes', wintypes.DWORD), ('created', wintypes.FILETIME),
                ('accessed', wintypes.FILETIME), ('written', wintypes.FILETIME),
                ('volume', wintypes.DWORD), ('size_high', wintypes.DWORD),
                ('size_low', wintypes.DWORD), ('links', wintypes.DWORD),
                ('index_high', wintypes.DWORD), ('index_low', wintypes.DWORD)]
        self._information = FileInformation

    @contextmanager
    def _directory(self, path, anchors=None):
        # Hold each ancestor against rename/removal and inspect its opened object.
        if str(path).startswith('\\\\') or not path.drive:
            raise OSError(errno.ENOTSUP, 'Publication requires a qualified local Windows volume')
        with ExitStack() as stack:
            for length in range(1, len(path.parts) + 1):
                current = Path(*path.parts[:length])
                handle = self.api.CreateFileW(str(current), 0x80, 0x1 | 0x2,
                    None, 3, 0x02000000 | 0x00200000, None)
                if handle == ctypes.c_void_p(-1).value:
                    raise ctypes.WinError(ctypes.get_last_error())
                stack.callback(self.api.CloseHandle, handle)
                info = self._information()
                if not self.api.GetFileInformationByHandle(handle, ctypes.byref(info)):
                    raise ctypes.WinError(ctypes.get_last_error())
                if info.attributes & 0x400 or not info.attributes & 0x10:
                    raise OSError(errno.ELOOP, 'Publication directory has a reparse point or changed type')
                identity = [info.volume, (info.index_high << 32) | info.index_low]
                expected = (anchors or {}).get(str(current))
                if expected is not None and list(expected) != identity:
                    raise OSError(errno.ESTALE, 'Publication directory identity changed', str(current))
            yield identity

    def directory_identity(self, path):
        with self._directory(Path(path).absolute()) as identity:
            return identity

    def preservation_path(self, candidate):
        candidate = Path(candidate).absolute()
        return candidate.with_name(candidate.name + '.displaced')

    def replace_preserving(self, destination, candidate, preserved, *, anchors=None):
        destination, candidate, preserved = _operands(destination, candidate, preserved)
        if preserved != self.preservation_path(candidate):
            raise ValueError('Windows replacement requires its reserved backup path')
        with ExitStack() as stack:
            for parent in sorted({destination.parent, candidate.parent, preserved.parent}):
                stack.enter_context(self._directory(parent, anchors))
            if preserved.exists() or preserved.is_symlink():
                raise FileExistsError(errno.EEXIST, 'Preservation path is occupied', str(preserved))
            # The journal reserves an operation-private recovery namespace first.
            if not self.api.ReplaceFileW(str(destination), str(candidate), str(preserved), 0, None, None):
                raise ctypes.WinError(ctypes.get_last_error())

    def _move(self, source, destination, anchors=None):
        source, destination = _operands(source, destination)
        with self._directory(source.parent, anchors), self._directory(destination.parent, anchors):
            # Flags zero require same-volume movement and refuse an existing name.
            if not self.api.MoveFileExW(str(source), str(destination), 0):
                raise ctypes.WinError(ctypes.get_last_error())

    def create(self, destination, candidate, *, anchors=None):
        self._move(candidate, destination, anchors)

    def retire(self, destination, preserved, *, anchors=None):
        self._move(destination, preserved, anchors)

    def release_preserved(self, path, expected, *, anchors=None):
        """Check and delete the same exclusively held Windows file object."""
        from ctypes import wintypes
        path = Path(path).absolute()
        with self._directory(path.parent, anchors):
            handle = self.api.CreateFileW(str(path), 0x80000000 | 0x10000, 0,
                                         None, 3, 0x00200000, None)
            if handle == ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                info = self._information()
                if not self.api.GetFileInformationByHandle(handle, ctypes.byref(info)):
                    raise ctypes.WinError(ctypes.get_last_error())
                identity = [info.volume, (info.index_high << 32) | info.index_low]
                if info.attributes & (0x400 | 0x10) or info.links != 1:
                    raise ValueError('Release requires a regular single-link artifact')
                size = (info.size_high << 32) | info.size_low
                if size > 4_000_000:
                    raise ValueError('Retained artifact exceeds release limit')
                digest, total = hashlib.sha256(), 0
                buffer, count = ctypes.create_string_buffer(65536), wintypes.DWORD()
                while True:
                    if not self.api.ReadFile(handle, buffer, len(buffer), ctypes.byref(count), None):
                        raise ctypes.WinError(ctypes.get_last_error())
                    if count.value == 0:
                        break
                    total += count.value
                    digest.update(buffer.raw[:count.value])
                if identity != expected['identity'] or digest.hexdigest() != expected['version'] or total != size:
                    raise ValueError('Retained version changed before release')
                disposition = ctypes.c_ubyte(1)  # FILE_DISPOSITION_INFO.DeleteFile is BOOLEAN.
                if not self.api.SetFileInformationByHandle(handle, 4, ctypes.byref(disposition),
                                                           ctypes.sizeof(disposition)):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                self.api.CloseHandle(handle)


def publication_backend():
    """Select a native implementation and fail explicitly on unsupported hosts."""
    if sys.platform == 'linux':
        return LinuxPublication()
    if sys.platform == 'win32':
        return WindowsPublication()
    raise OSError(errno.ENOTSUP, 'Recoverable publication supports Linux and Windows')


def _linux_release(request):
    """Hold a kernel write lease through verification and unlink in a helper."""
    import fcntl
    import signal
    # Lease-break notifications remain confined to this short-lived helper.
    signal.signal(signal.SIGIO, signal.SIG_IGN)
    path, expected = Path(request['path']), request['expected']
    backend = LinuxPublication()
    with backend._directory(path.parent, request['anchors']) as parent:
        descriptor = os.open(path.name, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            fcntl.fcntl(descriptor, fcntl.F_SETLEASE, fcntl.F_WRLCK)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 4_000_000:
                raise ValueError('Release requires a bounded regular single-link artifact')
            digest, total = hashlib.sha256(), 0
            while data := os.read(descriptor, 65536):
                total += len(data)
                if total > 4_000_000:
                    raise ValueError('Retained artifact exceeds release limit')
                digest.update(data)
            identity = [info.st_dev, info.st_ino]
            current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            if (identity != expected['identity'] or digest.hexdigest() != expected['version']
                    or (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino)
                    or fcntl.fcntl(descriptor, fcntl.F_GETLEASE) != fcntl.F_WRLCK):
                raise ValueError('Retained version changed or opened before release')
            os.unlink(path.name, dir_fd=parent)
            os.fsync(parent)
        finally:
            os.close(descriptor)


if __name__ == '__main__' and sys.argv[1:] == ['--release-linux']:
    try:
        _linux_release(json.loads(sys.stdin.read(65536)))
    except Exception as error:
        print(f'{type(error).__name__}: {error}')
        sys.exit(1)
