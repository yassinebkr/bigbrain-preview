"""Vision attachment dispatch tests."""

from types import SimpleNamespace
import json

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.front.front_brain import FrontBrain
from bigbrain.web.attachments import save_attachment


class RecordingProvider:
    def __init__(self, vision):
        self.entry = SimpleNamespace(vision=vision)
        self.calls = []

    async def chat_complete(self, messages=None, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return json.dumps({"decision":{"operation":"respond","reply":"I can see the image."}})


def message_for(record, text="What is in this photo?"):
    return BusMessage(
        type=MessageType.TASK, source="morphable_ui", target="front_brain",
        payload={"type": "user_message", "text": text, "session_id": "sess-v",
                 "attachments": [{"id": record["id"], "name": record["name"],
                                  "type": record["type"]}]},
    )


@pytest.mark.asyncio
async def test_vision_model_receives_inline_image(monkeypatch):
    record = save_attachment("photo.png", "image/png", b"PNGDATA")
    provider = RecordingProvider(vision=True)
    front = FrontBrain(MessageBus(auth=None), llm_provider=provider)
    emitted = []

    async def capture(role, content):
        emitted.append((role, content))

    monkeypatch.setattr(front, "_emit_chat_message", capture)
    await front._handle_ui_message(message_for(record))

    assert len(provider.calls) == 1
    user_content = provider.calls[0]["messages"][-1]["content"]
    assert user_content[0] == {"type": "text", "text": "What is in this photo?"}
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"] == "data:image/png;base64,UE5HREFUQQ=="
    stored = front._history_for("sess-v")[0]["content"]
    assert "image content was sent to the vision model" in stored
    assert "base64" not in stored
    assert emitted == [("assistant", "I can see the image.")]


@pytest.mark.asyncio
async def test_text_model_refuses_image_without_llm_or_delegation(
        monkeypatch):
    record = save_attachment("photo.jpg", "image/jpeg", b"JPEGDATA")
    provider = RecordingProvider(vision=False)
    bus = MessageBus(auth=None)
    front = FrontBrain(bus, llm_provider=provider)
    emitted = []

    async def capture(role, content):
        emitted.append((role, content))

    async def forbidden_task(*args, **kwargs):
        raise AssertionError("image must not be delegated")

    monkeypatch.setattr(front, "_emit_chat_message", capture)
    monkeypatch.setattr(bus, "send_task", forbidden_task)
    await front._handle_ui_message(message_for(record, text="analyse ça"))

    assert provider.calls == []
    assert len(emitted) == 1
    assert "can’t see this image" in emitted[0][1]
    assert front._history_for("sess-v")[-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_attachment_only_message_is_sent_to_vision_model(
        monkeypatch):
    record = save_attachment("photo.webp", "image/webp", b"WEBP")
    provider = RecordingProvider(vision=True)
    front = FrontBrain(MessageBus(auth=None), llm_provider=provider)

    async def capture(role, content):
        pass

    monkeypatch.setattr(front, "_emit_chat_message", capture)
    await front._handle_ui_message(message_for(record, text=""))
    content = provider.calls[0]["messages"][-1]["content"]
    assert content[0]["text"] == "Please describe the attached image."


@pytest.mark.asyncio
@pytest.mark.parametrize('alter_source', [False, True])
async def test_cad_vision_handoff_verifies_source_bytes(monkeypatch, alter_source):
    from tests.test_cad_drawings import drawing
    record = save_attachment('drawing.png', 'image/png', b'SYNTHETIC_DRAWING')

    class CadProvider(RecordingProvider):
        async def chat_complete(self, messages=None, **kwargs):
            blocks = messages[-1]['content']
            metadata = next(block['text'] for block in blocks
                            if block.get('type') == 'text' and block['text'].startswith('Image provenance: '))
            source = json.loads(metadata.removeprefix('Image provenance: '))
            if alter_source:
                source['sha256'] = '0' * 64
            spec = drawing()
            spec['sources'] = [source]
            spec['dimensions'][0]['sources'] = [source]
            return json.dumps({'decision': {'operation': 'delegate', 'reply': 'Je prépare la pièce.',
                'objective': 'Créer le support du dessin.', 'route': {'brain': 'cad_brain',
                'payload': {'type': 'model_cad', 'drawing': spec}}}})

    bus = MessageBus(auth=None)
    front = FrontBrain(bus, llm_provider=CadProvider(vision=True))
    front.register_brain('cad_brain', 'Mechanical CAD')
    tasks = []

    async def capture_task(**kwargs):
        tasks.append(kwargs['task_data'])

    async def capture_message(*args, **kwargs):
        return None

    monkeypatch.setattr(bus, 'send_task', capture_task)
    monkeypatch.setattr(front, '_emit_chat_message', capture_message)
    try:
        await front._handle_ui_message(message_for(record, 'Créer cette pièce.'))
        assert len(tasks) == (0 if alter_source else 1)
        if tasks:
            assert tasks[0]['drawing']['sources'][0]['attachment_id'] == record['id']
            assert tasks[0]['brain'] == 'cad_brain'
    finally:
        await bus.close()
