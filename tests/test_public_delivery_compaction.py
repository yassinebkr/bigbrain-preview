"""Public worker output survives repeated context compaction and chat delivery."""
import json
from unittest.mock import AsyncMock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.bus.delivery import public_delivery, DeliveryUnavailable
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator,TaskPlan,SubTask,TaskStatus
from bigbrain.front.front_brain import FrontBrain
from bigbrain.research_acquisition import repository


def compact(result, kind='research'):
    message = BusMessage(type=MessageType.TASK,source='front_brain',target='orchestrator_default',
                         payload={'session_id':'owner'})
    plan = TaskPlan(id='plan',original_task=message,subtasks=[SubTask(id='step',description='Task',
        brain_target=kind,payload={'type':kind},status=TaskStatus.COMPLETE,result=result)])
    orch = WorkspaceOrchestrator.__new__(WorkspaceOrchestrator)
    orch._compact_plan_context(plan)
    return orch,plan


@pytest.mark.parametrize('kind', ['research','taskboard','python'])
@pytest.mark.parametrize('status',['completed','partial'])
def test_exact_public_output_and_durable_archive_survive_compaction(kind,status):
    message = 'Public findings with citations and qualifications. ' * 100
    data = dict(success=True,research_status=status,public_message=message,
                evidence={'original':'large evidence '*4000},research_id='research',attempt_id='attempt')
    orch,plan = compact({'success':True,'data':data},kind)
    result = plan.get_results()['step']
    assert result['_compacted']
    assert message not in json.dumps(result)
    assert public_delivery(result,session_id='owner') == message
    assert result['delivery']['status'] == status
    reference = result['delivery']['result_artifact']
    assert json.loads(repository().get_artifact(reference['sha256'])) == data
    snapshot = json.dumps(result,sort_keys=True)
    orch._compact_plan_context(plan)
    assert json.dumps(plan.get_results()['step'],sort_keys=True) == snapshot
    with pytest.raises(DeliveryUnavailable,match='another conversation'):
        public_delivery(result,session_id='other')


@pytest.mark.asyncio
async def test_front_delivers_compacted_public_output_without_summary_or_model(tmp_path):
    public = 'A qualified result. [Source](https://docs.test/reference)'
    _,plan = compact(dict(success=True,public_message=public,research_status='completed'))
    bus = MessageBus(tmp_path/'logs',auth=None)
    front = FrontBrain(bus,llm_provider=AsyncMock())
    front._emit_chat_message = AsyncMock()
    front._summarize_result = AsyncMock(side_effect=AssertionError('Public output must remain exact'))
    try:
        await front._handle_task_result(BusMessage(type=MessageType.RESULT,source='orchestrator_default',
            target='front_brain',payload={'success':True,'results':plan.get_results(),'session_id':'owner'}))
        front._emit_chat_message.assert_awaited_once_with('assistant',public,session_id='owner')
    finally:
        await bus.close()


def test_archive_failure_retains_original_result(monkeypatch):
    def failed(*args,**kwargs):
        raise OSError('Storage unavailable')
    monkeypatch.setattr('bigbrain.bus.delivery.archive_delivery',failed)
    original = {'success':True,'public_message':'Available output'}
    _,plan = compact(original)
    assert plan.subtasks[0].result is original
    assert public_delivery(original) == 'Available output'
