"""Bounded browser execution and immutable Evidence for a web attempt."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from .evidence import DesignSpec, RunManifest, StageResult, default_repository


async def browser_report(url: str, acceptance: dict | None, timeout: float = 60) -> dict:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "bigbrain.verification.browser_runner",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=(os.name == "posix"),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(json.dumps({"url": url, "acceptance": acceptance}).encode()),
            timeout,
        )
        if process.returncode:
            return {"status": "inconclusive", "error": stderr.decode(errors="replace")[-2000:]}
        return json.loads(stdout)
    except asyncio.TimeoutError:
        return {
            "status": "inconclusive",
            "error": f"Browser verification timed out after {timeout}s",
        }
    finally:
        # Chromium is a descendant; terminate the whole process group on Stop
        # or timeout, including a child driver that outlived the Python runner.
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.returncode is None:
            process.kill()
        # Drain after termination so buffered pipe transports can close even
        # when the original communicate call was cancelled by its deadline.
        await asyncio.wait_for(process.communicate(), timeout=5)


def record_attempt(
    project: Path,
    user_request: str,
    validation: dict,
    report: dict,
    *,
    brain: str,
    attempt: int,
    parent_run_id: str | None = None,
    contract_revision: dict | None = None,
) -> RunManifest:
    repository = default_repository()
    design_id = "task-" + hashlib.sha256(user_request.encode()).hexdigest()[:16]
    if contract_revision:
        if contract_revision.get('design_id') != design_id:
            raise ValueError('Web contract belongs to another request')
        spec = repository.load_spec(design_id, contract_revision['revision'])
        if spec is None or spec.metadata.get('approval', {}).get('decision') != 'approved':
            raise ValueError('Approved web contract revision unavailable')
    else:
        spec = repository.load_latest_spec(design_id)
    if spec is None:
        spec = DesignSpec(
            design_id=design_id,
            name=user_request[:60],
            user_request=user_request,
            contracts=["Static web artifacts and browser scenarios pass"],
        )
        repository.save_spec(spec)
    artifacts = []
    for file in project.rglob("*"):
        if file.is_file() and file.suffix.lower() in {
            ".html",
            ".css",
            ".js",
            ".json",
            ".ts",
            ".tsx",
        }:
            if any(
                part.startswith(".") or part in {"node_modules", "dist"}
                for part in file.relative_to(project).parts
            ):
                continue
            if file.stat().st_size <= 2_000_000:
                artifacts.append(
                    repository.put_artifact(
                        file.read_bytes(),
                        name=file.relative_to(project).as_posix(),
                        media_type="text/plain",
                    )
                )
    report = json.loads(json.dumps(report))
    screenshot_hashes = []
    for index, case in enumerate(report.get("cases", [])):
        screenshot = case.pop("screenshot", None)
        if screenshot:
            ref = repository.put_artifact(
                base64.b64decode(screenshot),
                name=f"browser-case-{index + 1}.png",
                media_type="image/png",
            )
            artifacts.append(ref)
            case["screenshot_sha256"] = ref.sha256
            screenshot_hashes.append(ref.sha256)
    report_ref = repository.put_artifact(
        json.dumps(report, ensure_ascii=False).encode(),
        name="browser-report.json",
        media_type="application/json",
    )
    artifacts.append(report_ref)
    stages = [
        StageResult(
            name="web_artifacts",
            status="passed" if validation["passed"] else "failed",
            tool="BigBrain static web validator",
            details={"errors": validation["errors"],
                     **({'cause': 'missing_test'} if not validation['passed'] and validation.get('acceptance') is None else {})},
        ),
        StageResult(
            name="browser",
            status=report["status"],
            tool="Playwright Chromium",
            tool_version=report.get("browser_version"),
            artifact_hashes=[report_ref.sha256, *screenshot_hashes],
            details={
                **({'cause': 'awaiting_checks'} if report['status'] == 'skipped' else {}),
                "error": failure_summary(report) if report["status"] != "passed" else None,
                "cases": [
                    {"name": case["name"], "status": case["status"], "error": case.get("error")}
                    for case in report.get("cases", [])
                ],
            },
        ),
    ]
    if report.get('semantic_review'):
        stages.append(StageResult.model_validate(report['semantic_review']))
    for build in report.get("build_stages", []):
        stages.insert(
            -1,
            StageResult(name=build["name"], status=build["status"], tool="Node/npm",
                        details={**build, **({'cause': 'environment_blocked'}
                            if build['name'] == 'dependencies' and build['status'] != 'passed' else {})}),
        )
    manifest = RunManifest(
        design_id=spec.design_id,
        design_revision=spec.revision,
        spec_sha256=spec.content_sha256(),
        stages=stages,
        artifacts=artifacts,
        parent_run_id=parent_run_id,
        toolchain={"brain": brain, "browser": report.get("browser_version", "unavailable")},
        metadata={
            "attempt": attempt,
            "project_path": str(project),
            "browser_tests_executed": bool(report.get("cases")),
        },
    )
    manifest.completed_at = datetime.now(timezone.utc)
    manifest.status = {"passed": "completed", "failed": "failed", "inconclusive": "inconclusive"}[
        manifest.verdict
    ]
    repository.save_manifest(manifest)
    return manifest


def failure_summary(report: dict) -> str:
    errors = [report.get("error", "")]
    errors += [
        f"{case['name']}: {case.get('error', '')}"
        for case in report.get("cases", [])
        if case["status"] != "passed"
    ]
    errors += report.get("console_errors", []) + report.get("network_errors", [])
    errors += ["Blocked external request: " + url for url in report.get("blocked_requests", [])]
    errors += [
        f"{stage['name']}: {stage['output']}"
        for stage in report.get("build_stages", [])
        if stage["status"] != "passed"
    ]
    return (
        "\n".join(error for error in errors if error)[:8000] or "Browser verification did not pass"
    )
