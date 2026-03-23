"""Chat Panel - Conversation interface with streaming support."""

from datetime import datetime

from textual.widgets import Static
from textual.containers import VerticalScroll
from rich.markdown import Markdown
from rich.text import Text


class ChatMessage(Static):
    """A single chat message widget.

    NOTE: Static.content is a property in Textual 8.x.
    We use `message_text` for our data and call super().__init__() first.
    """

    def __init__(self, role: str, message_text: str, timestamp: datetime = None):
        self.role = role
        self.message_text = message_text
        self.timestamp = timestamp or datetime.now()

        # Render content
        if role == "assistant" and ("```" in message_text or "**" in message_text):
            try:
                rendered = Markdown(message_text)
            except Exception:
                rendered = Text(message_text)
        else:
            rendered = Text(message_text)

        super().__init__(rendered, classes=f"{role}-message")


class StreamingMessage(Static):
    """A message that updates in real-time during streaming.

    Same pattern: avoid setting `self.content` (Static property conflict).
    """

    def __init__(self, role: str):
        super().__init__("", classes=f"{role}-message")
        self.role = role
        self._chunks: list[str] = []
        self.is_streaming = True

    @property
    def message_text(self) -> str:
        return "".join(self._chunks)

    def append_content(self, chunk: str) -> None:
        self._chunks.append(chunk)
        self._refresh_display()

    def replace_content(self, text: str) -> None:
        """Replace all streaming content (for interim STT updates)."""
        self._chunks = [text]
        self._refresh_display()

    def finish_streaming(self) -> None:
        self.is_streaming = False
        self._refresh_display()

    def _refresh_display(self) -> None:
        text = self.message_text
        if self.is_streaming:
            text += " █"

        if self.role == "assistant" and "```" in text:
            try:
                rendered = Markdown(text)
            except Exception:
                rendered = Text(text)
        else:
            rendered = Text(text)

        self.update(rendered)


class ChatPanel(VerticalScroll):
    """Chat panel with scrolling message history and streaming support.
    
    Messages are mounted directly as children of VerticalScroll (no inner
    container) so Textual's scroll system works correctly. The VerticalScroll
    needs to see multiple children to compute scroll height properly.
    """

    BORDER_TITLE = "💬 Chat"

    def __init__(self, **kwargs):
        self.messages: list[Static] = []
        self.current_streaming_message: StreamingMessage | None = None
        super().__init__(**kwargs)

    def compose(self):
        yield ChatMessage(
            "system",
            "Welcome to BigBrain! 🧠\nType a message below to get started.",
        )

    def add_message(self, role: str, text: str) -> None:
        message = ChatMessage(role, text)
        self.messages.append(message)
        self.mount(message)
        self.call_after_refresh(self._do_scroll)

    def start_streaming_message(self, role: str) -> None:
        if self.current_streaming_message:
            self.finish_streaming_message()
        self.current_streaming_message = StreamingMessage(role)
        self.mount(self.current_streaming_message)
        self.call_after_refresh(self._do_scroll)

    def append_to_streaming(self, chunk: str) -> None:
        if self.current_streaming_message:
            self.current_streaming_message.append_content(chunk)
            self.call_after_refresh(self._do_scroll)

    def _do_scroll(self) -> None:
        """Scroll to bottom after refresh."""
        self.scroll_end(animate=False)

    def finish_streaming_message(self) -> None:
        if self.current_streaming_message:
            self.current_streaming_message.finish_streaming()
            self.messages.append(self.current_streaming_message)
            self.current_streaming_message = None
            self.call_after_refresh(self._do_scroll)

    def discard_streaming_message(self) -> None:
        """Remove the current streaming message without keeping it in history."""
        if self.current_streaming_message:
            if self.current_streaming_message.parent:
                self.current_streaming_message.remove()
            self.current_streaming_message = None

    def clear(self) -> None:
        for msg in self.messages:
            if msg.parent:
                msg.remove()
        self.messages.clear()
        self.current_streaming_message = None
        self.mount(ChatMessage("system", "Chat cleared. Ready! 🔄"))
