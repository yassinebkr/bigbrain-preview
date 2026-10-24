"""Actual worker→bus journal→conversation replay, no network or inference."""
from unittest.mock import AsyncMock
import asyncio

import pytest

from bigbrain.brains.researcher import ResearcherBrain
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.web.run_history import conversation_activity


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [True, False])
async def test_research_evidence_survives_history_restore_without_reexecution(tmp_path, terminal):
    bus = MessageBus(tmp_path / "logs", auth=None)
    async def event(kind, **kwargs):
        await bus.broadcast_event(source="test", event_type=kind,
            payload={"task_id": "run", "session_id": "session", **kwargs})
    search, reader = AsyncMock(), AsyncMock()
    search.search.return_value = [{"url": "https://first.test/a"}, {"url": "https://second.test/a"}]
    reader.read.side_effect = [{"url": "https://first.test/a", "text": "First actual page", "sha256": "first"},
                              {"url": "https://second.test/a", "text": "Second actual page", "sha256": "second"}]
    worker = ResearcherBrain("researcher", bus, search_provider=search, page_reader=reader)
    worker._current_task = BusMessage(type=MessageType.TASK, source="orchestrator", target="researcher",
        payload={"session_id": "session", "_plan_id": "run", "_subtask_id": "research-step", "query": "question"})
    try:
        await event("task.received", description="Research question")
        result = await worker.handle_task(worker._current_task)
        if terminal:
            await event("task.complete")
    finally:
        await bus.close()
    frames = conversation_activity(bus.logger.log_dir, "session", 10**12 if not terminal else 0)
    observations = [f["payload"] for f in frames if f["payload"].get("stage") == "research_observation"]
    assert len(observations) == 4  # Search, two page reads, conclusion.
    read_text = [p["text"] for f in observations for p in f["observation"]["data"].get("passages", [])]
    assert read_text == ["First actual page", "Second actual page"]
    checkpoint = next(f["payload"] for f in frames if f["payload"].get("stage") == "research_finished")
    assert checkpoint["subtask_id"] == "research-step"
    assert checkpoint["research"]["status"] == "completed"
    assert result["pages_read"] == 2
    if not terminal:
        assert frames[-1]["payload"]["event"] == "task.failed"
        assert "redémarrage" in frames[-1]["payload"]["error"]
    assert conversation_activity(bus.logger.log_dir, "foreign-session", 0) == []
    search.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_reader_selection_and_cache_refinement_survive_bus_replay(tmp_path):
    from bigbrain.research import Action, PageReader
    from bigbrain.research_acquisition import Response, artifact
    body = ("<main>" + "".join(f"<h2>Profile {i}</h2><p>Pottery profile {i}: " +
            " ".join(f"ceramic{i}v{n}" for n in range(80)) + "</p>" for i in range(12)) + "</main>").encode()
    ref = artifact(body, name="history-page.html", media_type="text/html")
    fetcher, search = AsyncMock(), AsyncMock()
    fetcher.fetch.return_value = Response("https://source.test/", 200, body, {"content-type": "text/html"}, "utf-8", ref, ())
    search.search.return_value = [{"url": "https://source.test/"}]
    class Policy:
        async def choose(self, state, remaining):
            shared = {"question_id": "q1", "rationale": "Read the observed sections"}
            if not state.sources:
                return Action(tool="search", query="quantum entanglement", **shared)
            if not state.observations[-1].action.tool == "open":
                return Action(tool="open", source_id="s1", **shared)
            source = state.sources[0]
            if source.acquisition.get("status") == "needs_context":
                selection = source.acquisition["selection"]
                return Action(tool="open", source_id="s1", group_ids=[selection["catalog"][0]["id"]],
                              observation_sha256=selection["observation_sha256"], **shared)
            return Action(tool="conclude", **shared)
    bus = MessageBus(tmp_path / "logs", auth=None)
    worker = ResearcherBrain("researcher", bus, search_provider=search, page_reader=PageReader(fetcher=fetcher), research_policy=Policy())
    worker._current_task = BusMessage(type=MessageType.TASK, source="orchestrator", target="researcher",
        payload={"session_id": "session", "_plan_id": "run", "_subtask_id": "step", "query": "quantum entanglement"})
    try:
        await bus.broadcast_event(source="test", event_type="task.received", payload={"task_id": "run", "session_id": "session"})
        result = await worker.handle_task(worker._current_task)
    finally:
        await bus.close()
    frames = conversation_activity(bus.logger.log_dir, "session", 0)
    updates = [f["payload"] for f in frames if f["payload"].get("research")]
    checkpoint = next(p["research"] for p in updates if p["stage"] == "research_finished")
    assert result["research_status"] == "completed"
    assert checkpoint["activity"] is None
    assert checkpoint["sources"][0]["acquisition"]["cache_hit"]
    assert checkpoint["sources"][0]["acquisition"]["selection"]["method"] == "explicit-section-ids"
    assert any(p["research"]["activity"].get("phase") == "selecting_context" for p in updates if p["research"]["activity"])
    assert [h["status"] for h in checkpoint["history"]] == ["ok", "error", "ok", "ok"]
    assert any("Pottery profile" in p["text"] for p in checkpoint["passages"])
    fetcher.fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_review_evidence_for_distinct_rounds_is_retained_before_a_checkpoint(tmp_path):
    bus = MessageBus(tmp_path / "logs", auth=None)
    try:
        for index in (2, 5):
            await bus.broadcast_event(source="test", event_type="task.progress", payload={
                "task_id": "run", "session_id": "session", "subtask_id": "step", "stage": "research_review_evidence",
                "index": index, "research": {"research_id": "attempt"},
                "passages": [{"id": f"p{index}", "text": f"Observed review {index}"}]})
    finally:
        await bus.close()
    frames = conversation_activity(bus.logger.log_dir, "session", 0)
    assert [f["payload"]["index"] for f in frames] == [2, 5]


@pytest.mark.asyncio
async def test_pending_http_phase_is_restored_as_interrupted_without_resuming_io(tmp_path):
    from bigbrain.research import PageReader
    started = asyncio.Event()
    fetcher, search = AsyncMock(), AsyncMock()
    async def pending(url):
        started.set()
        await asyncio.Event().wait()
    fetcher.fetch.side_effect = pending
    search.search.return_value = [{"url": "https://source.test/"}]
    bus = MessageBus(tmp_path / "logs", auth=None)
    worker = ResearcherBrain("researcher", bus, search_provider=search, page_reader=PageReader(fetcher=fetcher))
    worker._current_task = BusMessage(type=MessageType.TASK, source="orchestrator", target="researcher",
        payload={"session_id": "session", "_plan_id": "run", "_subtask_id": "step", "query": "question"})
    task = None
    try:
        await bus.broadcast_event(source="test", event_type="task.received", payload={"task_id": "run", "session_id": "session"})
        task = asyncio.create_task(worker.handle_task(worker._current_task))
        await asyncio.wait_for(started.wait(), 2)
        frames = conversation_activity(bus.logger.log_dir, "session", 10**12)
        latest = [f["payload"]["research"] for f in frames if f["payload"].get("research")][-1]
        assert latest["activity"]["phase"] == "http_loading"
        assert latest["activity"]["source_id"] == "s1"
        assert frames[-1]["payload"]["event"] == "task.failed"
        # Reading history performs no transport call and no task dispatch.
        conversation_activity(bus.logger.log_dir, "session", 10**12)
        fetcher.fetch.assert_awaited_once()
    finally:
        if task:
            worker._cancelled = True
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
        await bus.close()
    terminal = next(f["payload"]["research"] for f in conversation_activity(bus.logger.log_dir, "session", 0)
                    if f["payload"].get("stage") == "research_finished")
    assert terminal["status"] == "cancelled" and terminal["activity"] is None
