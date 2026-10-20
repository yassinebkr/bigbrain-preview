"""Read-only, bounded context for one pinned execution target.

Not a secret scanner guarantee or an OS sandbox for generated programs.
Source is data for the configured LLM, never runtime instructions.
"""
import hashlib
import os
import re
import stat
from contextlib import ExitStack
from pathlib import Path

from .execution_target import relative_path

MAX_FILE_BYTES = 48_000
MAX_TOTAL_BYTES = 128_000
MAX_FILES = 64
EXTENSIONS = {'.py', '.md', '.txt', '.json', '.js', '.jsx', '.ts', '.tsx', '.css', '.html', '.toml'}
SKIP_DIRS = {'node_modules', 'venv', '__pycache__', 'dist', 'build'}
SENSITIVE_NAME = re.compile(r'(secret|credential|password|private.?key|token)', re.I)
SENSITIVE_TEXT = re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:api[_-]?key|access[_-]?token|password)\s*[=:]\s*[\"\'][^\"\'\n]{8,}[\"\']', re.I)


def digest(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def read_source(target, path: str, limit=MAX_FILE_BYTES) -> tuple[str, bool]:
    """No-follow descriptor walk; a symlink parent cannot redirect this read."""
    relative_path(path)
    parts = Path(path).parts
    if any(part.startswith('.') for part in parts):
        raise ValueError('Hidden project source is not readable')
    target.validate()
    with ExitStack() as stack:
        fd = os.open(target.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, fd)
        identity = os.fstat(fd)
        if target.inode is not None and (identity.st_dev, identity.st_ino) != (target.device, target.inode):
            raise ValueError('Project changed before inspection')
        for part in parts[:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            stack.callback(os.close, fd)
        source = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        stack.callback(os.close, source)
        before = os.fstat(source)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('Project source must be a regular file')
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(source, min(8192, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(source)
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Source changed during inspection')
        complete = len(raw) <= limit
        content = bytes(raw[:limit]).decode('utf-8', errors='strict' if complete else 'ignore')
        if '\x00' in content:
            raise ValueError('Binary source excluded')
    target.validate()
    return content, complete


def inspect_project(target) -> dict:
    target.validate()
    sources, inventory = {}, []
    remaining, limited, directories = MAX_TOTAL_BYTES, False, 0
    for directory, dirs, names in os.walk(target.directory, followlinks=False):
        directories += 1
        if directories > 128:
            limited = True
            break
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in SKIP_DIRS
                         and not SENSITIVE_NAME.search(d) and not (Path(directory) / d).is_symlink())
        for name in sorted(names):
            if len(inventory) >= MAX_FILES:
                limited = True
                break
            path = (Path(directory) / name).relative_to(target.directory).as_posix()
            entry = {'path': path}
            inventory.append(entry)
            if name.startswith('.') or SENSITIVE_NAME.search(name) or Path(name).suffix.lower() not in EXTENSIONS:
                entry['status'] = 'excluded'
                continue
            if not remaining:
                entry['status'] = 'budget_exceeded'
                limited = True
                continue
            try:
                text, complete = read_source(target, path, min(MAX_FILE_BYTES, remaining))
                remaining -= len(text.encode('utf-8'))
                if SENSITIVE_TEXT.search(text):
                    entry['status'] = 'sensitive_content_excluded'
                    continue
                sources[path] = {'content': text, 'complete': complete,
                                 'sha256': digest(text) if complete else None}
                if complete:
                    entry['sha256'] = sources[path]['sha256']
                entry['status'] = 'read' if complete else 'truncated'
                limited |= not complete
            except (OSError, ValueError, UnicodeError):
                entry['status'] = 'unreadable'
        if len(inventory) >= MAX_FILES:
            limited = True
            break
    target.validate()
    return {'path': target.path, 'sources': sources, 'inventory': inventory,
            'limited': limited, 'limits': {'files': MAX_FILES, 'file_bytes': MAX_FILE_BYTES, 'total_bytes': MAX_TOTAL_BYTES}}


async def diagnose_project(target, inspection):
    """Baseline on the inspected revision, before any implementation edits.

    Tests execute project code (same trust boundary as the existing runner),
    not an OS sandbox. Never run an arbitrary entry point with guessed args.
    """
    import ast
    from .verification.executors import stage_tests
    versions = {path: source['sha256'] for path, source in inspection['sources'].items()
                if source['complete']}
    syntax = []
    for path, source in inspection['sources'].items():
        if path.endswith('.py') and source['complete']:
            try:
                ast.parse(source['content'], filename=path)
            except SyntaxError as exc:
                syntax.append({'path': path, 'line': exc.lineno, 'error': exc.msg})
    tests = await stage_tests(target.directory, timeout=30,
                              python=target.directory / '.venv' / 'bin' / 'python')
    # A test may itself mutate a source: don't plan from a stale snapshot.
    for path, version in versions.items():
        content, complete = read_source(target, path)
        if not complete or digest(content) != version:
            raise ValueError(f'{path}: source changed during baseline diagnosis')
    return {'source_versions': versions, 'syntax_errors': syntax,
            'tests': {'status': tests.status, **tests.details},
            'execution': 'tests only; entry point not invoked',
            'limited_inspection': inspection['limited']}
