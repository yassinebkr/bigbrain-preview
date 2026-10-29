"""Attached source consent through the orchestrator proposal boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.local_projects import ProjectRegistry
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
from bigbrain.verification.evidence import default_repository


@pytest.mark.asyncio
async def test_attached_plan_records_runtime_inventory_before_source_calls(tmp_path, monkeypatch):
    import bigbrain.local_projects as projects
    import bigbrain.verification.contracts as contracts

    source = tmp_path / 'sources'
    source.mkdir()
    (source / 'main.py').write_text('print("private-source-marker")\n')
    registry = ProjectRegistry(tmp_path / 'state' / 'registry.json')
    project = registry.attach(source, ('read', 'write', 'execute', 'transmit'))
    monkeypatch.setattr(projects, 'default_registry', lambda: registry)
    drafting = AsyncMock(return_value=['The entry point produces the approved result'])
    monkeypatch.setattr(contracts, 'draft_contracts', drafting)
    provider = SimpleNamespace(entry=SimpleNamespace(provider='openai_compat',
        base_url='https://recipient.invalid/v1'))
    orchestrator = WorkspaceOrchestrator('test', MessageBus(log_dir=tmp_path / 'logs'))
    orchestrator.specialist_provider = lambda name: provider
    message = BusMessage(type=MessageType.TASK, source='front_brain', target=orchestrator.name,
        payload={'type': 'maintain_project', 'user_request': 'Repair the current project',
            'deliverable_type': 'python', 'entry_point': 'main.py',
            'local_project': {'project_id': project['id'], 'revision': 1},
            'source_transmission': {'recipient': 'model-supplied-value'}})
    plan = await orchestrator._create_task_plan(message)
    assert plan.execution_target is None
    assert plan.source_transmission['recipient']['endpoint'] == 'https://recipient.invalid/v1'
    assert list(plan.source_transmission['source_versions']) == ['main.py']
    spec = await orchestrator._propose_contracts(plan, message.payload['user_request'])
    assert spec.metadata['source_transmission'] == plan.source_transmission
    assert spec.metadata['local_project'] == message.payload['local_project']
    assert 'private-source-marker' not in str(drafting.call_args_list)
    assert plan.awaiting_approval
    assert 'approval' not in spec.metadata

    # A changed source version creates a distinct immutable proposal revision.
    (source / 'main.py').write_text('print("second-source-marker")\n')
    next_plan = await orchestrator._create_task_plan(message)
    next_spec = await orchestrator._propose_contracts(next_plan, message.payload['user_request'])
    assert next_spec.revision == spec.revision + 1
    assert default_repository().load_spec(spec.design_id, spec.revision).metadata == spec.metadata
