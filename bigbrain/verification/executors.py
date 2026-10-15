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
* :func:`stage_contracts` — the file the request named ("crée un script
  hello.py") exists in the working project.

Stages never raise for a bad script: a failure IS the result. Only
programming errors in the stage itself propagate.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import os
import platform
import re
import sys
import tempfile
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


async def stage_tests(work_dir: Path, *, timeout: float = 60.0) -> StageResult:
    """pytest over the work_dir — honest about what was NOT tested.

    * no test files     → ``not_applicable`` (not a pass, not a block)
    * pytest missing    → ``inconclusive`` (never a disguised pass)
    * tests ran         → ``passed`` / ``failed`` on the exit code
    * run exceeded time → ``inconclusive``
    """
    test_files = sorted(
        {p for pattern in ("test_*.py", "*_test.py") for p in work_dir.glob(pattern)}
    )
    if not test_files:
        return StageResult(
            name="tests", status="not_applicable", tool="pytest",
            details={"reason": "no test files in work_dir"},
        )
    if importlib.util.find_spec("pytest") is None:
        return StageResult(
            name="tests", status="inconclusive", tool="pytest",
            details={"reason": "pytest is not installed"},
        )
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
        *[p.name for p in test_files],
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        cwd=str(work_dir),
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return StageResult(
            name="tests", status="inconclusive", tool="pytest",
            details={"reason": f"test run exceeded {timeout:.0f}s"},
        )
    output = stdout.decode(errors="replace")
    status = "passed" if process.returncode == 0 else "failed"
    return StageResult(
        name="tests", status=status, tool="pytest", tool_version=_PY,
        details={
            "returncode": process.returncode,
            "tests": [p.name for p in test_files],
            "output_tail": output[-2000:],
        },
    )


def stage_contracts(work_dir: Path, requested_file: str | None,
                    *, persisted_file: str | None = None) -> StageResult:
    """The file the request named exists at the expected place.

    This is the stage that catches the classic agent lie: "hello.py
    créé avec succès" while the workspace holds a different name.
    """
    if not requested_file:
        return StageResult(
            name="contracts", status="not_applicable", tool="pathlib",
            details={"reason": "request names no file"},
        )
    target = work_dir / requested_file
    if target.is_file():
        return StageResult(
            name="contracts", status="passed", tool="pathlib",
            details={"file": requested_file, "size_bytes": target.stat().st_size,
                     "persisted_as": persisted_file},
        )
    return StageResult(
        name="contracts", status="failed", tool="pathlib",
        details={
            "expected": requested_file,
            "reason": "requested file missing from the working project",
        },
    )
