import json
from pathlib import Path

import pytest

from bigbrain.brains.web_app_brain import WebAppBrain
from bigbrain.bus.bus import MessageBus
from bigbrain.orchestrator.architect import ArchitectPhase
from bigbrain.web import fs_api


def _write_web_project(root: Path, name: str = "fitness") -> tuple[Path, list[dict]]:
    project = root / name
    (project / "tests").mkdir(parents=True)
    files = {
        "index.html": '<!doctype html><main><h1>Plan</h1><button id="next">Next</button></main><link rel="stylesheet" href="styles.css"><script src="app.js"></script>',
        "styles.css": "button:focus-visible { outline: 2px solid blue; }\n",
        "app.js": "document.querySelector('#next').addEventListener('click', () => {});\n",
        "tests/acceptance.json": json.dumps({"cases": [{"name": "advance workout", "assertions": ["button advances the workout"]}]}),
    }
    for rel, content in files.items():
        target = project / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return project, [{"path": path} for path in files]


def test_web_project_validation_checks_browser_artifacts(tmp_path):
    project, files = _write_web_project(tmp_path)
    result = WebAppBrain.validate_project(project, files)
    assert result["passed"] is True
    assert result["acceptance"]["cases"][0]["name"] == "advance workout"


def test_web_project_validation_rejects_broken_local_asset(tmp_path):
    project, files = _write_web_project(tmp_path)
    (project / "index.html").write_text('<main></main><script src="missing.js"></script>')
    result = WebAppBrain.validate_project(project, files)
    assert result["passed"] is False
    assert "missing local asset: missing.js" in "; ".join(result["errors"])


@pytest.mark.asyncio
async def test_web_app_brain_creates_verified_preview_manifest(tmp_path):
    _, files = _write_web_project(tmp_path)
    brain = WebAppBrain("web_app_test", MessageBus(auth=None), "default", work_dir=tmp_path)
    result = await brain._assemble_and_preview({"project_name": "fitness", "all_files": files})
    try:
        assert result["success"] is True
        assert result["runnable"] is True
        assert result["preview_url"].startswith("http://127.0.0.1:")
        manifest = json.loads((tmp_path / "fitness" / ".project.json").read_text())
        assert manifest["deliverable_type"] == "web_app"
        assert manifest["run"] == {"kind": "static_preview"}
    finally:
        await brain.cleanup()


@pytest.mark.asyncio
async def test_manual_run_starts_verified_web_preview(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
    project, _ = _write_web_project(tmp_path)
    (project / ".project.json").write_text(json.dumps({
        "name": "fitness", "deliverable_type": "web_app",
        "entry_point": "index.html", "run": {"kind": "static_preview"},
        "verified": True,
    }))
    result = await fs_api.run_static_preview("fitness/index.html")
    process = fs_api._manual_web_previews.pop(project.as_posix())
    try:
        assert result["ok"] is True
        assert result["previewUrl"].startswith("http://127.0.0.1:")
    finally:
        process.terminate()
        await process.wait()


def test_architect_repairs_minimal_web_spec_with_required_files():
    architect = ArchitectPhase(llm_provider=None)
    spec = architect._parse_spec({
        "project_name": "fitness",
        "description": "interactive plan",
        "deliverable_type": "web_app",
        "interaction_mode": "browser",
        "file_specs": [{"path": "app.js", "purpose": "interaction"}],
        "entry_point": "index.html",
    })
    paths = {item.path for item in spec.file_specs}
    assert spec.deliverable_type == "web_app"
    assert spec.interaction_mode == "browser"
    assert {"index.html", "styles.css", "app.js", "tests/acceptance.json"} <= paths
