"""Persistent TaskBoard store — the user's tasks, surviving restarts.

Tasks used to live only in the browser's Zustand store (lost on reload,
invisible to the agent). The board is now server-side: a small JSON
file (``data/tasks.json``, ``BIGBRAIN_TASKS_FILE`` to move), atomic
writes, full CRUD. The agent creates tasks through the taskboard
brain (task type ``board_task``); the UI reads and writes the same
store via ``/api/tasks``.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

from aiohttp import web

from pathlib import Path as _Path

_REPO_ROOT = _Path(__file__).resolve().parents[2]

VALID_STATUSES = ("todo", "in-progress", "review", "done")


class TaskBoardError(ValueError):
    """Raised for invalid task operations."""


class TaskBoardStore:
    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = _Path(path or os.environ.get("BIGBRAIN_TASKS_FILE")
                         or (_REPO_ROOT / "data" / "tasks.json")).absolute()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── persistence ──────────────────────────────────────────────────

    def _load(self) -> List[Dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return data.get("tasks", []) if isinstance(data, dict) else []

    def _save(self, tasks: List[Dict[str, Any]]) -> None:
        content = json.dumps({"tasks": tasks}, indent=2,
                             ensure_ascii=False).encode("utf-8")
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent,
                                              prefix=f".{self.path.name}.",
                                              suffix=".tmp",
                                              delete=False) as handle:
                temporary = handle.name
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    # ── API ───────────────────────────────────────────────────────────

    def list(self) -> List[Dict[str, Any]]:
        return self._load()

    def create(self, title: str, description: str = "",
               status: str = "todo", tags: Optional[List[str]] = None,
               priority: str = "medium", assignee: str = "BigBrain") -> Dict[str, Any]:
        title = (title or "").strip()
        if not title:
            raise TaskBoardError("task title must not be empty")
        if status not in VALID_STATUSES:
            raise TaskBoardError(f"invalid status: {status!r}")
        task = {
            "id": f"task-{uuid.uuid4().hex[:10]}",
            "title": title[:200],
            "description": (description or "").strip()[:2000],
            "status": status,
            "tags": tags or [],
            "assignee": assignee,
            "priority": priority if priority in ("low", "medium", "high") else "medium",
            "createdAt": time.time(),
        }
        tasks = self._load()
        tasks.append(task)
        self._save(tasks)
        return task

    def update(self, task_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        tasks = self._load()
        for task in tasks:
            if task.get("id") == task_id:
                for key in ("title", "description", "status", "tags",
                            "assignee", "priority"):
                    if key in updates and updates[key] is not None:
                        if key == "status" and updates[key] not in VALID_STATUSES:
                            raise TaskBoardError(f"invalid status: {updates[key]!r}")
                        task[key] = updates[key]
                self._save(tasks)
                return task
        return None

    def delete(self, task_id: str) -> bool:
        tasks = self._load()
        remaining = [t for t in tasks if t.get("id") != task_id]
        if len(remaining) == len(tasks):
            return False
        self._save(remaining)
        return True


def setup_taskboard_routes(app: web.Application) -> None:
    app.router.add_get("/api/tasks", _handle_list)
    app.router.add_post("/api/tasks", _handle_create)
    app.router.add_patch("/api/tasks", _handle_update)
    app.router.add_delete("/api/tasks", _handle_delete)


def _store() -> TaskBoardStore:
    return TaskBoardStore()


async def _handle_list(request: web.Request) -> web.Response:
    return web.json_response({"tasks": _store().list()})


async def _handle_create(request: web.Request) -> web.Response:
    body = await request.json()
    try:
        task = _store().create(
            title=body.get("title", ""),
            description=body.get("description", ""),
            status=body.get("status", "todo"),
            tags=body.get("tags"),
            priority=body.get("priority", "medium"),
            assignee=body.get("assignee", "You"),
        )
    except TaskBoardError as exc:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": str(exc)}),
            content_type="application/json",
        ) from exc
    return web.json_response({"task": task})


async def _handle_update(request: web.Request) -> web.Response:
    body = await request.json()
    task = _store().update(body.get("id", ""), body.get("updates") or body)
    if task is None:
        raise web.HTTPNotFound(
            text=json.dumps({"error": "unknown task"}),
            content_type="application/json")
    return web.json_response({"task": task})


async def _handle_delete(request: web.Request) -> web.Response:
    deleted = _store().delete(request.query.get("id", ""))
    return web.json_response({"deleted": deleted})
