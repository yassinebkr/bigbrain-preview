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

import asyncio
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

# Streaming runs: the server registers an async broadcast so the fs
# module can push live output to the WS clients without holding a bus
# reference (fs_api stays a standalone module).
_EventSink = Any
_event_sink: _EventSink = None


def set_event_sink(sink: _EventSink) -> None:
    """Register `async def sink(event_type, payload) -> None`."""
    global _event_sink
    _event_sink = sink


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
        if not child.name.startswith(".") and child.name not in {"node_modules", "__pycache__"}
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

    def _exec_blocking(args: list, cwd: Path) -> Dict[str, Any]:
        start = time.time()
        try:
            proc = subprocess.run(
                args,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(cwd),
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

    # Package files run as modules (relative imports need a project root).
    package = _package_module_run(target)
    if package is not None:
        project_root, module = package
        return _exec_blocking([sys.executable, "-u", "-m", module],
                              cwd=project_root)

    result = _exec_blocking([sys.executable, "-u", str(target)],
                            cwd=target.parent)
    if _relative_import_failure(result):
        retry = _namespace_retry(target)
        if retry is not None:
            project_root, module = retry
            return _exec_blocking([sys.executable, "-u", "-m", module],
                                  cwd=project_root)
    return result


def search_files(query: str, limit: int = 20) -> Dict[str, Any]:
    """Case-insensitive substring search over the workspace tree.

    Bounded and dot-free (manifests, .exec/ temp scripts are skipped) —
    powers the research bar's real file suggestions.
    """
    q = (query or "").strip().lower()
    if not q:
        return {"query": query, "results": []}
    root = workspace_root()
    results: List[Dict[str, Any]] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        _dirnames[:] = [d for d in _dirnames if not d.startswith(".") and d not in {"node_modules", "__pycache__"}]
        for name in filenames:
            if name.startswith(".") or q not in name.lower():
                continue
            rel = Path(dirpath).relative_to(root).as_posix()
            full = f"{rel}/{name}" if rel != "." else name
            results.append({"path": full, "name": name, "type": "file"})
            if len(results) >= limit:
                return {"query": query, "results": results}
    return {"query": query, "results": results}


# ── projects (global workspace + per-project sub-workspaces) ───────────────

async def run_file_with_evidence(rel: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Run a workspace .py file AND record it through the deterministic gate.

    The UI's Run button must leave the same auditable evidence as the
    agent's runs: stages (syntax, compile, run, contracts, tests) and an
    immutable manifest under data/evidence/. Evidence is best effort —
    a recording failure never breaks a manual run. Kill switch:
    BIGBRAIN_EVIDENCE=0.
    """
    result = await asyncio.to_thread(run_file, rel, timeout)
    return await _record_run_evidence(rel, result)


async def _record_run_evidence(rel: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the deterministic gate verdict to an executed run result.

    Best effort — a recording failure never breaks a manual run.
    """
    if os.environ.get("BIGBRAIN_EVIDENCE", "1") == "0":
        return result

    try:
        import platform

        from ..verification.evidence import default_repository
        from ..verification.gate import RunGate

        target = _resolve(workspace_root(), rel)
        code = await asyncio.to_thread(
            target.read_text, encoding="utf-8", errors="replace")
        # run_file's wire keys (exitCode, timedOut) → the executor's
        # execution shape (exit_code, timed_out).
        execution = {
            "exit_code": result.get("exitCode"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "timed_out": bool(result.get("timedOut")),
        }
        manifest, verdict = await RunGate(default_repository()).evaluate_attempt(
            user_request=f"manual run {rel}",
            code=code,
            execution=execution,
            work_dir=target.parent,
            requested_file=target.name,
            persisted_file=target.name,
            toolchain={"python": platform.python_version(), "brain": "manual-ui"},
            filename=target.name,
        )
        result["verification"] = {
            "run_id": manifest.run_id,
            "verdict": verdict,
            "stages": [{"name": s.name, "status": s.status}
                       for s in manifest.stages],
        }
    except Exception:
        pass
    return result


# ── streaming manual runs ──────────────────────────────────────────────────

MAX_STREAM_BUFFER = 20000  # live tail kept per stream


def _package_module_run(target: Path) -> tuple[Path, str] | None:
    """If the file lives inside a package, the correct invocation is
    `python -m pkg.mod` from the project root — a plain `python cli.py`
    breaks relative imports ("attempted relative import with no known
    parent package"), which is exactly what generated multi-file
    projects use.

    Returns (project_root, dotted_module) or None for a plain script.
    """
    if not (target.parent / "__init__.py").is_file():
        return None
    root = target.parent.parent
    parts = [target.parent.name]
    # Walk up through enclosing packages (__init__.py present).
    while (root / "__init__.py").is_file():
        parts.insert(0, root.name)
        root = root.parent
    parts.append(target.stem)
    return root, ".".join(parts)


def _relative_import_failure(result: Dict[str, Any]) -> bool:
    stderr = str(result.get("stderr") or "")
    return (result.get("exitCode") not in (0, None)
            and "relative import" in stderr
            and "ImportError" in stderr)


def _namespace_retry(target: Path) -> tuple[Path, str] | None:
    """Fallback for namespace packages (no __init__.py): the parent dir
    is the package, its parent the project root."""
    if target.parent.parent == target.parent:
        return None  # no room above
    return target.parent.parent, f"{target.parent.name}.{target.stem}"


async def run_file_streaming(rel: str, timeout: float = 30.0,
                              on_delta=None) -> Dict[str, Any]:
    """Run a workspace .py file, forwarding output AS IT IS PRODUCED.

    Same contract as :func:`run_file` (bounded, parent cwd, evidence-ready
    result dict) plus `on_delta(stream, chunk)` callbacks fired while the
    program runs. The child runs with ``python -u`` so prints stream as
    they happen instead of waiting for the block-buffered pipe to flush.
    """
    import sys

    root = workspace_root()
    target = _resolve(root, rel)
    if not target.is_file():
        raise web.HTTPNotFound(text=json_error("file not found"))
    if target.suffix != ".py":
        raise web.HTTPBadRequest(text=json_error("only .py files can be run"))
    timeout = min(max(float(timeout), 1.0), 120.0)

    async def _exec(args: list, cwd: Path) -> Dict[str, Any]:
        start = time.time()
        # stdin = DEVNULL: a manual run has no interactive input — a
        # program reading stdin must get EOF, not hang until the timeout.
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )

        async def pump(stream, name: str, sink) -> str:
            collected: list[str] = []
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                collected.append(text)
                if sink is not None:
                    try:
                        await sink(name, text)
                    except Exception:
                        pass  # streaming must never break the execution
            return "".join(collected)[-MAX_STREAM_BUFFER:]

        async def pump_all() -> tuple[str, str]:
            out_task = asyncio.create_task(pump(proc.stdout, "out", on_delta))
            err_task = asyncio.create_task(pump(proc.stderr, "err", on_delta))
            out = await out_task
            err = await err_task
            await proc.wait()
            return out, err

        try:
            stdout, stderr = await asyncio.wait_for(pump_all(), timeout=timeout)
            return {
                "ok": proc.returncode == 0,
                "exitCode": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "durationMs": int((time.time() - start) * 1000),
                "timedOut": False,
            }
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            return {
                "ok": False,
                "exitCode": -1,
                "stdout": "",
                "stderr": f"timed out after {timeout:.0f}s",
                "durationMs": int((time.time() - start) * 1000),
                "timedOut": True,
            }

    # Package files (relative imports) must run as modules from the
    # project root: `python -m todo_app.cli`, not `python cli.py`.
    package = _package_module_run(target)
    if package is not None:
        project_root, module = package
        return await _exec([sys.executable, "-u", "-m", module],
                           cwd=project_root)

    result = await _exec([sys.executable, "-u", str(target)],
                         cwd=target.parent)
    if _relative_import_failure(result):
        # Namespace package (no __init__.py): one retry as a module.
        retry = _namespace_retry(target)
        if retry is not None:
            project_root, module = retry
            return await _exec([sys.executable, "-u", "-m", module],
                               cwd=project_root)
    return result


_manual_web_previews: Dict[str, asyncio.subprocess.Process] = {}


async def run_static_preview(rel: str) -> Dict[str, Any]:
    """Start (or replace) the preview for a verified static web project."""
    target = _resolve(workspace_root(), rel)
    if target.name != "index.html" or not target.is_file():
        raise web.HTTPBadRequest(text=json_error("web preview entry point must be index.html"))
    project_dir = target.parent
    manifest_path = project_dir / PROJECT_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise web.HTTPBadRequest(text=json_error("verified web project manifest missing"))
    if (manifest.get("deliverable_type") != "web_app"
            or manifest.get("entry_point") != "index.html"
            or not manifest.get("verified")):
        raise web.HTTPBadRequest(text=json_error("web project is not verified runnable"))

    key = project_dir.as_posix()
    preview_dir = project_dir
    if manifest.get("web_stack") == "react_vite":
        preview_dir = project_dir / "dist"
        if not (preview_dir / "index.html").is_file():
            raise web.HTTPBadRequest(text=json_error("verified production build missing; rebuild the project"))
    previous = _manual_web_previews.pop(key, None)
    if previous and previous.returncode is None:
        previous.terminate()
        try:
            await asyncio.wait_for(previous.wait(), timeout=2)
        except asyncio.TimeoutError:
            previous.kill()
            await previous.wait()

    port = None
    import socket
    for candidate in range(3300, 3400):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", candidate))
            except OSError:
                continue
        port = candidate
        break
    if port is None:
        raise RuntimeError("no free manual preview port in 3300-3399")

    started = time.time()
    process = await asyncio.create_subprocess_exec(
        "python3", "-m", "http.server", str(port), "--bind", "127.0.0.1",
        cwd=str(preview_dir), stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    await asyncio.sleep(0.15)
    if process.returncode is not None:
        stderr = (await process.stderr.read()).decode(errors="replace")
        return {"ok": False, "exitCode": process.returncode, "stdout": "",
                "stderr": stderr[-20000:], "durationMs": int((time.time() - started) * 1000),
                "timedOut": False}
    _manual_web_previews[key] = process
    url = f"http://127.0.0.1:{port}"
    return {"ok": True, "exitCode": 0, "stdout": f"Preview ready: {url}\n",
            "stderr": "", "durationMs": int((time.time() - started) * 1000),
            "timedOut": False, "previewUrl": url, "serverRunning": True,
            "serverPid": process.pid}


async def _run_with_events(rel: str, timeout: float, run_id: str) -> None:
    """Background task behind POST /api/fs/run: stream then finalise."""
    async def sink(stream: str, delta: str) -> None:
        if _event_sink is not None:
            await _event_sink("fs.run_output",
                              {"runId": run_id, "stream": stream,
                               "delta": delta})

    try:
        if Path(rel).suffix.lower() == ".html":
            result = await run_static_preview(rel)
            if result.get("stdout"):
                await sink("out", result["stdout"])
        else:
            result = await run_file_streaming(rel, timeout, on_delta=sink)
    except web.HTTPNotFound:
        result = {"ok": False, "exitCode": -1, "stdout": "",
                  "stderr": "file not found", "durationMs": 0,
                  "timedOut": False}
    except web.HTTPBadRequest:
        result = {"ok": False, "exitCode": -1, "stdout": "",
                  "stderr": "only Python files or verified web projects can be run", "durationMs": 0,
                  "timedOut": False}
    except Exception as exc:  # never leave a client without a verdict
        logger.exception("streaming run failed")
        result = {"ok": False, "exitCode": -1, "stdout": "",
                  "stderr": f"internal error: {exc}"[:200],
                  "durationMs": 0, "timedOut": False}

    if Path(rel).suffix.lower() == ".py":
        result = await _record_run_evidence(rel, result)
    if _event_sink is not None:
        await _event_sink("fs.run_result", {"runId": run_id, **result})



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
    for manifest_path in sorted(root.rglob(PROJECT_MANIFEST)):
        if any(part in {".venv", "__pycache__", ".git"} for part in manifest_path.parts):
            continue
        child = manifest_path.parent
        relative = child.relative_to(root)
        # Root projects plus one nested level (not arbitrary dependency trees).
        if len(relative.parts) > 2:
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError:
            manifest = {}
        projects.append({
            "name": manifest.get("name") or child.name,
            "path": relative.as_posix(),
            "created": manifest.get("created"),
            "entry_point": manifest.get("entry_point"),
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
    app.router.add_get("/api/fs/search", _handle_search)
    app.on_cleanup.append(_cleanup_manual_web_previews)


async def _cleanup_manual_web_previews(_app: web.Application) -> None:
    """Never leave UI-started preview servers behind on shutdown."""
    processes = list(_manual_web_previews.values())
    _manual_web_previews.clear()
    for process in processes:
        if process.returncode is None:
            process.terminate()
    for process in processes:
        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()


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
    """Start a streaming workspace run — output flows over the WS.

    Returns {runId} immediately; the client follows `fs.run_output`
    deltas and the final `fs.run_result` (same payload shape as the old
    blocking response, evidence included) over its WebSocket.
    """
    import uuid

    body = await request.json()
    run_id = f"fsrun-{uuid.uuid4().hex[:10]}"
    asyncio.create_task(_run_with_events(
        body.get("path", ""), body.get("timeout", 30.0), run_id))
    return web.json_response({"runId": run_id, "streaming": True})


async def _handle_search(request: web.Request) -> web.Response:
    import asyncio

    result = await asyncio.to_thread(search_files, request.query.get("q", ""))
    return web.json_response(result)


async def _handle_projects(request: web.Request) -> web.Response:
    return web.json_response(list_projects())


async def _handle_project_create(request: web.Request) -> web.Response:
    body = await request.json()
    return web.json_response(create_project(body.get("name", "")))
