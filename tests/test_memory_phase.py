"""Item 6 — the memory phase: per-turn semantic recall, attachment
memory, and the batch-consolidated soul. Frugal by design: retrieval
costs zero LLM tokens, the soul costs ONE call per N turns.
"""

import json

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType


@pytest.fixture
def isolated_memory(tmp_path, monkeypatch):
    """Isolate every store the memory phase touches."""
    monkeypatch.setenv("BIGBRAIN_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("BIGBRAIN_SOUL_FILE", str(tmp_path / "soul.json"))
    monkeypatch.setenv("BIGBRAIN_ATTACHMENTS_DIR", str(tmp_path / "attachments"))
    return tmp_path


def _memory_manager(brain="front_brain", tmp_path=None):
    from bigbrain.memory.memory_manager import MemoryManager

    return MemoryManager(brain, storage_dir=tmp_path)


class TestConversationPersistence:
    def test_turns_are_persisted_for_recall(self, isolated_memory, tmp_path):
        manager = _memory_manager(tmp_path=tmp_path / "chroma")
        manager.store_conversation_turn(
            "user", "je m'appelle Yassine et je bosse sur near_agi",
            {"session_id": "sess-1"})

        # The persistent copy exists and is findable
        results = manager.persistent.query(
            "qui suis-je ?", limit=5, memory_type="conversation")
        assert len(results) >= 1
        assert any("Yassine" in r["content"] for r in results)
        assert results[0]["metadata"]["role"] in ("user", "assistant")

    def test_empty_turn_is_not_persisted(self, isolated_memory, tmp_path):
        manager = _memory_manager(tmp_path=tmp_path / "chroma")
        manager.store_conversation_turn("user", "   ")
        assert manager.persistent.query(
            "anything", memory_type="conversation") == []


def _front(tmp_path, monkeypatch, provider=None):
    monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "ev"))
    monkeypatch.setenv("BIGBRAIN_TASKS_FILE", str(tmp_path / "tasks.json"))
    from bigbrain.front.front_brain import FrontBrain

    return FrontBrain(MessageBus(auth=None), llm_provider=provider)


class TestRecall:
    async def test_recall_injects_relevant_memory(self, isolated_memory,
                                                  tmp_path, monkeypatch):
        class RecordingProvider:
            def __init__(self):
                self.messages = None

            async def chat_complete(self, messages=None, **kwargs):
                self.messages = messages
                return "Bonjour !"

        provider = RecordingProvider()
        front = _front(tmp_path, monkeypatch, provider)
        front.memory.persistent.store(
            content=("user: j'ai un chien qui s'appelle Rex et j'adore "
                     "les randonnées en montagne"),
            scope="global", memory_type="conversation",
            extra_metadata={"role": "user", "session_id": "old-session"})

        await front._llm_respond("parle-moi de mes animaux", session_id=None)

        # The retrieved memory reached the LLM prompt
        blocks = [m.get("content", "") for m in (provider.messages or [])]
        assert any("Rex" in block for block in blocks)

    async def test_recall_dedupes_the_live_window(self, isolated_memory,
                                                  tmp_path, monkeypatch):
        """A turn already in the 20-message window must not be re-injected."""
        class RecordingProvider:
            async def chat_complete(self, messages=None, **kwargs):
                self.seen = messages
                return "ok"

        provider = RecordingProvider()
        front = _front(tmp_path, monkeypatch, provider)
        front._conversation_history.append(
            {"role": "user", "content": "j'ai un chien nommé Rex"})
        front.memory.persistent.store(
            content="user: j'ai un chien nommé Rex",
            scope="global", memory_type="conversation",
            extra_metadata={"role": "user"})

        recalled = front._recall_relevant(
            "chiens", front._conversation_history[-20:])
        assert recalled == []  # already in the window

    async def test_recall_kill_switch(self, isolated_memory, tmp_path,
                                      monkeypatch):
        monkeypatch.setenv("BIGBRAIN_RECALL", "0")
        front = _front(tmp_path, monkeypatch)
        front.memory.persistent.store(
            content="user: j'ai un chien nommé Rex",
            scope="global", memory_type="conversation",
            extra_metadata={"role": "user"})
        assert front._recall_relevant("chiens", []) == []


class TestAttachmentMemory:
    async def test_attachments_are_remembered(self, isolated_memory,
                                              tmp_path, monkeypatch):
        front = _front(tmp_path, monkeypatch)
        front._remember_attachments(
            [{"id": "att-abc123", "name": "vacances.png",
              "type": "image/png"}],
            "sess-1")

        results = front.memory.persistent.query(
            "vacances", limit=3, memory_type="attachment")
        assert len(results) == 1
        assert "vacances.png" in results[0]["content"]
        assert results[0]["metadata"]["attachment_id"] == "att-abc123"

    async def test_ui_message_notes_attachments_and_remembers(
            self, isolated_memory, tmp_path, monkeypatch):
        class Provider:
            async def chat_complete(self, messages=None, **kwargs):
                return "Merci pour l'image !"

        front = _front(tmp_path, monkeypatch, Provider())
        front.memory.store_conversation_turn(
            "user", "old", {"session_id": None})

        await front._handle_ui_message(BusMessage(
            type=MessageType.TASK, source="morphable_ui",
            target="front_brain",
            payload={
                "text": "regarde cette photo",
                "session_id": "sess-9",
                "attachments": [
                    {"id": "att-xyz789", "name": "chat.png",
                     "type": "image/png"},
                ],
            },
        ))

        # The stored user turn carries the honest attachment note
        user_turns = [m for m in front._history_for("sess-9")
                      if m["role"] == "user"]
        assert any("chat.png" in t["content"] for t in user_turns)
        assert any("selected model cannot see image content" in t["content"]
                   for t in user_turns)

        # The attachment lives in persistent memory
        results = front.memory.persistent.query(
            "photo chat", limit=3, memory_type="attachment")
        assert len(results) == 1

    def test_save_and_read_attachment(self, isolated_memory, monkeypatch):
        from bigbrain.web.attachments import read_attachment, save_attachment

        record = save_attachment("../../etc/passwd", "image/png", b"PNGDATA")
        assert record["name"] == "passwd"  # path stripped, hostile chars gone
        stored = read_attachment(record["id"])
        assert stored is not None
        assert stored.read_bytes() == b"PNGDATA"

        # No traversal: a bogus id never resolves
        assert read_attachment("../etc/passwd") is None
        assert read_attachment("att-zzz") is None


class TestSoul:
    def test_soul_store_roundtrip(self, isolated_memory, tmp_path):
        from bigbrain.memory.soul import SoulStore

        soul = SoulStore(tmp_path / "soul.json")
        assert soul.summary == ""
        soul.save("- Yassine, travaille sur near_agi\n- préfère le français\n- détail inutile très long "
                  + "x" * 2000 + "\n- septième ligne à couper\n- huitième\n- neuvième")
        reloaded = SoulStore(tmp_path / "soul.json")
        assert "near_agi" in reloaded.summary
        # Capped: max 6 lines, 900 chars
        assert len(reloaded.summary) <= 900
        assert len(reloaded.summary.splitlines()) <= 6

    async def test_consolidation_uses_one_llm_call(self, isolated_memory,
                                                   tmp_path, monkeypatch):
        from bigbrain.web.sessions import SessionStore

        sessions = SessionStore()
        session = sessions.create()
        for text in ["je m'appelle Yassine", "je bosse sur bigbrain",
                     "j'aime les tests"]:
            sessions.append_message(session["id"], "user", text)

        class SoulProvider:
            def __init__(self):
                self.soul_calls = 0

            async def chat_complete(self, messages=None, **kwargs):
                if messages and "soul" in str(messages[0].get("content", "")).lower():
                    self.soul_calls += 1
                    return "- Yassine, construit bigbrain\n- aime les tests"
                return "ok"

        provider = SoulProvider()
        front = _front(tmp_path, monkeypatch, provider)
        monkeypatch.setenv("BIGBRAIN_SOUL_TURNS", "3")

        # Three user turns → exactly one batched soul consolidation
        for text in ["un", "deux", "trois"]:
            await front.handle_user_input(text, session_id=None)
        # The consolidation task needs one loop tick
        import asyncio
        await asyncio.sleep(0)

        if front._soul_task:
            await front._soul_task

        assert provider.soul_calls == 1  # ONE batched call, not per-turn
        assert "bigbrain" in front._soul_store.summary

    async def test_soul_injected_into_the_prompt(self, isolated_memory,
                                                 tmp_path, monkeypatch):
        class RecordingProvider:
            def __init__(self):
                self.messages = None

            async def chat_complete(self, messages=None, **kwargs):
                self.messages = messages
                return "salut"

        provider = RecordingProvider()
        front = _front(tmp_path, monkeypatch, provider)
        front._soul_store.save("- Yassine, préfère les réponses courtes")

        await front._llm_respond("bonjour", session_id=None)
        system_blocks = [m["content"] for m in provider.messages
                         if m["role"] == "system"]
        assert any("préfère les réponses courtes" in b for b in system_blocks)

    async def test_soul_kill_switch(self, isolated_memory, tmp_path,
                                    monkeypatch):
        monkeypatch.setenv("BIGBRAIN_SOUL", "0")
        class RecordingProvider:
            def __init__(self):
                self.messages = None

            async def chat_complete(self, messages=None, **kwargs):
                self.messages = messages
                return "ok"

        provider = RecordingProvider()
        front = _front(tmp_path, monkeypatch, provider)
        front._soul_store.save("- ne doit pas apparaître")

        await front._llm_respond("bonjour", session_id=None)
        assert not any("ne doit pas apparaître" in m["content"]
                       for m in provider.messages or [])
