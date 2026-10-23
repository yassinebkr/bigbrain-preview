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
    from bigbrain.brains.web_stack import REACT_FILES
    from bigbrain.execution_target import ExecutionTarget
    from bigbrain.project_inspection import digest
    from bigbrain.project_transaction import ProjectTransaction
    from bigbrain.verification.gate import RunGate
    from dataclasses import replace
    for path, content in REACT_FILES.items():
        (target / path).write_text(content)
    binding = replace(ExecutionTarget('existing', 'tracker', str(tmp_path)).prepare(), mode='new')
    spec = RunGate(default_repository()).build_spec('Persist the completed state across reload', ['index.html'])
    spec.metadata.update(business_criteria=['Completed state survives reload'], execution_target=binding.public())
    default_repository().save_spec(spec)
    spec = default_repository().approve_spec(spec.design_id, plan_id='react')
    transaction = ProjectTransaction.begin(binding, [])
    payload = {'project_name': 'tracker', 'web_stack': 'react_vite', 'user_request': spec.user_request,
        '_execution_target': binding.to_payload(), '_transaction': str(transaction.journal),
        'contract_revision': {'design_id': spec.design_id, 'revision': spec.revision}}
    provider = AsyncMock()
    actions = []
    if type_error:
        original = (target / "src/App.tsx").read_text()
        (target / "src/App.tsx").write_text("const invalid: number = 'bad';\n" + original)
        actions = [{'type': 'read', 'path': 'src/App.tsx'},
            {'type': 'patch', 'path': 'src/App.tsx', 'sha256': digest((target / 'src/App.tsx').read_text()),
             'edits': [{'old': "const invalid: number = 'bad';\n", 'new': ''}]}]

    async def respond(**kwargs):
        if 'independent acceptance reviewer' in kwargs['messages'][0]['content']:
            from bigbrain.llm.usage import UsageRecord, get_tracker
            get_tracker().record(UsageRecord(model_id='offline', provider='test', input_tokens=20,
                                            output_tokens=20, total_tokens=40))
            context = json.loads(kwargs['messages'][1]['content'])
            return json.dumps({'decision': 'pass', 'contradictions': [], 'coverage': [{
                'criterion_id': '0', 'tests': context['passing_tests'],
                'sources': ['src/App.tsx', 'tests/acceptance.json'],
                'reason': 'Real browser clicks save, reloads, and asserts Completed'}]})
        return json.dumps({'action': actions.pop(0), 'notebook': 'Repair reproduced type error'})
    provider.chat_complete.side_effect = respond
    brain = WebAppBrain("web", MessageBus(auth=None), work_dir=tmp_path, llm_provider=provider)
    try:
        with brain.execution_scope(payload):
            result = await brain._assemble_and_preview(payload)
        assert result["success"], result.get("error")
        manifest = default_repository().load_manifest(result["verification"]["run_id"])
        assert {s.name for s in manifest.stages} >= {"typecheck", "build", "browser"}
        assert manifest.verdict == "passed"
        if type_error:
            parent = default_repository().load_manifest(manifest.parent_run_id)
            assert parent.verdict == "failed"
            assert next(s for s in parent.stages if s.name == "typecheck").status == "failed"
            assert result['repair']['repair_rounds'] == 1
            assert not actions
        assert not (target / 'package-lock.json').exists()
        assert transaction.finish(commit=True)['state'] == 'committed'
        assert (target / "dist/index.html").is_file()
        rerun = await fs_api.run_static_preview("tracker/index.html")
        assert rerun["ok"]
        assert rerun['previewAvailable']
        assert not rerun['serverRunning']
        from bigbrain.web.preview_leases import PreviewLeases
        import httpx
        previews = PreviewLeases()
        lease = await previews.acquire(target / 'dist')
        try:
            async with httpx.AsyncClient() as client:
                page = await client.get(lease['previewUrl'])
                assert page.status_code == 200
                assert '/assets/' in page.text
        finally:
            await previews.release(lease['leaseId'])
    finally:
        await brain.cleanup()
        if json.loads(transaction.journal.read_text())['state'] == 'open':
            transaction.finish()
