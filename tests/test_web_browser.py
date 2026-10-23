"""Real Chromium scenarios: persistence, failures, evidence and bounded repair."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bigbrain.brains.web_app_brain import WebAppBrain
from bigbrain.bus.bus import MessageBus
from bigbrain.verification.evidence import default_repository

SCRIPT = """const box = document.querySelector('#done');
box.checked = localStorage.getItem('done') === 'yes';
box.onchange = () => localStorage.setItem('done', box.checked ? 'yes' : 'no');"""


def project(root: Path, script: str = SCRIPT):
    target = root / "tracker"
    (target / "tests").mkdir(parents=True)
    (target / "index.html").write_text(
        '<main><h1>Tracker</h1><label><input id="done" type="checkbox">Done</label></main><script src="app.js"></script>'
    )
    (target / "styles.css").write_text("main {max-width:100%;}")
    (target / "app.js").write_text(script)
    (target / "tests/acceptance.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "cases": [
                    {
                        "name": "Progress persists across reload",
                        "steps": [
                            {"op": "check", "selector": "#done"},
                            {"op": "reload"},
                        ],
                        "assertions": [
                            {"op": "checked", "selector": "#done", "value": True},
                            {"op": "storage_equals", "key": "done", "value": "yes"},
                            {"op": "no_overflow"},
                        ],
                    }
                ],
            }
        )
    )
    return target


@pytest.mark.asyncio
async def test_real_browser_persistence_and_png_evidence(tmp_path):
    project(tmp_path)
    brain = WebAppBrain("web", MessageBus(auth=None), work_dir=tmp_path)
    try:
        result = await brain._assemble_and_preview({"project_name": "tracker"})
        assert result["success"], result.get("error")
        manifest = default_repository().load_manifest(result["verification"]["run_id"])
        assert manifest.verdict == "passed"
        png = next(ref for ref in manifest.artifacts if ref.media_type == "image/png")
        assert default_repository().get_artifact(png.sha256).startswith(b"\x89PNG")
    finally:
        await brain.cleanup()


@pytest.mark.asyncio
async def test_unbound_browser_failure_does_not_authorize_source_edits(tmp_path):
    target = project(tmp_path, "throw new Error('broken handler');")
    frozen = (target / "tests/acceptance.json").read_bytes()
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps(
        {"files": [{"path": "app.js", "content": SCRIPT}]}
    )
    brain = WebAppBrain("web", MessageBus(auth=None), work_dir=tmp_path, llm_provider=provider)
    try:
        result = await brain._assemble_and_preview({"project_name": "tracker"})
        assert result["success"] is False
        assert (target / "tests/acceptance.json").read_bytes() == frozen
        assert (target / 'app.js').read_text() == "throw new Error('broken handler');"
        manifest = default_repository().load_manifest(result["verification"]["run_id"])
        assert manifest.metadata["attempt"] == 1
        assert manifest.verdict == 'failed'
        provider.chat_complete.assert_not_awaited()
    finally:
        await brain.cleanup()


@pytest.mark.asyncio
async def test_browser_failure_blocks_delivery_and_stale_manifest(tmp_path):
    target = project(tmp_path, "throw new Error('broken handler');")
    (target / ".project.json").write_text(json.dumps({"verified": True}))
    brain = WebAppBrain("web", MessageBus(auth=None), work_dir=tmp_path)
    result = await brain._assemble_and_preview({"project_name": "tracker"})
    assert result["success"] is False
    assert result["runnable"] is False
    assert "broken handler" in result["error"]
    manifest = default_repository().load_manifest(result["verification"]["run_id"])
    assert (
        "broken handler"
        in next(stage for stage in manifest.stages if stage.name == "browser").details["error"]
    )
    assert json.loads((target / ".project.json").read_text())["verified"] is False
    assert brain._preview_process is None


@pytest.mark.asyncio
async def test_browser_unavailable_is_inconclusive_without_repair(tmp_path, monkeypatch):
    project(tmp_path)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "missing-browsers"))
    provider = AsyncMock()
    brain = WebAppBrain("web", MessageBus(auth=None), work_dir=tmp_path, llm_provider=provider)
    result = await brain._assemble_and_preview({"project_name": "tracker"})
    assert result["success"] is False
    assert result["verification"]["verdict"] == "inconclusive"
    provider.chat_complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_browser_stop_terminates_child_process(monkeypatch):
    from bigbrain.verification.web_gate import browser_report

    original_spawn = asyncio.create_subprocess_exec
    started = asyncio.Event()
    processes = []

    async def capture_spawn(*args, **kwargs):
        process = await original_spawn(*args, **kwargs)
        processes.append(process)
        started.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture_spawn)
    task = asyncio.create_task(
        browser_report(
            "http://127.0.0.1:3299",
            {
                "schema_version": 2,
                "cases": [{"name": "load", "assertions": [{"op": "visible", "selector": "main"}]}],
            },
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert processes[0].returncode is not None
