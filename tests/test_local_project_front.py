"""Selected local project routing through the production front decision path."""

import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.front.decision import FrontDecision
from bigbrain.front.front_brain import FrontBrain
from bigbrain.local_projects import default_registry


def intent(scope):
    return {'decision': {'operation': 'delegate', 'reply': 'Je prépare la correction.',
        'objective': 'Repair the selected Python project and verify its tests',
        'route': {'brain': 'python_brain', 'payload': {'type': 'maintain_project',
            'deliverable_type': 'python', 'entry_point': 'main.py', 'local_project': scope}}}}


@pytest.mark.asyncio
@pytest.mark.parametrize('selected', [True, False])
@pytest.mark.parametrize('deliverable', ['python', 'web_app'])
async def test_front_requires_current_conversation_selection(tmp_path, selected, deliverable):
    registry = default_registry()
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'main.py').write_text('print("private-code-body")\n')
    project = registry.attach(source, ('read', 'write', 'execute', 'transmit'))
    scope = {'project_id': project['id'], 'revision': project['revision']}
    if selected:
        registry.selection('s', project_id=project['id'], update=True)
    provider = AsyncMock()
    decision = intent(scope)
    if deliverable == 'web_app':
        decision['decision']['route']['brain'] = 'web_app_brain'
        decision['decision']['route']['payload'].update(deliverable_type='web_app', web_stack='static')
    provider.chat_complete.return_value = json.dumps(decision)
    bus = MessageBus(log_dir=tmp_path / 'logs')
    dispatched = []
    async def receive(frame):
        if frame.type == MessageType.TASK:
            dispatched.append(frame)
    bus.subscribe('orchestrator_default', receive)
    front = FrontBrain(bus, llm_provider=provider)
    front.register_brain('python_brain', 'Python specialist')
    front.register_brain('web_app_brain', 'Web specialist')
    await front._handle_ui_message(BusMessage(type=MessageType.TASK, source='morphable_ui',
        target='front_brain', payload={'text': 'Corrige ce projet', 'session_id': 's'}))
    assert bool(dispatched) is selected
    if selected:
        assert dispatched[0].payload['local_project'] == scope
        assert dispatched[0].payload['type'] == 'maintain_project'
        assert 'main.py' in str(provider.chat_complete.call_args_list)
    assert 'private-code-body' not in str(provider.chat_complete.call_args_list)
    assert front._attached_project_context.get() is None
    await bus.close()


def test_attached_route_rejects_an_additional_workspace_destination():
    data = intent({'project_id': 'p', 'revision': 1})
    data['decision']['project_target'] = {'mode': 'existing', 'path': 'sandbox/other'}
    with pytest.raises(ValidationError):
        FrontDecision.model_validate(data)
