"""Run the shared repair engine on an approved attached-project working copy."""

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from .execution_target import ExecutionTarget
from .local_projects import ProjectAccessError, ProjectFiles
from .local_project_checks import run_project_tests
from .local_project_patches import verify_and_apply
from .local_project_provider import SourceBoundProvider
from .local_project_runner import ProjectRunner
from .maintenance import maintain, ProjectTools
from .project_transaction import ProjectTransaction, active_transaction
from .verification.evidence import default_repository
from .verification.semantics import review_semantics


@dataclass(frozen=True)
class AttachedWorkspaceTarget(ExecutionTarget):
    registry: object = field(default=None, repr=False, compare=False)
    snapshot_id: str = ''
    source_id: str = ''
    source_revision: int = 0

    def validate(self):
        super().validate()
        with self.registry.access(self.snapshot_id, 1, 'read'):
            pass

    def public(self):
        return {'mode': 'attached', 'project_id': self.source_id, 'revision': self.source_revision}

    def to_payload(self):
        # Recovery uses the runtime-owned working copy and its original journal.
        return ExecutionTarget(self.mode, self.path, self.root, self.device, self.inode).to_payload()


async def maintain_attached(brain, registry, project_id, revision, payload):
    """Use immutable source consent, isolated checks and the shared repair loop."""
    repository = default_repository()
    reference = payload.get('contract_revision') or {}
    approved = repository.load_spec(reference.get('design_id', ''), reference.get('revision', 0))
    scope = {'project_id': project_id, 'revision': revision}
    if (approved is None or approved.metadata.get('local_project') != scope
            or approved.user_request != payload.get('user_request')
            or approved.metadata.get('approval', {}).get('decision') != 'approved'):
        raise ProjectAccessError('An approved contract for this attached project revision is required')
    deliverable = payload.get('deliverable_type')
    if deliverable not in {'python', 'web_app'} or deliverable != brain.project_kind:
        raise ProjectAccessError('Attached maintenance requires the matching specialist')
    delivery = approved.metadata.get('delivery', {})
    if (delivery.get('deliverable_type') != deliverable
            or delivery.get('entry_point') != payload.get('entry_point')
            or delivery.get('executable') != payload.get('executable', True)
            or delivery.get('web_stack', 'static') != payload.get('web_stack', 'static')):
        raise ProjectAccessError('Attached delivery settings differ from the approved contract')
    for right in ('read', 'write', 'execute', 'transmit'):
        with registry.access(project_id, revision, right):
            pass
    provider = SourceBoundProvider(brain.llm_provider, registry, project_id, revision, approved)
    consent = approved.metadata['source_transmission']
    snapshot = registry.create_snapshot(project_id, revision,
                                        allowed_versions=consent['source_versions'])
    directory = Path(snapshot['root'])
    identity = directory.stat()
    target = AttachedWorkspaceTarget('existing', directory.name, str(directory.parent),
        identity.st_dev, identity.st_ino, registry, snapshot['id'], project_id, revision)
    transaction = ProjectTransaction.begin(target, [])
    stage_tools = ProjectTools(target)
    baseline = {path: stage_tools.source(path) for path in stage_tools.inventory()}
    baseline_artifact = repository.put_artifact(json.dumps(baseline, ensure_ascii=False).encode(),
        name='attached-baseline.json', media_type='application/json')

    class Worker:
        llm_provider = provider
        model = getattr(brain, 'model', None)
        _directory_context = SimpleNamespace(get=lambda: target)

        @property
        def _cancelled(self):
            return brain._cancelled

        async def send_progress(self, data):
            await brain.send_progress({**data, 'local_project': scope})

        async def send_event(self, event, data):
            await brain.send_event('workspace.candidate_written' if event == 'workspace.file_written' else event,
                                   {**data, 'local_project': scope})

        async def maintenance_prepare(self, data):
            return {'status': 'inconclusive', 'cause': 'environment_blocked', 'next_action': 'stop',
                    'reason': 'Prepare the attached project environment before resuming this contract'}

    initial_diagnostic = None
    framework = None

    async def diagnose():
        nonlocal initial_diagnostic, framework
        if deliverable == 'web_app':
            from .local_project_web import run_web_tests
            result = await run_web_tests(registry, snapshot['id'], 1, payload['entry_point'],
                                         web_stack=payload.get('web_stack', 'static'))
        else:
            result = await run_project_tests(registry, snapshot['id'], 1)
        framework = result.get('framework')
        if initial_diagnostic is None:
            artifact = repository.put_artifact(json.dumps(result, ensure_ascii=False).encode(),
                name='attached-initial-diagnostic.json', media_type='application/json')
            initial_diagnostic = artifact.sha256
        return result

    async def verify(tools):
        tests = await diagnose()
        failures = []
        stages = [{'name': 'tests', 'status': tests['status'], 'details': tests}]
        if tests['status'] != 'passed':
            failures.append({'stage': 'tests', **stages[-1]})
        entry = payload.get('entry_point')
        if deliverable == 'python' and payload.get('executable', True):
            if not isinstance(entry, str) or entry not in tools.inventory():
                failures.append({'stage': 'entry_point', 'status': 'inconclusive',
                    'details': {'cause': 'environment_blocked', 'next_action': 'stop',
                                'reason': 'Declare an inspected Python entry point'}})
            else:
                run = await ProjectRunner(registry).run(snapshot['id'], 1, ['python', '-u', entry])
                stages.append({'name': 'entry_point', 'status': 'passed' if run['exitCode'] == 0 else 'failed',
                               'details': run})
                if run['exitCode'] != 0:
                    failures.append({'stage': 'entry_point', **stages[-1]})
        if not failures:
            sources = {path: tools.source(path) for path in tools.inventory()}
            versions = {path: hashlib.sha256(text.encode()).hexdigest() for path, text in sources.items()}
            original_versions = {path: hashlib.sha256(text.encode()).hexdigest() for path, text in baseline.items()}
            lineage = {'sources': baseline, 'artifact_sha256': baseline_artifact.sha256,
                'source_hashes': original_versions, 'current_hashes': versions,
                'revision': hashlib.sha256(json.dumps(original_versions, sort_keys=True).encode()).hexdigest(),
                'current_revision': hashlib.sha256(json.dumps(versions, sort_keys=True).encode()).hexdigest(),
                'initial_diagnostic': {'artifact_sha256': initial_diagnostic, 'source_hashes': original_versions}}
            stage = await review_semantics(provider, request=approved.user_request,
                contracts=approved.metadata.get('business_criteria') or approved.contracts,
                sources=sources, tests=tests, progressive=True, runtime_evidence={'_baseline': lineage})
            stages.append({'name': 'semantics', 'status': stage.status, 'details': stage.details})
            if stage.status != 'passed':
                failures.append({'stage': 'semantics', **stages[-1]})
        return {'success': not failures, 'verification': {'verdict': 'passed' if not failures else 'failed',
                 'stages': stages, 'failures': failures},
                **({'error': 'Attached project verification remains incomplete'} if failures else {})}

    token = active_transaction.set(str(transaction.journal))
    try:
        result = await maintain(Worker(), payload, diagnose=diagnose, verify=verify)
        if result.get('success'):
            provider.check()
            tools = ProjectTools(target)
            patches = [{'path': path, 'sha256': consent['source_versions'].get(path),
                        'content': tools.source(path)} for path, version in tools.fingerprints().items()
                       if consent['source_versions'].get(path) != version]
            if patches:
                command = (['browser'] if deliverable == 'web_app' else
                    ['python', '-m', 'unittest', 'discover'] if framework == 'unittest' else ['python', '-m', 'pytest', '-q'])
                checks = [command]
                if deliverable == 'python' and payload.get('executable', True):
                    checks.append(['python', '-u', payload['entry_point']])
                approved_tests = [change['path'] for change in approved.metadata.get('maintenance', {}).get('test_changes', [])]
                publication = await verify_and_apply(registry, project_id, revision, patches, checks,
                    approved_tests=approved_tests, web_entry=payload['entry_point'] if deliverable == 'web_app' else None,
                    web_stack=payload.get('web_stack', 'static'))
                result['success'] = publication['state'] == 'committed'
                result['publication'] = publication
            else:
                result['publication'] = {'state': 'unchanged', 'changedPaths': []}
        artifact = repository.put_artifact(json.dumps(result, ensure_ascii=False).encode(),
            name='attached-maintenance-result.json', media_type='application/json')
        # Detailed source diagnostics remain in local evidence for the user.
        public = {'success': bool(result.get('success')), 'local_project': scope,
                  'maintenance_status': 'verified' if result.get('success') else result.get('maintenance_status', 'incomplete'),
                  'evidence_artifact_sha256': artifact.sha256,
                  'verification': {'verdict': 'passed' if result.get('success') else 'inconclusive',
                                   'stages': [{'name': stage['name'], 'status': stage['status']}
                                              for stage in (result.get('verification') or {}).get('stages', [])]},
                  'changed_paths': result.get('publication', {}).get('changedPaths', [])}
        if not public['success']:
            if result.get('publication', {}).get('state') == 'incomplete':
                public['verification']['stages'].append({'name': 'publication', 'status': 'failed'})
            public['error'] = 'Attached project maintenance remains incomplete; local evidence contains the diagnostic'
        else:
            await brain.send_event('workspace.local_project_updated', public)
        return public
    finally:
        active_transaction.reset(token)
        transaction.finish()
        registry.change(snapshot['id'], 1, state='detached')
