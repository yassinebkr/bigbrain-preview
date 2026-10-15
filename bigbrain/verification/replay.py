"""Replay of recorded runs from their manifest (harness P3).

A replay re-executes the code artifact of a TERMINAL run in a clean
subprocess (same input bytes → compare output bytes) and reports whether
the run was deterministic. The replay itself is recorded as a new
manifest chained to the original via ``parent_run_id`` — evidence all
the way down.

What replay compares:
* stdout bytes, stderr bytes, exit code — hash equality per field.
* A single mismatch marks the run non-deterministic; the details carry
  exactly which fields differed.

What replay deliberately does NOT do: re-run the contracts stage against
the live workspace (the file may have legitimately changed since), and
re-run the tests stage (tests validate code under test conditions, not
run determinism). The replay manifest's stages are the fresh execution
plus a dedicated ``replay_compare`` stage.
"""

from __future__ import annotations

from typing import Any

from .evidence import (
    EvidenceRepository,
    RunManifest,
    StageResult,
    default_repository,
)
from .executors import run_code, stage_compile, stage_run, stage_syntax


class ReplayError(ValueError):
    """Raised when a run cannot be replayed."""


def _artifact_of(repository: EvidenceRepository, hashes: list[str]) -> bytes:
    for digest in hashes:
        content = repository.get_artifact(digest)
        if content is not None:
            return content
    return b""


async def replay_run(run_id: str, repository: EvidenceRepository | None = None,
                      *, timeout: float = 30.0) -> dict[str, Any]:
    """Re-execute a recorded run and compare against its artifacts.

    Returns a report dict::

        {original_run_id, replay_run_id, deterministic, mismatches: [...]}

    The replay is persisted as a new terminal manifest chained to the
    original (``parent_run_id``), with ``metadata.replay_of`` set.
    """
    repository = repository or default_repository()
    manifest = repository.load_manifest(run_id)
    if manifest is None:
        raise ReplayError(f"unknown run: {run_id}")
    if not manifest.terminal:
        raise ReplayError("only terminal runs can be replayed")

    code_hash = next(
        (digest for stage in manifest.stages if stage.name == "syntax"
         for digest in stage.artifact_hashes),
        None,
    )
    if code_hash is None:
        raise ReplayError("manifest carries no code artifact")
    code = _artifact_of(repository, [code_hash]).decode("utf-8", errors="replace")

    run_stage = next((s for s in manifest.stages if s.name == "run"), None)
    recorded_stdout = _artifact_of(
        repository, run_stage.artifact_hashes[:1] if run_stage else [])
    recorded_stderr = _artifact_of(
        repository, run_stage.artifact_hashes[1:] if run_stage else [])
    recorded_exit = (run_stage.details.get("exit_code") if run_stage else None)

    fresh = await run_code(code, timeout=timeout)

    mismatches: list[str] = []
    if fresh["stdout"].encode("utf-8") != recorded_stdout:
        mismatches.append("stdout")
    if fresh["stderr"].encode("utf-8") != recorded_stderr:
        mismatches.append("stderr")
    if fresh["exit_code"] != recorded_exit:
        mismatches.append("exit_code")
    deterministic = not mismatches

    # Persist the replay as its own chained manifest.
    code_ref = repository.put_artifact(
        code.encode("utf-8"), name="replay.py", media_type="text/x-python")
    stdout_ref = repository.put_artifact(
        fresh["stdout"].encode("utf-8"), name="replay.py.stdout",
        media_type="text/plain")
    stderr_ref = repository.put_artifact(
        fresh["stderr"].encode("utf-8"), name="replay.py.stderr",
        media_type="text/plain")

    syntax = stage_syntax(code, filename="replay.py")
    syntax.artifact_hashes = [code_ref.sha256]
    compile_stage = stage_compile(code, filename="replay.py")
    compile_stage.artifact_hashes = [code_ref.sha256]
    fresh_run = stage_run(fresh)
    fresh_run.artifact_hashes = [stdout_ref.sha256, stderr_ref.sha256]
    compare = StageResult(
        name="replay_compare", status="passed" if deterministic else "failed",
        tool="sha256", details={"mismatches": mismatches},
    )

    provisional = RunManifest(
        design_id=manifest.design_id,
        design_revision=manifest.design_revision,
        spec_sha256=manifest.spec_sha256,
        stages=[syntax, compile_stage, fresh_run, compare],
        artifacts=[code_ref, stdout_ref, stderr_ref],
    )
    verdict = provisional.verdict
    status = {"passed": "completed", "failed": "failed",
              "inconclusive": "inconclusive"}[verdict]
    replay_manifest = RunManifest.model_validate({
        **provisional.model_dump(mode="json"),
        "status": status,
        "completed_at": provisional.created_at.isoformat(),
        "parent_run_id": manifest.run_id,
        "metadata": {
            "replay_of": manifest.run_id,
            "deterministic": deterministic,
            "mismatches": mismatches,
        },
    })
    repository.save_manifest(replay_manifest)

    return {
        "original_run_id": manifest.run_id,
        "replay_run_id": replay_manifest.run_id,
        "deterministic": deterministic,
        "mismatches": mismatches,
        "exit_code": fresh["exit_code"],
    }
