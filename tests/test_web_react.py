"""A real React/TypeScript/Vite build tested in Chromium, without fake output."""

import json
from unittest.mock import AsyncMock

import pytest

from bigbrain.brains.web_app_brain import WebAppBrain
from bigbrain.bus.bus import MessageBus
from bigbrain.orchestrator.architect import ArchitectPhase
from bigbrain.verification.contracts import stack_contract
from bigbrain.verification.evidence import default_repository
from bigbrain.web import fs_api


def test_architect_defaults_to_react_typescript_vite_contract():
    spec = ArchitectPhase(llm_provider=None)._parse_spec(
        {
            "project_name": "tracker",
            "deliverable_type": "web_app",
            "file_specs": [],
        }
    )
    assert spec.web_stack == "react_vite"
    assert {"package.json", "tsconfig.json", "vite.config.ts", "src/App.tsx", "src/main.tsx"} <= {
        f.path for f in spec.file_specs
    }
    contract = stack_contract(spec)
    assert "React 19" in contract and "TypeScript" in contract and "Vite" in contract


@pytest.mark.asyncio
@pytest.mark.parametrize("type_error", [False, True])
async def test_react_build_browser_persistence_and_manual_rerun(tmp_path, monkeypatch, type_error):
    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path))
    target = tmp_path / "tracker"
    (target / "src").mkdir(parents=True)
    (target / "tests").mkdir()
    (target / "index.html").write_text(
        '<div id="root"></div><script type="module" src="/src/main.tsx"></script>'
    )
    (target / "src/main.tsx").write_text(
        "import {createRoot} from 'react-dom/client'; import App from './App'; import './styles.css'; createRoot(document.getElementById('root')!).render(<App/>);"
    )
    (target / "src/styles.css").write_text("body { margin: 0; } main { padding: 20px; }")
    (target / "src/App.tsx").write_text("""import {useState} from 'react';
export default function App() {
  const [done, setDone] = useState(localStorage.getItem('done') === 'yes');
  return <main><h1>Workout tracker</h1><button id="save" onClick={() => {localStorage.setItem('done','yes');setDone(true)}}>Complete</button><p id="state">{done ? 'Completed' : 'Pending'}</p></main>;
}""")
    (target / "tests/acceptance.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "cases": [
                    {
                        "name": "Real React state survives reload",
                        "steps": [{"op": "click", "selector": "#save"}, {"op": "reload"}],
                        "assertions": [{"op": "text", "selector": "#state", "value": "Completed"}],
                    }
                ],
            }
        )
    )
    provider = None
    if type_error:
        original = (target / "src/App.tsx").read_text()
        (target / "src/App.tsx").write_text("const invalid: number = 'bad';\n" + original)
        provider = AsyncMock()
        provider.chat_complete.return_value = json.dumps(
            {"files": [{"path": "src/App.tsx", "content": original}]}
        )
    brain = WebAppBrain("web", MessageBus(auth=None), work_dir=tmp_path, llm_provider=provider)
    try:
        result = await brain._assemble_and_preview(
            {"project_name": "tracker", "web_stack": "react_vite"}
        )
        assert result["success"], result.get("error")
        manifest = default_repository().load_manifest(result["verification"]["run_id"])
        assert {s.name for s in manifest.stages} >= {"typecheck", "build", "browser"}
        assert manifest.verdict == "passed"
        if type_error:
            parent = default_repository().load_manifest(manifest.parent_run_id)
            assert parent.verdict == "failed"
            assert next(s for s in parent.stages if s.name == "typecheck").status == "failed"
            provider.chat_complete.assert_awaited_once()
        assert (target / "dist/index.html").is_file()
        rerun = await fs_api.run_static_preview("tracker/index.html")
        assert rerun["ok"]
        process = fs_api._manual_web_previews.pop(target.as_posix())
        process.terminate()
        await process.wait()
    finally:
        await brain.cleanup()
