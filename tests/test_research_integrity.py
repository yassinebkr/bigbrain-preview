"""Regressions for honest research and cross-brain result summaries."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from bigbrain.brains.researcher import ResearcherBrain, UnavailableSearch
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.front.front_brain import FrontBrain


@pytest.mark.asyncio
async def test_missing_search_provider_never_returns_synthetic_sources():
    brain = ResearcherBrain(
        "researcher", MessageBus(auth=None), llm_provider=None,
    )
    brain.send_progress = AsyncMock()

    result = await brain._full_research("fitness programme 2026", {})

    assert isinstance(brain.search, UnavailableSearch)
    assert result["success"] is True
    assert result["research_unavailable"] is True
    assert result["top_sources"] == []
    assert result["unique_sources"] == 0
    assert "example.com" not in str(result)


@pytest.mark.asyncio
async def test_result_summary_prioritizes_execution_over_verbose_research():
    provider = AsyncMock()
    provider.chat_complete.return_value = "Le programme a été généré."
    brain = FrontBrain(MessageBus(auth=None), llm_provider=provider)
    brain._last_session_id = "sess-fitness"
    brain._history_for("sess-fitness").append({
        "role": "user",
        "content": "Crée un programme fitness en Python",
    })
    code_output = "PYTHON_RESULT_PRESENT\nmodels.py\nplanner.py\nmain.py"
    verbose_research = "research " * 1000

    await brain._summarize_result([
        ("research", verbose_research),
        ("code", code_output),
    ])

    prompt = provider.chat_complete.call_args.kwargs["messages"][1]["content"]
    assert "PYTHON_RESULT_PRESENT" in prompt
    assert prompt.index("Code execution output") < prompt.index("Research findings")
    assert len(prompt) < 7000


@pytest.mark.asyncio
async def test_web_result_uses_only_worker_preview_url():
    brain = FrontBrain(MessageBus(auth=None), llm_provider=None)
    brain._summarize_result = AsyncMock(return_value="Aperçu prêt.")
    brain._emit_chat_message = AsyncMock()
    brain.memory.store = MagicMock()
    preview_url = "http://127.0.0.1:3241"

    await brain._handle_task_result(BusMessage(
        type=MessageType.RESULT,
        source="orchestrator",
        target=brain.name,
        payload={"success": True, "results": {"preview": {"data": {
            "success": True,
            "server_running": True,
            "preview_url": preview_url,
            "preview_port": 3241,
        }}}},
    ))

    brain._summarize_result.assert_not_awaited()
    message = brain._emit_chat_message.await_args.args[1]
    assert message == "✅ Projet web terminé. Utilise l’aperçu ou les contrôles du projet ci-dessous."
    assert "clawos" not in message.lower()
