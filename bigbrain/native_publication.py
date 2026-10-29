"""Native preservation primitives used by the shared publication journal.

Callers authorize project scope and persist intent before invoking an operation.
Every error requires inspection of recorded paths, since native replacement and
durability failures can leave recoverable intermediate states.
"""

from contextlib import ExitStack, contextmanager
import ctypes
import errno
import os
from pathlib import Path
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
    def _directory(self, path):
        with ExitStack() as stack:
            descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
            stack.callback(os.close, descriptor)
            for part in path.parts[1:]:
                descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                     dir_fd=descriptor)
                stack.callback(os.close, descriptor)
            yield descriptor

    def preservation_path(self, candidate):
        # Exchange retains the displaced live object at the candidate's old name.
        return Path(candidate).absolute()

    def _rename(self, source, destination, flags):
        source, destination = _operands(source, destination)
        with self._directory(source.parent) as source_fd, self._directory(destination.parent) as dest_fd:
            if self._renameat2(source_fd, os.fsencode(source.name), dest_fd,
                               os.fsencode(destination.name), flags):
                number = ctypes.get_errno()
                raise OSError(number, os.strerror(number), str(destination))
            # Flush errors occur after mutation; the journal reconciles both names.
            os.fsync(source_fd)
            os.fsync(dest_fd)

    def replace_preserving(self, destination, candidate, preserved):
        if Path(preserved).absolute() != self.preservation_path(candidate):
            raise ValueError('Linux exchange preserves the original at the candidate path')
        self._rename(candidate, destination, 2)  # RENAME_EXCHANGE

    def create(self, destination, candidate):
        self._rename(candidate, destination, 1)  # RENAME_NOREPLACE

    def retire(self, destination, preserved):
        self._rename(destination, preserved, 1)


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

        class FileInformation(ctypes.Structure):
            _fields_ = [('attributes', wintypes.DWORD), ('created', wintypes.FILETIME),
                ('accessed', wintypes.FILETIME), ('written', wintypes.FILETIME),
                ('volume', wintypes.DWORD), ('size_high', wintypes.DWORD),
                ('size_low', wintypes.DWORD), ('links', wintypes.DWORD),
                ('index_high', wintypes.DWORD), ('index_low', wintypes.DWORD)]
        self._information = FileInformation

    @contextmanager
    def _directory(self, path):
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
            yield

    def preservation_path(self, candidate):
        candidate = Path(candidate).absolute()
        return candidate.with_name(candidate.name + '.displaced')

    def replace_preserving(self, destination, candidate, preserved):
        destination, candidate, preserved = _operands(destination, candidate, preserved)
        if preserved != self.preservation_path(candidate):
            raise ValueError('Windows replacement requires its reserved backup path')
        with ExitStack() as stack:
            for parent in sorted({destination.parent, candidate.parent, preserved.parent}):
                stack.enter_context(self._directory(parent))
            if preserved.exists() or preserved.is_symlink():
                raise FileExistsError(errno.EEXIST, 'Preservation path is occupied', str(preserved))
            # The journal reserves an operation-private recovery namespace first.
            if not self.api.ReplaceFileW(str(destination), str(candidate), str(preserved), 0, None, None):
                raise ctypes.WinError(ctypes.get_last_error())

    def _move(self, source, destination):
        source, destination = _operands(source, destination)
        with self._directory(source.parent), self._directory(destination.parent):
            # Flags zero require same-volume movement and refuse an existing name.
            if not self.api.MoveFileExW(str(source), str(destination), 0):
                raise ctypes.WinError(ctypes.get_last_error())

    def create(self, destination, candidate):
        self._move(candidate, destination)

    def retire(self, destination, preserved):
        self._move(destination, preserved)


def publication_backend():
    """Select a native implementation and fail explicitly on unsupported hosts."""
    if sys.platform == 'linux':
        return LinuxPublication()
    if sys.platform == 'win32':
        return WindowsPublication()
    raise OSError(errno.ENOTSUP, 'Recoverable publication supports Linux and Windows')
