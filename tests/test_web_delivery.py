"""Exercise the real worker -> bus -> orchestrator -> terminal UI event path."""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from bigbrain.brains.web_acceptance import normalize_acceptance
from bigbrain.brains.web_app_brain import WebAppBrain
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, SubTask, TaskStatus
from bigbrain.orchestrator.architect import ArchitectPhase


@pytest.mark.parametrize("document", [
    {"cases": [{"name": "load", "assertions": ["main visible"]}]},
    {"tests": [{"title": "load", "steps": [{"action": "assertVisible", "selector": "main"}]}]},
    {"acceptanceCriteria": [{"title": "load", "steps": ["open"], "expectedResults": ["main visible"]}]},
])
def test_legacy_formats_normalize_to_versioned_contract(document):
    normalized = normalize_acceptance(document)
    assert normalized["schema_version"] == 1
    assert normalized["cases"][0]["name"] == "load"
    assert normalize_acceptance(normalized) == normalized


@pytest.mark.parametrize("document", [
    [], {"cases": []}, {"cases": "load"},
    {"cases": [{"name": "load", "assertions": "not an array"}]},
    {"cases": [{"name": "load", "assertions": [""]}]},
    {"schema_version": 2, "cases": [{"name": "load", "assertions": ["ok"]}]},
    {"schema_version": 1, "cases": [{"name": "load", "steps": ["open"]}]},
])
def test_malformed_contracts_fail_explicitly(document):
    with pytest.raises(ValueError):
        normalize_acceptance(document)


def test_architect_enforces_contract_on_already_declared_acceptance_file():
    spec = ArchitectPhase(llm_provider=None)._parse_spec({
        "project_name": "excel", "deliverable_type": "web_app",
        "file_specs": [{"path": "tests/acceptance.json",
                        "implementation_notes": "invent a schema"}],
    })
    acceptance = next(file for file in spec.file_specs if file.path == "tests/acceptance.json")
    assert '"schema_version":2' in acceptance.implementation_notes
    assert "invent a schema" not in acceptance.implementation_notes


@pytest.mark.asyncio
async def test_generated_acceptance_is_canonical_before_file_written(tmp_path):
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({"acceptanceCriteria": [{
        "title": "load", "steps": ["open"], "expectedResults": ["main visible"],
    }]})
    brain = WebAppBrain("web", MessageBus(auth=None), work_dir=tmp_path,
                        llm_provider=provider)
    brain.send_event = AsyncMock()
    await brain._write_web_file({"project_name": "course", "file_path": "tests/acceptance.json"})
    written = json.loads((tmp_path / "course/tests/acceptance.json").read_text())
    assert written["schema_version"] == 1
    assert written["cases"][0]["assertions"] == ["main visible"]
    prompt = provider.chat_complete.call_args.kwargs["messages"][1]["content"]
    assert '"schema_version":2' in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "missing_asset", "invalid_contract"])
async def test_real_assembly_delivers_truthful_terminal_event(tmp_path, monkeypatch, failure):
    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
    project = tmp_path / "sandbox" / "excel"
    (project / "tests").mkdir(parents=True)
    (project / "index.html").write_text('<main>Excel</main><script src="app.js"></script>')
    (project / "styles.css").write_text("main {color: black}")
    (project / "app.js").write_text("document.title = 'Excel';")
    (project / "tests/acceptance.json").write_text(json.dumps({"schema_version": 2, "cases": [{
        "name": "load", "steps": [], "assertions": [{"op": "visible", "selector": "main"}],
    }]} if failure != "invalid_contract" else {"cases": []}))
    if failure == "missing_asset":
        (project / "index.html").write_text('<main>Excel</main><script src="missing.js"></script>')

    bus = MessageBus(log_dir=tmp_path / "logs", auth=None)
    brain = WebAppBrain("web_worker", bus, "default", work_dir=tmp_path / "sandbox")
    orch = WorkspaceOrchestrator("default", bus)
    orch._extract_learnings = AsyncMock()
    original = BusMessage(type=MessageType.TASK, source="test_ui", target=orch.name,
                          payload={"session_id": "excel-session"})
    step = SubTask(id="assembly", description="assemble Excel", brain_target=brain.name,
                   payload={"type": "assemble_and_preview", "project_name": "excel"})
    plan = TaskPlan(id="excel-plan", original_task=original, subtasks=[step], status=TaskStatus.RUNNING)
    orch.task_plans[plan.id] = plan
    events = []
    finished = asyncio.Event()

    async def observe(message):
        events.append(message)
        if message.payload.get("event") in {"task.complete", "task.failed"}:
            finished.set()

    bus.subscribe("*", observe)
    await orch.start()
    await brain.start()
    orch.register_brain(brain.name, {"type": "WebAppBrain"})
    try:
        await orch._execute_ready_subtasks(plan)
        await asyncio.wait_for(finished.wait(), timeout=5)
        terminal = next(m.payload for m in events if m.payload.get("event") in {"task.complete", "task.failed"})
        reply = next(m.payload for m in events if m.type == MessageType.RESULT and m.target == "test_ui")
        if failure:
            assert terminal["event"] == "task.failed"
            assert terminal["runnable"] is False
            assert reply["success"] is False
            assert ("missing local asset" if failure == "missing_asset" else "acceptance cases") in terminal["error"]
            assert not (project / ".project.json").exists()
        else:
            assert terminal["event"] == "task.complete"
            assert terminal["runnable"] is True
            assert terminal["project_path"] == "sandbox/excel"
            assert terminal["entry_point"] == "index.html"
            assert terminal["deliverable_type"] == "web_app"
            async with httpx.AsyncClient() as client:
                response = await client.get(terminal["preview_url"])
                assert response.status_code == 200
                assert "Excel" in response.text
            manifest = json.loads((project / ".project.json").read_text())
            assert manifest["browser_tests_executed"] is True
    finally:
        await brain.cleanup()
        await brain.stop()
        await orch.stop()
