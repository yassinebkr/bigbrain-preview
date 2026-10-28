"""Direct worker delivery, checkpoint ownership and terminal progress contracts."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from bigbrain.brains.researcher import ResearcherBrain
from bigbrain.bus.auth import BusAuth
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.research import PageReader, ResearchState
from tests.test_research_direct_journey import FixtureFetcher, ScriptedAdapter, URL


@pytest.mark.asyncio
async def test_default_direct_worker_settles_over_authenticated_bus_and_resumes(tmp_path, monkeypatch):
    adapters = []
    def adapter(runtime, provider):
        value = ScriptedAdapter()
        adapters.append(value)
        return value
    monkeypatch.setattr('bigbrain.research_direct_model.DirectModelAdapter', adapter)
    auth = BusAuth()
    for name in ('morphable_ui', 'researcher'):
        auth.generate_token(name)
    bus = MessageBus(tmp_path / 'logs', auth=auth)
    fetcher = FixtureFetcher()
    worker = ResearcherBrain('researcher', bus, llm_provider=AsyncMock(),
        search_provider=AsyncMock(), page_reader=PageReader(fetcher=fetcher))
    done, results, finished, progress = asyncio.Event(), [], [], []
    async def observe(message):
        if message.type == MessageType.RESULT:
            results.append(message.payload.get('data', message.payload))
            done.set()
        if message.payload.get('stage'):
            progress.append(message.payload)
        if message.payload.get('stage') == 'research_finished':
            finished.append(message.payload['research'])
    bus.subscribe('morphable_ui', observe)
    try:
        await worker.start()
        await bus.send(BusMessage(type=MessageType.TASK, source='morphable_ui', target='researcher',
            payload={'type': 'research', 'query': f'Establish the limit from {URL}',
                     'session_id': 'direct-worker'}), require_target=True)
        await asyncio.wait_for(done.wait(), 5)
        result = results[-1]
        assert result['success'], result.get('error')
        assert result['evidence']['workflow']['version'] == 'direct-1'
        assert len(finished) == 1 and finished[0]['status'] == 'completed'
        assert finished[0]['passages'] and finished[0]['assessments']
        assert finished[0]['usage']['stage_budget']['logical_calls'] == 2
        ResearchState.model_validate(result['evidence'])
        assert any(p['stage'] == 'research_direct_decision' for p in progress)
        from bigbrain.research_sessions import ResearchSessions
        retained, _ = ResearchSessions('default', 'direct-worker').load(result['research_id'])
        assert retained.claims and retained.status == 'completed'
        done.clear()
        await bus.send(BusMessage(type=MessageType.TASK, source='morphable_ui', target='researcher',
            payload={'type': 'research', 'query': 'Continue the same scope',
                     'session_id': 'direct-worker', 'resume_research_id': result['research_id']}),
            require_target=True)
        await asyncio.wait_for(done.wait(), 5)
        assert results[-1]['research_id'] == result['research_id']
        assert results[-1]['attempt_id'] != result['attempt_id']
        assert len(finished) == 2 and len(adapters) == 2
    finally:
        await worker.stop()
        await bus.close()


@pytest.mark.asyncio
async def test_system_shutdown_drains_native_transport_before_loop_close(monkeypatch):
    from bigbrain.system import BigBrainSystem
    close_native = AsyncMock()
    monkeypatch.setattr('bigbrain.llm.codex_provider.close_codex_app_server', close_native)
    system = BigBrainSystem.__new__(BigBrainSystem)
    system._running = True
    system.brains = {}
    for field in ('voice_brain', 'front_brain', 'orchestrator', 'focus_bridge', 'web_server', 'ui', 'bus'):
        setattr(system, field, None)
    await system.stop()
    close_native.assert_awaited_once()
