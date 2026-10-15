"""TaskBoardBrain — gives the agent a REAL task-board capability.

"Add a task to my task board" used to route to the PythonBrain (which
has nothing to do with it) and the LLM would claim success while
nothing persisted. This brain owns the user's persistent board
(``data/tasks.json`` via :class:`~bigbrain.web.taskboard.TaskBoardStore`):

* task type ``board_task`` with ``{title, description?, status?}``
  (status defaults to ``todo`` — a request is a TO-DO unless the user
  says otherwise),
* broadcasts ``taskboard.task_created`` so every open UI refreshes,
* returns the created task so the front brain can report the truth.
"""

from __future__ import annotations

from typing import Any, Dict

from .base import BaseBrain
from ..bus.message import BusMessage, MessageType, Priority


class TaskBoardBrain(BaseBrain):
    """Creates tasks on the user's persistent task board."""

    async def handle_task(self, message: BusMessage) -> Dict[str, Any]:
        payload = message.payload or {}
        task_type = payload.get("type")

        if task_type == "board_task":
            return await self._create_task(payload)
        raise ValueError(f"Unknown task type: {task_type}")

    async def _create_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from ..web.taskboard import TaskBoardError, TaskBoardStore

        title = payload.get("title") or payload.get("request") or ""
        description = payload.get("description") or payload.get("user_request") or ""
        status = payload.get("status", "todo")

        try:
            task = TaskBoardStore().create(
                title=title,
                description=description,
                status=status,
                tags=["agent"],
                assignee="BigBrain",
            )
        except TaskBoardError as exc:
            return {"success": False, "error": str(exc), "task": None}

        # Tell every connected UI a board task was created.
        try:
            await self.bus.send(BusMessage(
                type=MessageType.EVENT,
                source=self.name,
                target="morphable_ui",
                payload={
                    "event": "taskboard.task_created",
                    "task": task,
                },
                priority=Priority.NORMAL,
            ))
        except Exception:
            pass  # the notification must never break the creation

        return {
            "success": True,
            "task": task,
            "message": f"Task '{task['title']}' added to the board as {task['status']}.",
        }
