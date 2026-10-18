"""Evidence API — read-only views over the deterministic harness records.

Surfaces what the gate wrote under ``data/evidence/``:
* ``GET /api/evidence/runs``        — recent runs (verdict, contracts, stages)
* ``GET /api/evidence/run/{id}``    — one manifest + its spec
* ``GET /api/evidence/artifact?sha``— content of a recorded artifact (capped)

Read-only by design: evidence is immutable once terminal; the UI shows
what happened, it never rewrites it.
"""

from __future__ import annotations

from typing import Any, Dict, List

from aiohttp import web

from ..verification.evidence import default_repository

MAX_ARTIFACT_BYTES = 100 * 1024


def list_runs(limit: int = 100) -> Dict[str, Any]:
    """Runs GROUPED BY TASK (design_id), most recently active first.

    A task with 5 Honk attempts is ONE entry with its attempt history
    inside — a flat per-attempt list was unreadable. Each group carries
    the contracts, the verdict of the LATEST attempt, per-verdict counts
    and the individual run summaries.
    """
    repo = default_repository()
    groups: Dict[str, Dict[str, Any]] = {}

    for manifest in repo.iter_manifests():
        spec = repo.load_spec(manifest.design_id, manifest.design_revision)
        created_at = manifest.created_at.isoformat() \
            if hasattr(manifest.created_at, "isoformat") \
            else str(manifest.created_at)
        run = {
            "run_id": manifest.run_id,
            "status": manifest.status,
            "verdict": manifest.verdict,
            "created_at": created_at,
            "attempt": manifest.metadata.get("attempt"),
            "replay_of": manifest.metadata.get("replay_of"),
            "brain": manifest.toolchain.get("brain"),
            "stages": [{"name": s.name, "status": s.status}
                       for s in manifest.stages],
            "browser_evidence": next(({
                "details": stage.details,
                "screenshots": [artifact.sha256 for artifact in manifest.artifacts if artifact.media_type == "image/png"],
                "report": next((artifact.sha256 for artifact in manifest.artifacts if artifact.name == "browser-report.json"), None),
            } for stage in manifest.stages if stage.name == "browser"), None),
        }
        group = groups.get(manifest.design_id)
        if group is None:
            group = groups[manifest.design_id] = {
                "design_id": manifest.design_id,
                "name": spec.name if spec else manifest.design_id,
                "user_request": spec.user_request if spec else None,
                "contracts": list(spec.contracts) if spec else [],
                # Phase B approval trace: the user's verdict on the
                # proposed contracts, stamped on the spec revision.
                "approval": (spec.metadata.get("approval")
                             if spec else None),
                "runs": [],
            }
        group["runs"].append(run)

    tasks: List[Dict[str, Any]] = []
    for group in groups.values():
        runs = sorted(group["runs"], key=lambda r: r["created_at"], reverse=True)
        latest = runs[0]
        group.update({
            "runs": runs,
            "total": len(runs),
            "passed": sum(1 for r in runs if r["verdict"] == "passed"),
            "failed": sum(1 for r in runs if r["verdict"] == "failed"),
            "last_verdict": latest["verdict"],
            "last_run_id": latest["run_id"],
            "last_at": latest["created_at"],
            "has_replay": any(r["replay_of"] for r in runs),
        })
        tasks.append(group)
    tasks.sort(key=lambda t: t["last_at"], reverse=True)
    return {"tasks": tasks[:max(1, min(int(limit), 200))]}


def run_detail(run_id: str) -> Dict[str, Any]:
    """One manifest + its spec (contracts, user_request, hash link)."""
    repo = default_repository()
    manifest = repo.load_manifest(run_id)
    if manifest is None:
        raise web.HTTPNotFound(
            text='{"error": "unknown run"}', content_type="application/json")
    spec = repo.load_spec(manifest.design_id, manifest.design_revision)
    return {
        "manifest": manifest.model_dump(mode="json"),
        "spec": spec.model_dump(mode="json") if spec else None,
    }


def artifact_content(sha256: str) -> Dict[str, Any]:
    """Text content of a recorded artifact (size-capped)."""
    repo = default_repository()
    content = repo.get_artifact(sha256)
    if content is None:
        raise web.HTTPNotFound(
            text='{"error": "unknown artifact"}',
            content_type="application/json")
    truncated = len(content) > MAX_ARTIFACT_BYTES
    return {
        "sha256": sha256,
        "size_bytes": len(content),
        "truncated": truncated,
        "content": content[:MAX_ARTIFACT_BYTES].decode(
            "utf-8", errors="replace"),
    }


def setup_evidence_routes(app: web.Application) -> None:
    app.router.add_get("/api/evidence/runs", _handle_runs)
    app.router.add_get("/api/evidence/run/{run_id}", _handle_run)
    app.router.add_get("/api/evidence/artifact", _handle_artifact)
    app.router.add_get("/api/evidence/image/{sha}", _handle_image)


async def _handle_image(request: web.Request) -> web.Response:
    content = default_repository().get_artifact(request.match_info["sha"])
    if content is None or not content.startswith(b"\x89PNG\r\n\x1a\n") or len(content) > 2_000_000:
        raise web.HTTPNotFound()
    return web.Response(body=content, content_type="image/png", headers={"X-Content-Type-Options": "nosniff"})


async def _handle_runs(request: web.Request) -> web.Response:
    return web.json_response(list_runs(int(request.query.get("limit", 20))))


async def _handle_run(request: web.Request) -> web.Response:
    return web.json_response(run_detail(request.match_info["run_id"]))


async def _handle_artifact(request: web.Request) -> web.Response:
    return web.json_response(
        artifact_content(request.query.get("sha", "")))
