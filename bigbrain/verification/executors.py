"""Deterministic verification stages for Python code runs (harness P2).

Each stage is a pure, individually-testable check that returns a
:class:`~bigbrain.verification.evidence.StageResult`. Ported from the
fpga backend's split between *what to verify* (policy) and *how*
(executor), reduced to the Python domain:

* :func:`stage_syntax`  — ast.parse. Always run; free.
* :func:`stage_compile` — byte-compilation via the ``compile`` builtin.
* :func:`stage_run`     — verdict over an ALREADY HAPPENED execution
  (the Honk loop's subprocess result); the gate never re-executes code
  just to judge it.
* :func:`stage_tests`   — pytest over the work_dir when test files
  exist; absent tests are ``not_applicable`` (never a disguised pass),
  a missing pytest is ``inconclusive``.
* :func:`stage_contracts` — every file named by the request or architect
  project plan exists in the working project.

Stages never raise for a bad script: a failure IS the result. Only
programming errors in the stage itself propagate.
"""

from __future__ import annotations

import ast
import json
import asyncio
import importlib.util
import os
import platform
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Mapping

from .evidence import StageResult

# The filename a request asks for ("crée un script hello.py" → hello.py).
REQUESTED_FILE_RE = re.compile(
    r"[\w][\w.-]*\.(?:py|json|csv|txt|md|toml|yaml|yml)"
)

_PY = platform.python_version()


def extract_requested_file(user_request: str) -> str | None:
    """The file name the request mentions, if any."""
    match = REQUESTED_FILE_RE.search(user_request or "")
    return match.group(0) if match else None


async def run_code(code: str, *, timeout: float = 30.0,
                   cwd: Path | None = None,
                   filename: str = "replay.py") -> dict[str, Any]:
    """Execute code in a clean, side-effect-free subprocess.

    Used by replay and the golden corpus: minimal environment (deterministic
    locale/encoding, no secrets), stdin wired to /dev/null so ``input()``
    returns EOF instead of hanging, and a scratch directory unless ``cwd``
    is given. Returns the same shape as the brain's execution result.
    """
    work_dir = Path(cwd) if cwd is not None else Path(
        tempfile.mkdtemp(prefix="bigbrain-replay-"))
    script = work_dir / filename
    script.write_text(code, encoding="utf-8")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(work_dir),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(script),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL,
        cwd=str(work_dir),
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return {
            "stdout": "", "stderr": f"execution timed out after {timeout:.0f}s",
            "exit_code": -1, "timed_out": True,
        }
    if cwd is None:
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
    return {
        "stdout": stdout.decode(errors="replace"),
        "stderr": stderr.decode(errors="replace"),
        "exit_code": process.returncode,
        "timed_out": False,
    }


def stage_syntax(code: str, *, filename: str = "<generated>") -> StageResult:
    """AST parse — the cheapest possible rejection of broken code."""
    try:
        ast.parse(code, filename=filename)
    except SyntaxError as exc:
        return StageResult(
            name="syntax", status="failed", tool="ast.parse", tool_version=_PY,
            details={
                "error": exc.msg,
                "line": exc.lineno,
                "offset": exc.offset,
                "filename": filename,
            },
        )
    return StageResult(
        name="syntax", status="passed", tool="ast.parse", tool_version=_PY,
        details={"filename": filename},
    )


def stage_compile(code: str, *, filename: str = "<generated>") -> StageResult:
    """Byte-compilation — catches what ast.parse lets through rarely."""
    try:
        compile(code, filename, "exec")
    except SyntaxError as exc:
        return StageResult(
            name="compile", status="failed", tool="compile", tool_version=_PY,
            details={"error": exc.msg, "line": exc.lineno, "filename": filename},
        )
    return StageResult(
        name="compile", status="passed", tool="compile", tool_version=_PY,
        details={"filename": filename},
    )


def stage_run(execution: Mapping[str, Any]) -> StageResult:
    """Verdict over an execution that already happened.

    The gate does not re-run code: the Honk loop executed it and the
    result dict (exit_code / stderr / timed_out) is the evidence.
    """
    exit_code = execution.get("exit_code")
    timed_out = bool(execution.get("timed_out"))
    stderr = str(execution.get("stderr") or "")
    status = "passed" if (exit_code == 0 and not timed_out) else "failed"
    details: dict[str, Any] = {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stderr_chars": len(stderr),
    }
    if timed_out:
        details["error"] = "execution timed out"
    elif exit_code != 0:
        details["error"] = stderr.strip().splitlines()[-1] if stderr.strip() else f"exit code {exit_code}"
    return StageResult(name="run", status=status,
                       tool="subprocess", tool_version=_PY, details=details)


_PYTEST_REPORTER = '''
import json, sys, pytest
reports = []
class Recorder:
    def pytest_runtest_logreport(self, report):
        reports.append({"nodeid": report.nodeid, "phase": report.when, "outcome": report.outcome})
result = pytest.main(sys.argv[2:], plugins=[Recorder()])
with open(sys.argv[1], "w", encoding="utf-8") as stream:
    json.dump(reports, stream)
raise SystemExit(result)
'''


async def _pytest_with_report(interpreter, work_dir, test_files, env):
    """Structured pytest hooks, not status-like text printed by generated code."""
    import signal
    with tempfile.TemporaryDirectory(prefix='bigbrain-test-report-') as scratch:
        report = Path(scratch) / 'report.json'
        process = await asyncio.create_subprocess_exec(interpreter, '-c', _PYTEST_REPORTER, str(report),
            '-q', '--no-header', '-p', 'no:cacheprovider', *[str(p.relative_to(work_dir)) for p in test_files],
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL, env=env, cwd=str(work_dir), start_new_session=(os.name == 'posix'))
        try:
            # Generated tests can print without limit. Bound collection itself,
            # not just the diagnostic after an unbounded communicate().
            chunks, size = [], 0
            while chunk := await process.stdout.read(65536):
                size += len(chunk)
                if size > 2_000_000:
                    return b''.join(chunks), None, None
                chunks.append(chunk)
            await process.wait()
            stdout = b''.join(chunks)
            records = json.loads(report.read_text()) if report.is_file() and report.stat().st_size <= 2_000_000 else None
            return stdout, process.returncode, records
        finally:
            if os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif process.returncode is None:
                process.kill()
            await process.wait()


async def stage_tests(work_dir: Path, *, timeout: float = 60.0, python: str | Path | None = None) -> StageResult:
    """pytest over the work_dir — honest about what was NOT tested.

    * no test files     → ``not_applicable`` (not a pass, not a block)
    * pytest missing    → ``inconclusive`` (never a disguised pass)
    * tests ran         → ``passed`` / ``failed`` on the exit code
    * run exceeded time → ``inconclusive``
    """
    test_files = sorted({
        p for pattern in ("test_*.py", "*_test.py")
        for p in work_dir.rglob(pattern)
        if not any(part in {".venv", "venv", ".git", "node_modules"}
                   for part in p.relative_to(work_dir).parts)
    })
    if not test_files:
        return StageResult(
            name="tests", status="not_applicable", tool="pytest",
            details={"reason": "no test files in work_dir", 'cause': 'missing_test',
                     'next_action': 'extend_validation'},
        )
    interpreter = str(python) if python is not None else sys.executable
    env = {'PATH': str(Path(interpreter).parent) + os.pathsep + os.environ.get('PATH', ''),
           'HOME': str(work_dir), 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
           'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1'}
    try:
        probe = await asyncio.create_subprocess_exec(interpreter, '-c',
            'import importlib.util,json,sys; print(json.dumps({"python":sys.executable,"prefix":sys.prefix,"version":sys.version.split()[0],"pytest":importlib.util.find_spec("pytest") is not None}))',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL, env=env, cwd=str(work_dir))
        out, _ = await asyncio.wait_for(probe.communicate(), timeout=min(timeout, 10))
        environment = json.loads(out) if probe.returncode == 0 else {}
    except (OSError, ValueError, asyncio.TimeoutError):
        if 'probe' in locals() and probe.returncode is None:
            probe.kill()
            await probe.wait()
        environment = {}
    expected_venv = Path(interpreter).parent.parent
    if expected_venv.name == '.venv' and environment and Path(environment.get('prefix', '')).resolve() != expected_venv.resolve():
        return StageResult(name='tests', status='inconclusive', tool='pytest',
            details={'reason': 'Project interpreter is not running in its declared venv; no host fallback',
                     'cause': 'environment_blocked', 'next_action': 'stop',
                     'interpreter': interpreter, 'environment': environment})
    if not environment.get('pytest'):
        return StageResult(
            name="tests", status="inconclusive", tool="pytest",
            details={"reason": "project Python or pytest unavailable; no host fallback", "interpreter": interpreter,
                     'cause': 'environment_blocked', 'next_action': 'stop',
                     "environment": environment},
        )
    try:
        stdout, returncode, records = await asyncio.wait_for(
            _pytest_with_report(interpreter, work_dir, test_files, env), timeout=timeout)
    except asyncio.TimeoutError:
        return StageResult(
            name="tests", status="inconclusive", tool="pytest",
            details={"reason": f"test run exceeded {timeout:.0f}s"},
        )
    output = stdout.decode(errors="replace")
    # Keep actionable failures, not just the final traceback. Bound the
    # diagnostic explicitly; large logs remain honestly marked incomplete.
    valid_records = isinstance(records, list) and all(isinstance(item, dict) and isinstance(item.get('nodeid'), str)
        and item.get('outcome') in {'passed', 'failed', 'skipped'} and item.get('phase') in {'setup', 'call', 'teardown'} for item in records)
    failed_cases = sorted({item['nodeid'] for item in records if item['outcome'] == 'failed'}) if valid_records else []
    status = ('inconclusive' if returncode is None else
              'passed' if returncode == 0 and valid_records else 'failed' if returncode != 0 else 'inconclusive')
    return StageResult(
        name="tests", status=status, tool="pytest", tool_version=environment['version'],
        details={
            **({'reason': 'Test output exceeded 2000000-byte execution budget; process group terminated'} if returncode is None else {}),
            "environment": environment,
            "returncode": returncode,
            "tests": [str(p.relative_to(work_dir)) for p in test_files],
            "output_tail": output[-2000:],
            "diagnostic_output": output if len(output) <= 64000 else output[:32000] + '\n[diagnostic truncated]\n' + output[-32000:],
            "diagnostic_truncated": len(output) > 64000,
            "failed_cases": failed_cases[:100],
            "passed_cases": sorted({item['nodeid'] for item in records if item['phase'] == 'call' and item['outcome'] == 'passed'}) if valid_records else [],
            "structured_report_valid": valid_records,
        },
    )


def stage_contracts(
    work_dir: Path,
    requested_file: str | Sequence[str] | None,
    *,
    persisted_file: str | Sequence[str] | None = None,
) -> StageResult:
    """Verify that every file named by the request or project plan exists."""
    requested = ([requested_file] if isinstance(requested_file, str)
                 else list(requested_file or []))
    persisted = ([persisted_file] if isinstance(persisted_file, str)
                 else list(persisted_file or []))
    if not requested:
        return StageResult(
            name="contracts", status="not_applicable", tool="pathlib",
            details={"reason": "request names no file"},
        )

    present = []
    missing = []
    for path in requested:
        target = work_dir / path
        if target.is_file():
            present.append({"path": path, "size_bytes": target.stat().st_size})
        else:
            missing.append(path)

    if not missing:
        return StageResult(
            name="contracts", status="passed", tool="pathlib",
            details={
                "files": present,
                "file": requested[0] if len(requested) == 1 else None,
                "size_bytes": present[0]["size_bytes"] if len(present) == 1 else None,
                "persisted_as": persisted[0] if len(persisted) == 1 else persisted,
            },
        )
    return StageResult(
        name="contracts", status="failed", tool="pathlib",
        details={
            "expected": requested[0] if len(requested) == 1 else requested,
            "missing": missing,
            "present": [item["path"] for item in present],
            "reason": "requested project files missing from the working project",
        },
    )
