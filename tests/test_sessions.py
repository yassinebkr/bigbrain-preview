"""Persistent sessions — store, server routing, per-session brain history."""

import json

import pytest

from bigbrain.web.sessions import SessionStore, SessionError


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_SESSIONS_DIR", str(tmp_path / "sessions"))
    return SessionStore()


class TestSessionStore:
    def test_create_and_persist(self, store):
        session = store.create()
        assert session["id"].startswith("sess-")
        assert session["messages"] == []
        # Really on disk.
        loaded = store.get(session["id"])
        assert loaded == session

    def test_list_sorted_by_recency(self, store):
        import time

        first = store.create()
        second = store.create()
        store.append_message(second["id"], "user", "newest")
        listed = store.list()
        assert [s["id"] for s in listed] == [second["id"], first["id"]]
        assert listed[0]["message_count"] == 1

    def test_append_message_auto_titles_from_first_user_message(self, store):
        session = store.create()
        store.append_message(session["id"], "user",
                             "crée un script hello.py\nsvp")
        loaded = store.get(session["id"])
        assert loaded["title"] == "crée un script hello.py"
        assert loaded["messages"][0]["role"] == "user"

    def test_title_sticks_after_first_message(self, store):
        session = store.create()
        store.append_message(session["id"], "user", "first question")
        store.append_message(session["id"], "user", "second question")
        assert store.get(session["id"])["title"] == "first question"

    def test_ensure_creates_unknown_session(self, store):
        session = store.ensure("sess-custom123")
        assert session["id"] == "sess-custom123"
        assert session["messages"] == []

    def test_ensure_without_id_creates_fresh(self, store):
        session = store.ensure(None)
        assert session["id"].startswith("sess-")

    def test_messages_are_bounded(self, store, monkeypatch):
        from bigbrain.web import sessions as sessions_mod

        monkeypatch.setattr(sessions_mod, "MAX_MESSAGES", 5)
        session = store.create()
        for i in range(10):
            store.append_message(session["id"], "user", f"m{i}")
        loaded = store.get(session["id"])
        assert len(loaded["messages"]) == 5
        assert loaded["messages"][-1]["text"] == "m9"

    def test_delete(self, store):
        session = store.create()
        assert store.delete(session["id"]) is True
        assert store.get(session["id"]) is None
        assert store.delete(session["id"]) is False

    def test_invalid_session_id_rejected(self, store):
        with pytest.raises(SessionError):
            store.get("../escape")

    def test_survives_store_restart(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BIGBRAIN_SESSIONS_DIR", str(tmp_path / "sessions"))
        store = SessionStore()
        session = store.create()
        store.append_message(session["id"], "user", "hello")
        # A NEW store instance (server restart) sees the same data.
        reopened = SessionStore()
        loaded = reopened.get(session["id"])
        assert loaded["messages"][0]["text"] == "hello"


@pytest.fixture
def bus():
    from bigbrain.bus.bus import MessageBus

    return MessageBus(auth=None)


class TestServerSessionRouting:
    @pytest.fixture
    def server(self, bus, tmp_path, monkeypatch):
        monkeypatch.setenv("BIGBRAIN_SESSIONS_DIR", str(tmp_path / "sessions"))
        from bigbrain.web.server import WebServer

        server = WebServer(bus=bus)
        server._ws_clients = set()
        return server

    async def test_chat_send_routes_to_session(self, server, bus, tmp_path):
        sent = []

        async def fake_send(msg):
            sent.append(msg)

        bus.send = fake_send

        # Fake ws: only the message.status acks use it.
        from unittest.mock import AsyncMock

        ws = AsyncMock()

        await server._handle_chat_send(ws, {
            "type": "chat.send",
            "payload": {"text": "bonjour", "messageId": "m1",
                        "sessionId": "sess-abc"},
        })

        # The user message landed in the session file.
        from bigbrain.web.sessions import SessionStore

        session = SessionStore().get("sess-abc")
        assert session is not None
        assert session["messages"][0]["text"] == "bonjour"
        assert server._active_session_id == "sess-abc"

        # The bus task carries the session id.
        task = sent[-1]
        assert task.payload["session_id"] == "sess-abc"
        assert task.payload["text"] == "bonjour"

    async def test_chat_history_per_session(self, server, tmp_path, monkeypatch):
        from unittest.mock import AsyncMock

        monkeypatch.setenv("BIGBRAIN_SESSIONS_DIR", str(tmp_path / "s2"))
        ws = AsyncMock()
        await server._handle_chat_send(ws, {
            "payload": {"text": "première conversation", "messageId": "m1",
                        "sessionId": "sess-one"},
        })
        await server._handle_chat_send(ws, {
            "payload": {"text": "deuxième conversation", "messageId": "m2",
                        "sessionId": "sess-two"},
        })

        server._active_session_id = "sess-two"
        await server._handle_request(ws, {
            "id": "r1", "method": "chat.history",
            "params": {"sessionId": "sess-one"},
        })
        resp = ws.send_json.call_args_list[-1].args[0]
        assert resp["id"] == "r1"
        texts = [m["text"] for m in resp["payload"]["messages"]]
        assert "première conversation" in texts
        assert "deuxième conversation" not in texts

    async def test_sessions_list_create_delete(self, server):
        from unittest.mock import AsyncMock

        ws = AsyncMock()
        await server._handle_request(ws, {"id": "r1", "method": "sessions.create"})
        created = ws.send_json.call_args_list[-1].args[0]["payload"]["session"]
        assert created["id"].startswith("sess-")

        await server._handle_request(ws, {"id": "r2", "method": "sessions.list"})
        listed = ws.send_json.call_args_list[-1].args[0]["payload"]["sessions"]
        assert any(s["id"] == created["id"] for s in listed)

        await server._handle_request(ws, {
            "id": "r3", "method": "sessions.delete",
            "params": {"sessionId": created["id"]},
        })
        assert ws.send_json.call_args_list[-1].args[0]["payload"]["deleted"] is True


class TestFrontBrainSessionHistories:
    def test_histories_are_isolated(self):
        from bigbrain.front.front_brain import FrontBrain
        from bigbrain.bus.bus import MessageBus

        brain = FrontBrain(MessageBus(auth=None))
        hist_a = brain._history_for("sess-a")
        hist_b = brain._history_for("sess-b")
        hist_a.append({"role": "user", "content": "in A"})
        hist_b.append({"role": "user", "content": "in B"})
        # No leakage across sessions, and the default history is separate.
        assert len(brain._history_for("sess-a")) == 1
        assert len(brain._history_for("sess-b")) == 1
        assert brain._conversation_history == []
        assert brain._history_for(None) is brain._conversation_history
