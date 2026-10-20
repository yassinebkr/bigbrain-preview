"""Run-owned destinations: navigation races, approval, paths and worker reuse."""

import asyncio
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.execution_target import ExecutionTarget, resolve_target
from bigbrain.brains.python_brain import PythonBrain
from bigbrain.brains.web_app_brain import WebAppBrain
from bigbrain.orchestrator.architect import ProjectSpec
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, SubTask, TaskStatus
from bigbrain.web import fs_api
from bigbrain.system import BigBrainSystem
from bigbrain.verification.evidence import default_repository


def action(kind="write_web_file"):
    return SubTask(id="s", description="file operation", brain_target="web_app_brain", payload={"type": kind})


def existing(root, name):
    directory = root / "sandbox" / name
    directory.mkdir(parents=True)
    (directory / ".project.json").write_text(json.dumps({"name": name, "entry_point": "main.py", "run": ["python", "main.py"]}))
    return directory


def message(payload):
    return BusMessage(type=MessageType.TASK, source="front_brain", target="orchestrator_default", payload=payload)


def test_navigation_does_not_bind_a_new_project_or_non_file_task(tmp_path):
    root = fs_api.workspace_root()
    blender = existing(root, "blender")
    fs_api.set_current_project("sandbox/blender")
    target = resolve_target("id", {"navigation_project": "sandbox/blender"}, [action()], ProjectSpec("running", "Running"))
    assert target.path == "sandbox/running"
    assert not target.directory.exists()
    assert blender.is_dir()
    with pytest.raises(FrozenInstanceError):
        target.path = "sandbox/blender"
    assert resolve_target("board", {"project_path": "sandbox/blender"}, [action("board_task")]) is None


@pytest.mark.parametrize("path", [".", "..", "../outside", "/tmp/outside", "sandbox/../blender", "sandbox//app", "sandbox/app/", "sandbox\\app", "sandbox/.hidden"])
def test_unsafe_project_targets_are_rejected(path):
    with pytest.raises(ValueError):
        resolve_target("id", {"project_target": {"mode": "new", "path": path}}, [action()])


def test_new_project_collision_is_not_implicit_permission_to_edit():
    existing(fs_api.workspace_root(), "running")
    with pytest.raises(ValueError, match="existe déjà"):
        resolve_target("id", {"project_target": {"mode": "new", "path": "sandbox/running"}}, [action()])
    target = resolve_target("id", {"project_target": {"mode": "existing", "path": "sandbox/running"}}, [action()])
    assert target.mode == "existing"


def test_partial_project_requires_provenance_and_still_pins_identity():
    directory = fs_api.workspace_root() / 'sandbox' / 'partial'
    directory.mkdir(parents=True)
    data = {'project_target': {'mode': 'existing', 'path': 'sandbox/partial'}}
    with pytest.raises(ValueError, match='manifeste'):
        resolve_target('fix', data, [action()])
    with pytest.raises(ValueError, match='manifeste'):
        resolve_target('fix', data, [action()], partial_project_check=lambda path: False)
    target = resolve_target('fix', data, [action()], partial_project_check=lambda path: path == 'sandbox/partial')
    assert target.inode == directory.stat().st_ino
    assert not (directory / '.project.json').exists()  # no fabricated runnable claim


def test_existing_operations_need_an_explicit_project():
    existing(fs_api.workspace_root(), "blender")
    fs_api.set_current_project("sandbox/blender")
    with pytest.raises(ValueError, match="Préciser le projet"):
        resolve_target("id", {}, [action("edit_file")])


def test_symlinks_and_replaced_directory_are_rejected(tmp_path):
    root = fs_api.workspace_root()
    folder = existing(root, "running")
    target = resolve_target("id", {"project_target": {"mode": "existing", "path": "sandbox/running"}}, [action()])
    outside = tmp_path / "outside"
    outside.mkdir()
    (folder / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolique"):
        target.file("linked/escape.py")
    folder.rename(folder.with_name("moved-running"))
    folder.mkdir()
    with pytest.raises(ValueError, match="remplacée"):
        target.validate()
    folder.rmdir()
    folder.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolique"):
        target.validate()


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_kind", ["python", "web"])
async def test_navigation_change_while_llm_waits_cannot_move_worker_output(tmp_path, worker_kind):
    root = fs_api.workspace_root()
    existing(root, "blender")
    target = resolve_target("id", {"project_target": {"mode": "new", "path": "sandbox/running"}}, [action()]).prepare()
    entered, release = asyncio.Event(), asyncio.Event()
    class Provider:
        async def complete(self, prompt, **kwargs):
            return await self.chat_complete(**kwargs)

        async def chat_complete(self, **kwargs):
            entered.set()
            await release.wait()
            return "VALUE = 42\n" if worker_kind == "python" else "const value = 42;\n"
    bus = MessageBus(tmp_path / "logs", auth=None)
    cls = PythonBrain if worker_kind == "python" else WebAppBrain
    worker = cls(worker_kind, bus, work_dir=root / "sandbox", llm_provider=Provider())
    filename = "state.py" if worker_kind == "python" else "app.js"
    payload = {"type": "write_project_file" if worker_kind == "python" else "write_web_file",
               "project_name": "wrong-old-name", "file_path": filename, "_execution_target": target.to_payload()}
    task = asyncio.create_task(worker.handle_task(message(payload)))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        fs_api.set_current_project("sandbox/blender")
        system = object.__new__(BigBrainSystem)
        system.brains = {worker_kind: worker}
        assert system.apply_current_project()["retargeted"] == 0
        release.set()
        result = await asyncio.wait_for(task, 5)
        assert result["success"], result
        assert (target.directory / filename).read_text().strip()
        assert not (root / "sandbox/blender" / filename).exists()
        assert not (target.directory / "wrong-old-name").exists()
        assert worker.work_dir == root / "sandbox"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await bus.close()


@pytest.mark.asyncio
async def test_same_python_worker_reused_for_two_targets(tmp_path):
    root = fs_api.workspace_root()
    worker = PythonBrain("python", MessageBus(tmp_path / "logs", auth=None), work_dir=root / "sandbox")
    for name in ["running", "photoshop"]:
        target = resolve_target(name, {"project_target": {"mode": "new", "path": f"sandbox/{name}"}}, [action()]).prepare()
        result = await worker.handle_task(message({"type": "batch_write_files", "_execution_target": target.to_payload(),
            "files": [{"path": "marker.txt", "content": name}]}))
        assert result["success"], result
    assert (root / "sandbox/running/marker.txt").read_text() == "running"
    assert (root / "sandbox/photoshop/marker.txt").read_text() == "photoshop"


@pytest.mark.asyncio
async def test_target_is_in_immutable_contract_and_no_directory_created_before_approval(tmp_path):
    bus = MessageBus(tmp_path / "logs", auth=None)
    orch = WorkspaceOrchestrator("default", bus)
    plan = TaskPlan("run", message({"user_request": "Build running", "session_id": "sess-run"}), subtasks=[action()])
    plan.project_spec = ProjectSpec("running", "Running", acceptance_contracts=["Un écran utilisable", "Les données persistent"])
    plan.execution_target = resolve_target(plan.id, {}, plan.subtasks, plan.project_spec)
    orch.task_plans[plan.id] = plan
    try:
        proposed = await orch._propose_contracts(plan, "Build running")
        assert proposed.metadata["execution_target"] == {"mode": "new", "path": "sandbox/running"}
        assert not plan.execution_target.directory.exists()
        # Selection and mutable original request no longer own the binding.
        plan.original_task.payload["project_path"] = "sandbox/blender"
        assert plan.execution_target.path == "sandbox/running"
        # A collision introduced while the user reviews the contract blocks approval.
        plan.execution_target.directory.mkdir(parents=True)
        orch._execute_ready_subtasks = AsyncMock()
        await orch._handle_contracts_approval({"plan_id": plan.id, "design_id": proposed.design_id, "approve": True})
        assert plan.awaiting_approval
        orch._execute_ready_subtasks.assert_not_called()
        assert "approval" not in default_repository().load_latest_spec(proposed.design_id).metadata
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_real_approval_dispatch_writes_only_to_the_bound_target(tmp_path):
    root = fs_api.workspace_root()
    blender = existing(root, "blender")
    bus = MessageBus(tmp_path / "logs", auth=None)
    orch = WorkspaceOrchestrator("default", bus)
    worker = PythonBrain("python_brain", bus, work_dir=root / "sandbox")
    orch.register_brain("python_brain")
    completed = asyncio.Event()
    async def observe(frame):
        if frame.payload.get("event") == "task.complete":
            completed.set()
    bus.subscribe("*", observe)
    await orch.start()
    await worker.start()
    try:
        plan = await orch._create_task_plan(message({
            "type": "batch_write_files", "brain": "python_brain", "user_request": "Write the marker",
            "project_target": {"mode": "new", "path": "sandbox/running"},
            "files": [{"path": "marker.txt", "content": "approved target only"}],
        }))
        plan.project_spec = ProjectSpec("running", "Marker", acceptance_contracts=["Le fichier existe", "Le contenu est préservé"])
        orch.task_plans[plan.id] = plan
        proposed = await orch._propose_contracts(plan, "Write the marker")
        assert not (root / "sandbox/running").exists()
        fs_api.set_current_project("sandbox/blender")
        await orch._handle_contracts_approval({"plan_id": plan.id, "design_id": proposed.design_id, "approve": True})
        await asyncio.wait_for(completed.wait(), 5)
        assert (root / "sandbox/running/marker.txt").read_text() == "approved target only"
        assert not (blender / "marker.txt").exists()
        assert plan.status == TaskStatus.COMPLETE
        recorded = default_repository().load_latest_spec(proposed.design_id)
        assert recorded.metadata["execution_target"]["path"] == "sandbox/running"
        assert recorded.metadata["approval"]["decision"] == "approved"
    finally:
        await worker.stop()
        await orch.stop()
        await bus.close()


def test_selected_project_metadata_is_not_a_fallback_without_a_binding():
    root = fs_api.workspace_root()
    existing(root, "blender")
    fs_api.set_current_project("sandbox/blender")
    subtask = action("edit_file")
    subtask.status = TaskStatus.COMPLETE
    subtask.result = {"success": True, "file_path": "main.py"}
    plan = TaskPlan("unbound", message({"project_path": "sandbox/blender"}), subtasks=[subtask])
    assert WorkspaceOrchestrator._project_result_metadata(plan) == {"runnable": False}
