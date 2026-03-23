"""Chat Panel - Conversation interface with streaming support."""

from datetime import datetime

from textual.widgets import Static
from textual.containers import Vertical, VerticalScroll
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
        if role == "assistant" and "```" in message_text:
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

    def finish_streaming(self) -> None:
        self.is_streaming = False
        self._refresh_display()

    def _refresh_display(self) -> None:
        text = self.message_text
        if self.is_streaming:
            text += "█"

        if self.role == "assistant" and "```" in text:
            try:
                rendered = Markdown(text)
            except Exception:
                rendered = Text(text)
        else:
            rendered = Text(text)

        self.update(rendered)


class ChatPanel(VerticalScroll):
    """Chat panel with scrolling message history and streaming support."""

    BORDER_TITLE = "💬 Chat"

    def __init__(self, **kwargs):
        self.messages: list[Static] = []
        self.current_streaming_message: StreamingMessage | None = None
        super().__init__(**kwargs)

    def compose(self):
        with Vertical(id="chat-messages"):
            yield ChatMessage(
                "system",
                "Welcome to BigBrain! 🧠\nType a message below to get started.",
            )

    def add_message(self, role: str, text: str) -> None:
        message = ChatMessage(role, text)
        self.messages.append(message)
        container = self.query_one("#chat-messages")
        container.mount(message)
        self.scroll_end(animate=True)

    def start_streaming_message(self, role: str) -> None:
        if self.current_streaming_message:
            self.finish_streaming_message()
        self.current_streaming_message = StreamingMessage(role)
        container = self.query_one("#chat-messages")
        container.mount(self.current_streaming_message)
        self.scroll_end(animate=True)

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

    def clear(self) -> None:
        container = self.query_one("#chat-messages")
        for msg in self.messages:
            if msg.parent:
                msg.remove()
        self.messages.clear()
        self.current_streaming_message = None
        container.mount(ChatMessage("system", "Chat cleared. Ready! 🔄"))
