"""Workspace filesystem API for the Aplot web UI.

Real file operations (list / read / write / mkdir / rename / move / delete)
against a workspace root directory, replacing the UI's mock file tree.
The agent (PythonBrain) can write into the same root — the UI and the agent
share one workspace.

Security: every path is resolved and checked to stay inside the workspace
root (no traversal). Content reads are size-bounded. Deletes refuse to
escape the root by construction.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from aiohttp import web

logger = logging.getLogger(__name__)

# Maximum read size served to the UI (larger files return a notice).
MAX_READ_BYTES = 512 * 1024

_REPO_ROOT = Path(__file__).resolve().parents[2]


def workspace_root() -> Path:
    """The shared workspace root (agent + UI)."""
    root = Path(os.environ.get("BIGBRAIN_WORKSPACE_DIR") or (_REPO_ROOT / "workspace"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve(root: Path, rel: str) -> Path:
    """Resolve a workspace-relative path, refusing any escape from root."""
    if rel is None:
        rel = ""
    rel = (rel or "").strip().lstrip("/").lstrip("\\")
    candidate = (root / rel).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise web.HTTPBadRequest(
            text=json_error("path escapes the workspace root")
        )
    return candidate


def json_error(message: str) -> str:
    import json

    return json.dumps({"error": message})


def _entry_info(path: Path, root: Path) -> Dict[str, Any]:
    rel = path.relative_to(root).as_posix()
    stat = path.stat()
    return {
        "name": path.name,
        "path": rel,
        "type": "folder" if path.is_dir() else "file",
        "size": stat.st_size if path.is_file() else None,
        "modified": stat.st_mtime,
        "extension": path.suffix.lstrip(".") if path.is_file() else None,
    }


def list_dir(rel: str = "") -> Dict[str, Any]:
    root = workspace_root()
    target = _resolve(root, rel)
    if not target.exists():
        raise web.HTTPNotFound(text=json_error("path not found"))
    if not target.is_dir():
        raise web.HTTPBadRequest(text=json_error("not a folder"))
    entries: List[Dict[str, Any]] = [
        _entry_info(child, root) for child in sorted(target.iterdir())
        # Dot-entries are internal: .project.json manifests, the brain's
        # .exec/ temp scripts. They stay on disk but never clutter the UI.
        if not child.name.startswith(".")
    ]
    return {"path": rel or "", "entries": entries}


def read_file(rel: str) -> Dict[str, Any]:
    root = workspace_root()
    target = _resolve(root, rel)
    if not target.is_file():
        raise web.HTTPNotFound(text=json_error("file not found"))
    size = target.stat().st_size
    if size > MAX_READ_BYTES:
        return {
            "path": rel,
            "truncated": True,
            "binary": False,
            "content": f"(file is {size} bytes — too large to preview)",
        }
    try:
        content = target.read_text(encoding="utf-8")
        binary = False
    except UnicodeDecodeError:
        return {
            "path": rel,
            "truncated": False,
            "binary": True,
            "content": "(binary file — preview unavailable)",
        }
    return {"path": rel, "truncated": False, "binary": False, "content": content}


def write_file(rel: str, content: str) -> Dict[str, Any]:
    root = workspace_root()
    target = _resolve(root, rel)
    if target == root.resolve():
        raise web.HTTPBadRequest(text=json_error("missing file path"))
    if target.exists() and target.is_dir():
        raise web.HTTPBadRequest(text=json_error("path is a folder"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content or "", encoding="utf-8")
    return {"ok": True, "path": rel}


def mkdir(rel: str) -> Dict[str, Any]:
    root = workspace_root()
    target = _resolve(root, rel)
    if target.exists():
        raise web.HTTPBadRequest(text=json_error("path already exists"))
    target.mkdir(parents=True, exist_ok=False)
    return {"ok": True, "path": rel}


def rename(rel: str, new_name: str) -> Dict[str, Any]:
    root = workspace_root()
    target = _resolve(root, rel)
    if not target.exists():
        raise web.HTTPNotFound(text=json_error("path not found"))
    new_name = (new_name or "").strip()
    if not new_name or "/" in new_name or "\\" in new_name or new_name in (".", ".."):
        raise web.HTTPBadRequest(text=json_error("invalid name"))
    destination = target.with_name(new_name)
    if destination.exists():
        raise web.HTTPBadRequest(text=json_error("name already exists"))
    target.rename(destination)
    return {"ok": True, "path": destination.relative_to(root).as_posix()}


def move(rel: str, dest_dir: str) -> Dict[str, Any]:
    root = workspace_root()
    target = _resolve(root, rel)
    destination_dir = _resolve(root, dest_dir)
    if not target.exists():
        raise web.HTTPNotFound(text=json_error("path not found"))
    if not destination_dir.is_dir():
        raise web.HTTPBadRequest(text=json_error("destination is not a folder"))
    destination = destination_dir / target.name
    if destination.exists():
        raise web.HTTPBadRequest(text=json_error("name already exists in destination"))
    shutil.move(str(target), str(destination))
    return {"ok": True, "path": destination.relative_to(root).as_posix()}


def delete(rel: str) -> Dict[str, Any]:
    root = workspace_root()
    target = _resolve(root, rel)
    if target == root.resolve():
        raise web.HTTPBadRequest(text=json_error("refusing to delete the workspace root"))
    if not target.exists():
        raise web.HTTPNotFound(text=json_error("path not found"))
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"ok": True, "path": rel}


def run_file(rel: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Run a workspace Python file in a subprocess and capture its output.

    Dev-tool counterpart of the code viewer's Run button: same trust model
    as the write API (local single-user tool), bounded output, hard
    timeout. The process runs with the file's parent as cwd so relative
    writes behave as in the brain's execution model.
    """
    import subprocess
    import sys

    root = workspace_root()
    target = _resolve(root, rel)
    if not target.is_file():
        raise web.HTTPNotFound(text=json_error("file not found"))
    if target.suffix != ".py":
        raise web.HTTPBadRequest(text=json_error("only .py files can be run"))
    timeout = min(max(float(timeout), 1.0), 120.0)
    start = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(target)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(target.parent),
        )
        return {
            "ok": proc.returncode == 0,
            "exitCode": proc.returncode,
            "stdout": proc.stdout[-20000:],
            "stderr": proc.stderr[-20000:],
            "durationMs": int((time.time() - start) * 1000),
            "timedOut": False,
        }
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        return {
            "ok": False,
            "exitCode": -1,
            "stdout": out[-20000:],
            "stderr": f"timed out after {timeout:.0f}s",
            "durationMs": int((time.time() - start) * 1000),
            "timedOut": True,
        }


# ── projects (global workspace + per-project sub-workspaces) ───────────────

PROJECT_MANIFEST = ".project.json"
SANDBOX_PROJECT = "sandbox"


def create_project(name: str) -> Dict[str, Any]:
    """Create a project sub-workspace at the workspace root.

    A project is a folder with a ``.project.json`` manifest — future home
    of per-project config (models, brains, focus). Refuses weird names.
    """
    import json
    import re

    name = (name or "").strip()
    if not name or not re.fullmatch(r"[\w][\w .-]*", name) or name.startswith("."):
        raise web.HTTPBadRequest(text=json_error("invalid project name"))
    root = workspace_root()
    target = _resolve(root, name)
    if target.exists():
        raise web.HTTPBadRequest(text=json_error("project already exists"))
    target.mkdir(parents=True)
    manifest = {"name": name, "created": time.time()}
    (target / PROJECT_MANIFEST).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return {"ok": True, "path": name, "manifest": manifest}


def ensure_sandbox() -> Dict[str, Any]:
    """Idempotently create the sandbox project.

    The sandbox is the default write target when no project is selected
    (global mode): agent files land in a real project folder instead of a
    loose ``python/`` pool, so the explorer, project selector and future
    per-project config treat them uniformly.
    """
    import json

    root = workspace_root()
    target = root / SANDBOX_PROJECT
    manifest_path = target / PROJECT_MANIFEST
    if not manifest_path.is_file():
        target.mkdir(parents=True, exist_ok=True)
        manifest = {"name": SANDBOX_PROJECT, "created": time.time(), "sandbox": True}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"ok": True, "path": SANDBOX_PROJECT}


def list_projects() -> Dict[str, Any]:
    """Projects = root-level folders carrying a .project.json manifest."""
    import json

    root = workspace_root()
    projects = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / PROJECT_MANIFEST
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError:
            manifest = {}
        projects.append({
            "name": manifest.get("name") or child.name,
            "path": child.name,
            "created": manifest.get("created"),
        })
    return {"projects": projects}


# ── current project (the project the chat/agent is working in) ──────────────

_CURRENT_PROJECT_FILE = _REPO_ROOT / "data" / "current_project.json"


def get_current_project() -> Optional[str]:
    """The selected project path ('' or None = global workspace)."""
    try:
        data = json.loads(_CURRENT_PROJECT_FILE.read_text(encoding="utf-8"))
        return data.get("project") or None
    except (OSError, ValueError):
        return None


def set_current_project(project: Optional[str]) -> Dict[str, Any]:
    """Select the working project (None/'' = global).

    Validates that the path is an existing project (manifest-carrying
    folder) — selecting a plain folder is refused.
    """
    project = (project or "").strip() or None
    if project:
        root = workspace_root()
        target = _resolve(root, project)
        if not target.is_dir() or not (target / PROJECT_MANIFEST).is_file():
            raise web.HTTPBadRequest(text=json_error("not a project (missing .project.json)"))
    _CURRENT_PROJECT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CURRENT_PROJECT_FILE.write_text(
        json.dumps({"project": project}, indent=2), encoding="utf-8"
    )
    return {"ok": True, "project": project}


# ── aiohttp handlers ──────────────────────────────────────────────────────


def setup_fs_routes(app: web.Application) -> None:
    app.router.add_get("/api/fs/list", _handle_list)
    app.router.add_get("/api/fs/projects", _handle_projects)
    app.router.add_post("/api/fs/project", _handle_project_create)
    app.router.add_get("/api/fs/file", _handle_read)
    app.router.add_post("/api/fs/file", _handle_write)
    app.router.add_delete("/api/fs/file", _handle_delete)
    app.router.add_post("/api/fs/mkdir", _handle_mkdir)
    app.router.add_post("/api/fs/rename", _handle_rename)
    app.router.add_post("/api/fs/move", _handle_move)
    app.router.add_post("/api/fs/run", _handle_run)


async def _handle_list(request: web.Request) -> web.Response:
    return web.json_response(list_dir(request.query.get("path", "")))


async def _handle_read(request: web.Request) -> web.Response:
    return web.json_response(read_file(request.query.get("path", "")))


async def _handle_write(request: web.Request) -> web.Response:
    body = await request.json()
    return web.json_response(write_file(body.get("path", ""), body.get("content", "")))


async def _handle_delete(request: web.Request) -> web.Response:
    return web.json_response(delete(request.query.get("path", "")))


async def _handle_mkdir(request: web.Request) -> web.Response:
    body = await request.json()
    return web.json_response(mkdir(body.get("path", "")))


async def _handle_rename(request: web.Request) -> web.Response:
    body = await request.json()
    return web.json_response(rename(body.get("path", ""), body.get("newName", "")))


async def _handle_move(request: web.Request) -> web.Response:
    body = await request.json()
    return web.json_response(move(body.get("path", ""), body.get("destDir", "")))


async def _handle_run(request: web.Request) -> web.Response:
    """Execute a workspace .py file off the event loop."""
    import asyncio

    body = await request.json()
    result = await asyncio.to_thread(
        run_file, body.get("path", ""), body.get("timeout", 30.0)
    )
    return web.json_response(result)


async def _handle_projects(request: web.Request) -> web.Response:
    return web.json_response(list_projects())


async def _handle_project_create(request: web.Request) -> web.Response:
    body = await request.json()
    return web.json_response(create_project(body.get("name", "")))
