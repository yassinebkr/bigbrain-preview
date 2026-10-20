"""Bounded architecture, compact web schema, actual wait/Stop regression tests."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
import httpx

from bigbrain.bus.bus import MessageBus
from bigbrain.orchestrator import architect as architecture
from bigbrain.orchestrator import orchestrator as orchestration


def web_spec():
    return json.dumps({
        "project_name": "running-tracker", "deliverable_type": "web_app",
        "acceptance_contracts": ["Les sorties sont conservées", "Les limites des rappels sont indiquées"],
        "file_specs": [{"path": "index.html"}, {"path": "src/App.tsx"},
                       {"path": "src/styles.css"}],
    })


@pytest.mark.asyncio
async def test_runtime_manifest_is_not_dispatched_as_worker_source():
    provider = AsyncMock()
    raw = {'project_name': 'repair', 'deliverable_type': 'python',
           'acceptance_contracts': ['Actual behaviour works', 'Tests pass'],
           'file_specs': [{'path': '.project.json'}, {'path': 'main.py'}, {'path': 'tests/test_main.py', 'dependencies': ['main.py']}],
           'entry_point': 'main.py'}
    provider.chat_complete.return_value = json.dumps(raw)
    spec = await architecture.ArchitectPhase(provider).design('Repair the missing manifest then fix the application', expected_deliverable='python')
    assert '.project.json' not in [f.path for f in spec.dependency_order()]
    assert provider.chat_complete.await_count == 1
    assert 'runtime-owned metadata' in provider.chat_complete.call_args.kwargs['messages'][0]['content']
    raw['file_specs'].append({'path': '.env'})
    provider.chat_complete.return_value = json.dumps(raw)
    with pytest.raises(ValueError, match='Unsafe project file path'):
        await architecture.ArchitectPhase(provider).design('Repair', expected_deliverable='python')


@pytest.mark.parametrize("value", ["", "NaN", "inf", "0", "-1", "301", "typo"])
def test_invalid_timeout_setting_has_a_safe_default(monkeypatch, value):
    monkeypatch.setenv("BIGBRAIN_ARCHITECT_TIMEOUT_SECONDS", value)
    assert architecture.architecture_timeout_seconds() == 120


@pytest.mark.parametrize("value", [5, 90, 120, 300])
def test_timeout_setting_is_operator_configurable(monkeypatch, value):
    monkeypatch.setenv("BIGBRAIN_ARCHITECT_TIMEOUT_SECONDS", str(value))
    assert architecture.architecture_timeout_seconds() == value


@pytest.mark.asyncio
async def test_web_prompt_avoids_python_schema_without_dropping_the_request():
    provider = AsyncMock()
    provider.chat_complete.return_value = web_spec()
    request = "Des sorties avec distance, durée et allure, persistance et limites des notifications."
    spec = await architecture.ArchitectPhase(provider).design(request, expected_deliverable="web_app")
    call = provider.chat_complete.call_args.kwargs
    prompt = call["messages"][0]["content"]
    assert "models.py" not in prompt
    assert "auth.py" not in prompt
    assert "TypeScript" in prompt
    assert "interfaces" in prompt
    assert "page closed" in prompt
    assert call["messages"][1]["content"] == request
    assert call["max_tokens"] == 4096
    assert spec.entry_point == "index.html"
    assert spec.acceptance_contracts
    assert spec.get_file_spec("tests/acceptance.json")
    spec.dependency_order()


@pytest.mark.asyncio
async def test_python_prompt_is_compact_but_keeps_interfaces_tests_and_safety():
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({
        "project_name": "gcode-report", "deliverable_type": "python",
        "acceptance_contracts": ["Analyse hors ligne", "Distingue inconnus et mesures"],
        "file_specs": [{"path": "main.py"}, {"path": "tests/test_report.py", "dependencies": ["main.py"]}],
        "entry_point": "main.py",
    })
    request = "Analyse G-code hors ligne, stdlib uniquement, sans commande imprimante."
    spec = await architecture.ArchitectPhase(provider).design(request, expected_deliverable="python")
    call = provider.chat_complete.call_args.kwargs
    prompt = call["messages"][0]["content"]
    assert len(prompt) < len(architecture.ARCHITECT_SYSTEM_PROMPT)
    for required in ["interfaces", "tests/test_", "acceptance_contracts", "safety", "without arguments"]:
        assert required in prompt
    assert "auth.py" not in prompt
    assert "React" not in prompt
    assert call["messages"][1]["content"] == request
    assert call["max_tokens"] == 4096
    assert spec.get_file_spec("tests/test_report.py")
    spec.dependency_order()


@pytest.mark.asyncio
async def test_structural_repair_shares_one_total_deadline(monkeypatch):
    monkeypatch.setenv("BIGBRAIN_ARCHITECT_TIMEOUT_SECONDS", "120")
    real_timeout = asyncio.timeout
    budgets = []
    def short_budget(seconds):
        budgets.append(seconds)
        return real_timeout(0.03)
    monkeypatch.setattr(architecture.asyncio, "timeout", short_budget)
    cancelled = asyncio.Event()
    calls = 0
    class Provider:
        async def chat_complete(self, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return "invalid specification"
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
    with pytest.raises(architecture.ArchitectureTimeout, match="Aucun contrat ni code"):
        await architecture.ArchitectPhase(Provider()).design("running app", expected_deliverable="web_app")
    assert budgets == [120]
    assert calls == 2
    assert cancelled.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimeoutError(), httpx.ReadTimeout("read timed out")])
async def test_provider_timeout_is_actionable_without_retry(error):
    provider = AsyncMock()
    provider.chat_complete.side_effect = error
    with pytest.raises(architecture.ArchitectureTimeout, match="fournisseur"):
        await architecture.ArchitectPhase(provider).design("running app", expected_deliverable="web_app")
    assert provider.chat_complete.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", [False, True])
async def test_architecture_wait_reports_elapsed_and_cleans_up_on_stop(tmp_path, monkeypatch, stop):
    monkeypatch.setattr(orchestration, "PLANNING_HEARTBEAT_SECONDS", 0.005)
    release, cancelled, heartbeat = asyncio.Event(), asyncio.Event(), asyncio.Event()
    class Provider:
        async def chat_complete(self, **kwargs):
            try:
                await release.wait()
                return web_spec()
            finally:
                cancelled.set()
    bus = MessageBus(tmp_path / "logs", auth=None)
    orch = orchestration.WorkspaceOrchestrator("default", bus, llm_provider=Provider())
    updates = []
    async def observe(message):
        data = message.payload
        if data.get("event") == "planning.stage":
            updates.append(data)
            heartbeat.set()
    bus.subscribe("*", observe)
    task = asyncio.create_task(orch._plan_project(
        "running-plan", "running app", False, [], deliverable_type="web_app", session_id="sess-running"))
    try:
        await asyncio.wait_for(heartbeat.wait(), timeout=2)
        assert updates[0]["session_id"] == "sess-running"
        assert updates[0]["elapsed_ms"] > 0
        assert updates[0]["status"] == "running"
        if stop:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            release.set()
            subtasks = await asyncio.wait_for(task, timeout=2)
            assert {s.brain_target for s in subtasks} == {"web_app_brain"}
        assert cancelled.is_set()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await bus.close()
