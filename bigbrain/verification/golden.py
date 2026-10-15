"""Golden corpus — reference cases for regression-testing the harness.

Each case is a known-good request/code/output triple, independent of any
LLM. The corpus is executed through the same clean subprocess as replay
(:func:`~bigbrain.verification.executors.run_code`), so a regression in
the execution machinery (env stripping, encoding, timeouts, stdin
handling) fails a golden case even when every unit test still passes.

Usage: ``bigbrain/verification/golden.py`` is import-only; run the
corpus from tests or a future scheduled job via :func:`run_corpus`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .executors import run_code


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    user_request: str
    code: str
    expected_stdout: str


HELLO = GoldenCase(
    case_id="hello",
    user_request="crée un script hello.py qui affiche Hello, World!",
    code="print('Hello, World!')",
    expected_stdout="Hello, World!\n",
)

FIBONACCI = GoldenCase(
    case_id="fibonacci",
    user_request="calcule les 10 premiers nombres de fibonacci",
    code="\n".join([
        "a, b = 0, 1",
        "for _ in range(10):",
        "    print(a)",
        "    a, b = b, a + b",
    ]),
    expected_stdout="\n".join(str(n) for n in
                              [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]) + "\n",
)

FILE_IO = GoldenCase(
    case_id="file_io",
    user_request="écris puis relis un fichier data.txt",
    code="\n".join([
        "with open('data.txt', 'w', encoding='utf-8') as f:",
        "    f.write('bigbrain')",
        "with open('data.txt', encoding='utf-8') as f:",
        "    print(f.read())",
    ]),
    expected_stdout="bigbrain\n",
)

UNICODE = GoldenCase(
    case_id="unicode",
    user_request="affiche des caractères accentués et un emoji",
    code="print('héllo wörld ✓ 🧠')",
    expected_stdout="héllo wörld ✓ 🧠\n",
)

GOLDEN_CASES: tuple[GoldenCase, ...] = (HELLO, FIBONACCI, FILE_IO, UNICODE)


async def check_case(case: GoldenCase, *, timeout: float = 15.0) -> dict[str, Any]:
    """Run one golden case; the output must match byte for byte."""
    execution = await run_code(case.code, timeout=timeout)
    passed = (
        execution["exit_code"] == 0
        and not execution["timed_out"]
        and execution["stdout"] == case.expected_stdout
    )
    return {
        "case": case.case_id,
        "passed": passed,
        "exit_code": execution["exit_code"],
        "stdout": execution["stdout"],
        "expected": case.expected_stdout,
        "stderr": execution["stderr"],
    }


async def run_corpus(cases: tuple[GoldenCase, ...] = GOLDEN_CASES,
                     *, timeout: float = 15.0) -> dict[str, Any]:
    """Run every golden case; one summary, details per case."""
    results = [await check_case(case, timeout=timeout) for case in cases]
    return {
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "results": results,
    }
