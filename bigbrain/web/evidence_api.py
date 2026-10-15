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


def list_runs(limit: int = 20) -> Dict[str, Any]:
    """Recent terminal + running runs, newest first, contracts included."""
    repo = default_repository()
    items: List[Dict[str, Any]] = []
    for manifest in repo.iter_manifests():
        spec = repo.load_spec(manifest.design_id, manifest.design_revision)
        items.append({
            "run_id": manifest.run_id,
            "status": manifest.status,
            "verdict": manifest.verdict,
            "created_at": manifest.created_at.isoformat()
            if hasattr(manifest.created_at, "isoformat")
            else str(manifest.created_at),
            "name": spec.name if spec else manifest.design_id,
            "user_request": spec.user_request if spec else None,
            "contracts": list(spec.contracts) if spec else [],
            "stages": [{"name": s.name, "status": s.status}
                       for s in manifest.stages],
            "attempt": manifest.metadata.get("attempt"),
            "replay_of": manifest.metadata.get("replay_of"),
            "brain": manifest.toolchain.get("brain"),
        })
    items.sort(key=lambda r: r["created_at"], reverse=True)
    return {"runs": items[:max(1, min(int(limit), 100))]}


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


async def _handle_runs(request: web.Request) -> web.Response:
    return web.json_response(list_runs(int(request.query.get("limit", 20))))


async def _handle_run(request: web.Request) -> web.Response:
    return web.json_response(run_detail(request.match_info["run_id"]))


async def _handle_artifact(request: web.Request) -> web.Response:
    return web.json_response(
        artifact_content(request.query.get("sha", "")))
