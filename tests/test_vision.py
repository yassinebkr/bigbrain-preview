"""Vision attachment dispatch tests."""

from types import SimpleNamespace

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
        return "I can see the image."


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
