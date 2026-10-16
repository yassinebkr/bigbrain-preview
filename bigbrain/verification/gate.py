"""Conservative verification gate over one Python execution attempt.

The gate turns an execution that ALREADY happened (the Honk loop's
subprocess result) into versioned evidence: stages run cheapest-first
(syntax, compile, run, contracts, tests), artifacts are content-addressed
(code, stdout, stderr, test output) and the whole attempt is persisted as
an immutable :class:`RunManifest` once terminal.

Verdict semantics (the manifest's conservative property):
* ``passed``        — every mandatory stage passed.
* ``failed``        — at least one mandatory stage failed.
* ``inconclusive``  — a mandatory stage could not produce evidence
  (e.g. test files exist but pytest is missing). NEVER a pass.

The gate records truth; the CALLER owns the action policy (the PythonBrain
decides whether an inconclusive verdict warrants a retry — the loop never
retries on environment problems the LLM cannot fix).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .evidence import (
    DesignSpec,
    EvidenceRepository,
    ImmutableRunError,
    RunManifest,
    StageResult,
    default_repository,
)
from .executors import (
    extract_requested_file,
    stage_compile,
    stage_contracts,
    stage_run,
    stage_syntax,
    stage_tests,
)

import hashlib


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunGate:
    """Evaluate and persist one attempt against its DesignSpec."""

    def __init__(self, repository: EvidenceRepository | None = None):
        self.repository = repository or default_repository()

    # -- spec ---------------------------------------------------------------

    def build_spec(self, user_request: str, requested_file: str | None) -> DesignSpec:
        design_id = "task-" + hashlib.sha256(
            user_request.encode("utf-8")).hexdigest()[:16]
        contracts = []
        if requested_file:
            contracts.append(
                f"file {requested_file} exists in the working project")
        return DesignSpec(
            design_id=design_id,
            name=user_request.strip()[:60] or "unnamed request",
            user_request=user_request,
            contracts=contracts,
        )

    # -- evaluation -----------------------------------------------------------

    async def evaluate_attempt(
        self,
        *,
        user_request: str,
        code: str,
        execution: Mapping[str, Any],
        work_dir: Path,
        requested_file: str | None = None,
        persisted_file: str | None = None,
        attempt: int = 1,
        parent_run_id: str | None = None,
        toolchain: Mapping[str, str] | None = None,
        filename: str = "generated.py",
    ) -> tuple[RunManifest, str]:
        """Run all deterministic stages, persist the manifest, return it.

        Returns ``(manifest, verdict)`` where verdict is the conservative
        derived verdict ("passed" / "failed" / "inconclusive").
        """
        if requested_file is None:
            requested_file = extract_requested_file(user_request)
        # Contract approval flow: if a spec was already proposed and
        # approved for this design, the manifest must link to THAT spec
        # (approved contracts + approval trace), not a fresh bare one.
        design_id = "task-" + hashlib.sha256(
            user_request.encode("utf-8")).hexdigest()[:16]
        approved_spec = self.repository.load_latest_spec(design_id)
        if approved_spec is not None:
            spec = approved_spec
        else:
            spec = self.build_spec(user_request, requested_file)
            try:
                self.repository.save_spec(spec)
            except ImmutableRunError:
                # Same design_id with different content — keep the stored spec;
                # the manifest still hash-links to what THIS attempt consumed.
                spec = self.repository.load_spec(spec.design_id, spec.revision) or spec

        # Artifacts first: content-addressed, deduplicated across attempts.
        code_ref = self.repository.put_artifact(
            code.encode("utf-8"), name=filename, media_type="text/x-python")
        stdout = str(execution.get("stdout") or "")
        stderr = str(execution.get("stderr") or "")
        stdout_ref = self.repository.put_artifact(
            stdout.encode("utf-8"), name=f"{filename}.stdout",
            media_type="text/plain")
        stderr_ref = self.repository.put_artifact(
            stderr.encode("utf-8"), name=f"{filename}.stderr",
            media_type="text/plain")
        artifacts = [code_ref, stdout_ref, stderr_ref]

        # Stages, cheapest first.
        syntax = stage_syntax(code, filename=filename)
        compile_stage = stage_compile(code, filename=filename)
        run_stage = stage_run(execution)
        contracts = stage_contracts(work_dir, requested_file,
                                    persisted_file=persisted_file)
        tests = await stage_tests(work_dir)

        # Attach artifacts to the stages that produced/consumed them.
        syntax.artifact_hashes = [code_ref.sha256]
        compile_stage.artifact_hashes = [code_ref.sha256]
        run_stage.artifact_hashes = [stdout_ref.sha256, stderr_ref.sha256]
        tests_output = str(tests.details.get("output_tail") or "")
        if tests.status in ("passed", "failed"):
            tests_ref = self.repository.put_artifact(
                tests_output.encode("utf-8"), name="tests.output",
                media_type="text/plain")
            artifacts.append(tests_ref)
            tests.artifact_hashes = [tests_ref.sha256]

        stages: list[StageResult] = [
            syntax, compile_stage, run_stage, contracts, tests,
        ]
        for stage in stages:
            stage.started_at = datetime.now(timezone.utc)
            stage.finished_at = datetime.now(timezone.utc)

        # Conservative verdict BEFORE choosing the terminal status.
        provisional = RunManifest(
            design_id=spec.design_id,
            design_revision=spec.revision,
            spec_sha256=spec.content_sha256(),
            stages=stages,
            artifacts=artifacts,
        )
        verdict = provisional.verdict
        status = {"passed": "completed",
                  "failed": "failed",
                  "inconclusive": "inconclusive"}[verdict]

        manifest = RunManifest.model_validate({
            **provisional.model_dump(mode="json"),
            "status": status,
            "completed_at": _now_iso(),
            "parent_run_id": parent_run_id,
            "toolchain": dict(toolchain or {}),
            "metadata": {
                "attempt": attempt,
                "requested_file": requested_file,
                "persisted_file": persisted_file,
            },
        })
        self.repository.save_manifest(manifest)
        return manifest, verdict
