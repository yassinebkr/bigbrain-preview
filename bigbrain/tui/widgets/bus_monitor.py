"""Bus Monitor - Real-time message flow display."""

from datetime import datetime
from typing import Dict, List

from textual.widgets import Static
from textual.containers import Vertical, VerticalScroll
from rich.text import Text


class BusMessage(Static):
    """Individual bus message display.

    Calls super().__init__() first to avoid Textual 8.x property conflicts.
    """

    def __init__(self, msg_type: str, route: str, payload: str, timestamp: datetime = None, **kwargs):
        super().__init__("", **kwargs)
        self.msg_type = msg_type
        self.route = route
        self.payload = payload
        self.timestamp = timestamp or datetime.now()
        self._refresh_display()

    def _refresh_display(self) -> None:
        time_str = self.timestamp.strftime("%H:%M:%S")
        type_colors = {
            "TASK": "blue", "RESULT": "green", "EVENT": "yellow",
            "ERROR": "red", "PROGRESS": "cyan", "QUERY": "magenta",
        }
        color = type_colors.get(self.msg_type, "white")

        text = Text()
        text.append(f"[{time_str}] ", style="dim")
        text.append(self.msg_type, style=f"bold {color}")
        text.append(f" {self.route}", style="white")

        if self.payload:
            display = self.payload[:47] + "..." if len(self.payload) > 50 else self.payload
            text.append(f"\n  └ {display}", style="dim")

        self.update(text)


class BusMonitor(VerticalScroll):
    """Bus monitor widget showing real-time message flow."""

    BORDER_TITLE = "📡 Bus Monitor"

    def __init__(self, max_messages: int = 100, **kwargs):
        self.max_messages = max_messages
        self.messages: list[BusMessage] = []
        self.message_counts: Dict[str, int] = {}
        self.start_time = datetime.now()
        super().__init__(**kwargs)

    def compose(self):
        with Vertical(id="bus-messages"):
            yield Static(
                "🚌 Monitoring message bus...\nWaiting for activity...",
                id="welcome-message",
                classes="dim",
            )
            yield Static("", id="bus-stats")

    def add_message(self, msg_type: str, route: str, payload: str = "") -> None:
        if not self.messages:
            try:
                self.query_one("#welcome-message").remove()
            except Exception:
                pass

        message = BusMessage(msg_type, route, payload)
        self.messages.append(message)
        self.message_counts[msg_type] = self.message_counts.get(msg_type, 0) + 1

        try:
            self.query_one("#bus-messages").mount(message)
        except Exception:
            pass

        if len(self.messages) > self.max_messages:
            old = self.messages.pop(0)
            old.remove()

        self.scroll_end(animate=True)
        self._update_stats()

    def _update_stats(self) -> None:
        try:
            stats = self.query_one("#bus-stats")
        except Exception:
            return

        total = sum(self.message_counts.values())
        if total == 0:
            stats.update("")
            return

        elapsed = max((datetime.now() - self.start_time).total_seconds(), 1)
        text = Text()
        text.append("─" * 25 + "\n", style="dim")

        colors = {"TASK": "blue", "RESULT": "green", "EVENT": "yellow", "ERROR": "red", "PROGRESS": "cyan"}
        for t, count in self.message_counts.items():
            if count > 0:
                text.append(f"{t}:{count} ", style=colors.get(t, "white"))

        text.append(f"\nTotal: {total} | {total / elapsed:.1f}/s", style="dim")
        stats.update(text)

    def clear(self) -> None:
        try:
            container = self.query_one("#bus-messages")
        except Exception:
            return
        for msg in self.messages:
            if msg.parent:
                msg.remove()
        self.messages.clear()
        self.message_counts.clear()
        self.start_time = datetime.now()
        container.mount(Static("🚌 Bus cleared. Waiting...", id="welcome-message", classes="dim"))
        self._update_stats()
