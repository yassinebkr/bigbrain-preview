import pytest

from bigbrain.orchestrator.architect import ArchitectPhase
from bigbrain.orchestrator.widget_proposals import widget_proposal, validate_widget_proposal
from bigbrain.web.run_history import conversation_activity
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.web.server import WebServer
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator


@pytest.mark.parametrize('widgets', [[], ['html'], ['console', 'console'], ['files', 'console', 'preview'], 'files', [None]])
def test_closed_catalog_rejects_unbounded_or_invalid_widgets(widgets):
    with pytest.raises(ValueError):
        widget_proposal(widgets)


@pytest.mark.parametrize('extra', [{'execute': True}, {'html': '<script/>'}, {'path': '../other'}, {'width': 1000}])
def test_proposals_have_no_geometry_content_or_action_authority(extra):
    with pytest.raises(ValueError):
        validate_widget_proposal({'version': 1, 'revision': 1, 'widgets': ['console'], **extra})


def test_invalid_ui_metadata_does_not_break_valid_architecture():
    spec = ArchitectPhase(None)._parse_spec({'project_name': 'tool', 'file_specs': [{'path': 'main.py'}], 'workspace_widgets': ['execute_shell']})
    assert spec.workspace_widgets is None
    assert spec.entry_point == 'main.py'
    accepted = ArchitectPhase(None)._parse_spec({'project_name': 'tool', 'file_specs': [{'path': 'main.py'}], 'workspace_widgets': ['console', 'verification']})
    assert accepted.to_dict()['workspace_widgets'] == ['console', 'verification']


@pytest.mark.asyncio
async def test_journal_restores_latest_valid_proposal_not_a_stale_or_foreign_one(tmp_path):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    async def emit(revision, widgets, session='s'):
        await bus.broadcast_event(source='orchestrator_default', workspace='default', event_type='workspace.proposal', payload={
            'session_id': session, 'task_id': 'run', 'producer': 'architect',
            'proposal': {'version': 1, 'revision': revision, 'widgets': widgets}})
    try:
        await emit(2, ['files'])
        await emit(1, ['console'])
        await emit(3, ['shell'])
        await emit(4, ['preview'], 'foreign')
        await bus.broadcast_event(source='python_brain_0', workspace='default', event_type='workspace.proposal', payload={
            'session_id': 's', 'task_id': 'run', 'producer': 'architect',
            'proposal': widget_proposal(['preview']) | {'revision': 99}})
        await bus.broadcast_event(source='test', event_type='task.complete', payload={'session_id': 's', 'task_id': 'run'})
        restored = conversation_activity(tmp_path / 'logs', 's', 0)
        proposals = [frame['payload']['proposal'] for frame in restored if frame['payload']['event'] == 'workspace.proposal']
        assert proposals == [{'version': 1, 'revision': 2, 'widgets': ['files']}]
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_architect_emits_correlated_suggestion_without_an_extra_llm_call(tmp_path):
    import json
    from unittest.mock import AsyncMock
    provider = AsyncMock()
    provider.chat_complete.return_value = json.dumps({
        'project_name': 'tool', 'deliverable_type': 'python',
        'file_specs': [{'path': 'main.py'}, {'path': 'tests/test_tool.py'}],
        'acceptance_contracts': ['Résultat utilisable', 'Cas limites vérifiés'],
        'workspace_widgets': ['console', 'verification']})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    orchestrator = WorkspaceOrchestrator('default', bus, llm_provider=provider)
    events = []
    async def capture(message):
        if message.payload.get('event') == 'workspace.proposal':
            events.append(message.payload)
    bus.subscribe('*', capture)
    try:
        await orchestrator._plan_project('plan-ui', 'Build tool', False, [], deliverable_type='python', session_id='s')
        assert provider.chat_complete.call_count == 1
        assert len(events) == 1
        assert events[0]['task_id'] == 'plan-ui'
        assert events[0]['session_id'] == 's'
        assert events[0]['proposal']['widgets'] == ['console', 'verification']
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_relay_checks_real_bus_source_not_only_producer_claim(tmp_path):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    server = WebServer(bus)
    payload = {'event': 'workspace.proposal', 'session_id': 's', 'task_id': 'r',
               'producer': 'architect', 'proposal': widget_proposal(['files'])}
    try:
        await server._on_bus_message(BusMessage(type=MessageType.EVENT, source='python_brain_0', target='*', workspace='default', payload=payload))
        assert not server._replay_buffer
        await server._on_bus_message(BusMessage(type=MessageType.EVENT, source='orchestrator_default', target='*', workspace='default', payload=payload))
        assert len(server._replay_buffer) == 1
    finally:
        await bus.close()
