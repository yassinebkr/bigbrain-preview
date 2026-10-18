"""Rebuild conversation activity from the durable bus journal, not a 5m buffer.

Read-only projection: never re-dispatch tasks or replay assistant messages.
The journal is already fsync'd by BusLogger before events reach the UI.
"""

import json
from pathlib import Path

RUN_EVENTS = {
    "task.routing", "task.received", "planning.stage",
    "contracts.proposal", "contracts.approved", "contracts.rejected",
    "subtask.started", "subtask.complete", "subtask.failed",
    "workspace.file_written", "verification.run_recorded",
    "task.complete", "task.failed", "task.cancelled",
    "task.progress",
}
TERMINAL_EVENTS = {"task.complete", "task.failed", "task.cancelled"}


def conversation_activity(log_dir: Path, session_id: str, started_at: float) -> list[dict]:
    """Latest state per step/file of the last 100 runs, in journal order.

Legacy routing events lacked a plan id. Bind their preparation to the next
task.received; new events carry one stable id from the front brain onwards.
An unfinished plan from a previous process is interrupted, not live work.
"""
    runs = {}
    pending = None
    for path in sorted(log_dir.glob("bus-*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    frame = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(frame, dict):
                    continue
                data = frame.get("payload")
                if not isinstance(data, dict) or data.get("session_id") != session_id:
                    continue
                if frame.get("type") == "progress":
                    frame["type"] = "event"
                    data.update(event="task.progress", brain=frame.get("source"))
                event = data.get("event")
                if frame.get("type") != "event" or not isinstance(event, str) or event not in RUN_EVENTS:
                    continue
                run_id = data.get("task_id") or data.get("plan_id")
                if event == "task.routing" and not run_id:
                    pending = f"routing-{frame.get('id', len(runs))}"
                    run_id = pending
                elif event == "task.received" and pending:
                    if pending in runs:
                        runs[run_id] = runs.pop(pending)
                        for old in runs[run_id].values():
                            old["payload"]["task_id"] = run_id
                    pending = None
                run_id = run_id or pending
                if not isinstance(run_id, str) or not run_id:
                    continue
                data["task_id"] = run_id
                # Final subtask states replace started, preserving its label/brain.
                key = ("subtask" if event.startswith("subtask.") else event,
                       data.get("subtask_id"), data.get("path"), data.get("stage"))
                records = runs.setdefault(run_id, {})
                old = records.get(key)
                if old and event.startswith("subtask."):
                    frame["payload"] = {**old["payload"], **data}
                records[key] = frame
    output = []
    ordered = sorted(runs.items(), key=lambda item: max(f.get("timestamp", 0) for f in item[1].values()))
    closed = [item for item in ordered if any(f["payload"]["event"] in TERMINAL_EVENTS for f in item[1].values())]
    live = [item for item in ordered if not any(f["payload"]["event"] in TERMINAL_EVENTS for f in item[1].values())]
    recent = closed[-100:] + live
    for run_id, records in recent:
        frames = list(records.values())
        latest = max(f.get("timestamp", 0) for f in frames)
        if latest < started_at and not any(f["payload"]["event"] in TERMINAL_EVENTS for f in frames):
            frames.append({"type": "event", "timestamp": started_at, "source": "web_server",
                "payload": {"event": "task.failed", "task_id": run_id, "session_id": session_id,
                            "runnable": False, "error": "Exécution interrompue par un redémarrage du serveur. Relance la demande."}})
        output.extend(frames)
    return sorted(output, key=lambda frame: frame.get("timestamp", 0))
