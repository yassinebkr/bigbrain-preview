"""Real browser checks and publication against disposable attached web projects."""

import hashlib
import json

import pytest

from bigbrain.local_projects import ProjectRegistry
from bigbrain.local_project_web import run_web_tests
from bigbrain.local_project_patches import verify_and_apply


def setup(tmp_path):
    root = tmp_path / 'web-source'
    (root / 'tests').mkdir(parents=True)
    (root / 'index.html').write_text('<main><button id="add">Add</button><p id="count">0</p></main>'
        '<script src="app.js"></script>')
    (root / 'app.js').write_text('document.querySelector("#add").onclick = () => '
        'document.querySelector("#count").textContent = "0";')
    (root / 'tests/acceptance.json').write_text(json.dumps({'schema_version': 2, 'cases': [
        {'name': 'increment', 'steps': [{'op': 'click', 'selector': '#add'}],
         'assertions': [{'op': 'text', 'selector': '#count', 'value': '1'}]}]}))
    registry = ProjectRegistry(tmp_path / 'state' / 'registry.json')
    project = registry.attach(root, ('read', 'write', 'execute'))
    return root, registry, project


@pytest.mark.asyncio
async def test_browser_defect_is_reproduced_then_verified_before_publication(tmp_path):
    root, registry, project = setup(tmp_path)
    result = await run_web_tests(registry, project['id'], 1, 'index.html')
    assert result['status'] == 'failed', result
    assert result['cause'] == 'reproduced_defect'
    patch = {'path': 'app.js', 'sha256': hashlib.sha256((root / 'app.js').read_bytes()).hexdigest(),
        'content': 'document.querySelector("#add").onclick = () => document.querySelector("#count").textContent = "1";'}
    published = await verify_and_apply(registry, project['id'], 1, [patch], [['browser']], web_entry='index.html')
    assert published['state'] == 'committed', published
    assert [check['phase'] for check in published['checks']] == ['candidate', 'published']
    assert all(check['passed_cases'] == ['increment'] for check in published['checks'])
    assert (root / 'app.js').read_text() == patch['content']
    assert registry.list() == [registry.get(project['id'])]


@pytest.mark.asyncio
async def test_missing_browser_scenarios_stays_incomplete(tmp_path):
    root, registry, project = setup(tmp_path)
    (root / 'tests/acceptance.json').unlink()
    result = await run_web_tests(registry, project['id'], 1, 'index.html')
    assert result['status'] == 'inconclusive'
    assert result['cause'] == 'missing_test'
    assert result['next_action'] == 'add_validation'


@pytest.mark.asyncio
async def test_preview_capability_and_revocation_close_active_browser(tmp_path, monkeypatch):
    import asyncio
    import httpx
    from urllib.parse import urlsplit
    import bigbrain.local_project_web as module
    from bigbrain.local_projects import ProjectAccessError

    _, registry, project = setup(tmp_path)
    observed = {}
    async def inspect(url, acceptance):
        observed['url'] = url
        base = urlsplit(url)
        plain = f'{base.scheme}://{base.netloc}/index.html'
        async with httpx.AsyncClient(trust_env=False) as client:
            assert (await client.get(plain)).status_code == 403
            response = await client.get(url)
            assert response.status_code == 200
            assert (await client.get(f'{base.scheme}://{base.netloc}/app.js')).status_code == 200
        registry.change(project['id'], 1, state='revoked')
        try:
            await asyncio.Event().wait()
        finally:
            observed['cancelled'] = True
    monkeypatch.setattr(module, 'browser_report', inspect)
    with pytest.raises(ProjectAccessError, match='grant unavailable'):
        await run_web_tests(registry, project['id'], 1, 'index.html')
    assert observed['cancelled']
    async with httpx.AsyncClient(trust_env=False) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get(observed['url'])


@pytest.mark.asyncio
async def test_web_specialist_uses_shared_repair_and_independent_review(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from bigbrain.brains.web_app_brain import WebAppBrain
    from bigbrain.bus.bus import MessageBus
    from bigbrain.bus.message import BusMessage, MessageType
    from bigbrain.local_project_transmission import prepare_source_consent, provider_recipient
    from bigbrain.verification.evidence import default_repository
    from bigbrain.verification.gate import RunGate
    import bigbrain.local_projects as projects

    root, registry, project = setup(tmp_path)
    registry.change(project['id'], 1, rights=('read', 'write', 'execute', 'transmit'))
    before = (root / 'app.js').read_text()
    class Provider:
        entry = SimpleNamespace(provider='openai_compat', base_url='https://recipient.invalid/v1')
        worker_step = 0
        review_step = 0
        async def chat_complete(self, **kwargs):
            from bigbrain.llm.usage import UsageRecord, get_tracker
            get_tracker().record(UsageRecord(model_id='offline-protocol', provider='test',
                input_tokens=100, output_tokens=30, total_tokens=130))
            if kwargs['tool_schema']['name'] == 'project_maintenance_step':
                self.worker_step += 1
                action = ({'type': 'read', 'path': 'app.js'} if self.worker_step == 1 else
                    {'type': 'patch', 'path': 'app.js', 'sha256': hashlib.sha256(before.encode()).hexdigest(),
                     'edits': [{'old': 'textContent = "0"', 'new': 'textContent = "1"'}]})
                return json.dumps({'action': action, 'notebook': 'Repair the reproduced increment failure'})
            self.review_step += 1
            if self.review_step == 1:
                return json.dumps({'action': {'type': 'read_many', 'pages': [
                    {'path': p, 'start': 1, 'count': 80} for p in ['index.html', 'app.js', 'tests/acceptance.json']]},
                    'notebook': 'Inspect the handler and executed assertion'})
            return json.dumps({'action': None, 'decision': 'pass', 'contradictions': [], 'missing_evidence': [],
                'notebook': 'The browser case exercises the real click handler',
                'coverage': [{'criterion_id': '0', 'tests': ['increment'], 'runtime': [],
                    'sources': ['app.js', 'tests/acceptance.json'],
                    'reason': 'Clicking Add sets the counter to one, asserted by the executed browser case'}]})
    provider = Provider()
    scope = {'project_id': project['id'], 'revision': 2}
    repository = default_repository()
    request = 'Repair the Add button so it displays one after clicking'
    spec = RunGate(repository).build_spec(request, ['index.html'])
    spec.metadata.update(local_project=scope, business_criteria=['Clicking Add displays one'],
        delivery={'deliverable_type': 'web_app', 'entry_point': 'index.html', 'executable': True, 'web_stack': 'static'},
        source_transmission=prepare_source_consent(registry, project['id'], 2, provider_recipient(provider)))
    repository.save_spec(spec)
    approved = repository.approve_spec(spec.design_id, plan_id='attached-web')
    monkeypatch.setattr(projects, 'default_registry', lambda: registry)
    brain = WebAppBrain('web_app_brain_0', MessageBus(log_dir=tmp_path / 'logs'),
                        work_dir=tmp_path / 'worker', llm_provider=provider)
    result = await brain.handle_task(BusMessage(type=MessageType.TASK, source='orchestrator', target=brain.name,
        payload={'type': 'maintain_project', 'user_request': request, 'deliverable_type': 'web_app',
            'local_project': scope, 'entry_point': 'index.html', 'web_stack': 'static',
            'contract_revision': {'design_id': approved.design_id, 'revision': approved.revision}}))
    assert result['success'], result
    assert result['changed_paths'] == ['app.js']
    assert provider.worker_step == provider.review_step == 2
    assert 'textContent = "1"' in (root / 'app.js').read_text()
