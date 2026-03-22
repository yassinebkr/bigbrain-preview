"""Chat Panel - Conversation interface with streaming support."""

import time
from datetime import datetime

from textual.widgets import ScrollView, Static
from textual.widget import Widget
from textual.containers import Vertical
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text


class ChatMessage(Static):
    """A single chat message widget."""
    
    def __init__(self, role: str, content: str, timestamp: datetime = None):
        """
        Initialize chat message.
        
        Args:
            role: Message role ('user', 'assistant', 'system')
            content: Message content
            timestamp: Message timestamp
        """
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now()
        
        # Format content with rich rendering
        if role == "assistant" and "```" in content:
            # Render markdown for code blocks
            rendered = Markdown(content)
        else:
            rendered = Text(content)
        
        super().__init__(rendered, classes=f"{role}-message")
    
    def on_mount(self) -> None:
        """Handle mounting."""
        # Add timestamp if desired
        pass


class StreamingMessage(Static):
    """A message that can be updated in real-time during streaming."""
    
    def __init__(self, role: str):
        """
        Initialize streaming message.
        
        Args:
            role: Message role
        """
        self.role = role
        self.content = ""
        self.is_streaming = True
        
        super().__init__("", classes=f"{role}-message")
    
    def append_content(self, chunk: str) -> None:
        """
        Append content chunk during streaming.
        
        Args:
            chunk: Content chunk to append
        """
        self.content += chunk
        self._update_display()
    
    def finish_streaming(self) -> None:
        """Mark streaming as complete."""
        self.is_streaming = False
        self._update_display()
    
    def _update_display(self) -> None:
        """Update the displayed content."""
        display_content = self.content
        
        # Add cursor if still streaming
        if self.is_streaming:
            display_content += "█"
        
        # Render markdown for assistant messages with code
        if self.role == "assistant" and "```" in self.content:
            try:
                rendered = Markdown(display_content)
            except Exception:
                rendered = Text(display_content)
        else:
            rendered = Text(display_content)
        
        self.update(rendered)


class ChatPanel(ScrollView):
    """
    Chat panel widget for conversation interface.
    
    Features:
    - Scrolling message history
    - Role-based message styling (user, assistant, system)
    - Real-time streaming message support
    - Markdown rendering for code blocks
    - Automatic scroll to bottom
    """
    
    def __init__(self, **kwargs):
        """Initialize chat panel."""
        self.messages = []
        self.current_streaming_message = None
        super().__init__(**kwargs)
    
    def compose(self):
        """Compose the chat panel."""
        with Vertical(id="chat-messages"):
            # Welcome message
            welcome_msg = ChatMessage(
                "system", 
                "**Welcome to BigBrain!** 🧠\n\nI'm your multi-brain AI assistant. I can help with coding, research, analysis, and more.\n\nType a message below to get started."
            )
            yield welcome_msg
    
    def add_message(self, role: str, content: str) -> None:
        """
        Add a new message to the chat.
        
        Args:
            role: Message role ('user', 'assistant', 'system')
            content: Message content
        """
        message = ChatMessage(role, content)
        self.messages.append(message)
        
        # Add to the UI
        chat_container = self.query_one("#chat-messages")
        chat_container.mount(message)
        
        # Scroll to bottom
        self.scroll_end(animate=True)
    
    def start_streaming_message(self, role: str) -> None:
        """
        Start a new streaming message.
        
        Args:
            role: Message role
        """
        if self.current_streaming_message:
            self.finish_streaming_message()
        
        self.current_streaming_message = StreamingMessage(role)
        
        # Add to the UI
        chat_container = self.query_one("#chat-messages")
        chat_container.mount(self.current_streaming_message)
        
        # Scroll to bottom
        self.scroll_end(animate=True)
    
    def append_to_streaming(self, chunk: str) -> None:
        """
        Append content to the current streaming message.
        
        Args:
            chunk: Content chunk to append
        """
        if self.current_streaming_message:
            self.current_streaming_message.append_content(chunk)
            # Keep scrolled to bottom during streaming
            self.scroll_end(animate=False)
    
    def finish_streaming_message(self) -> None:
        """Finish the current streaming message."""
        if self.current_streaming_message:
            self.current_streaming_message.finish_streaming()
            self.messages.append(self.current_streaming_message)
            self.current_streaming_message = None
    
    def clear(self) -> None:
        """Clear all messages from the chat."""
        # Remove all message widgets
        chat_container = self.query_one("#chat-messages")
        for message in self.messages:
            if message.parent:
                message.remove()
        
        # Clear tracking
        self.messages.clear()
        self.current_streaming_message = None
        
        # Add welcome message back
        welcome_msg = ChatMessage(
            "system",
            "Chat cleared. Ready for new conversation! 🔄"
        )
        chat_container.mount(welcome_msg)
    
    def get_message_count(self) -> int:
        """Get total number of messages."""
        return len(self.messages)
    
    def get_last_message(self) -> tuple[str, str]:
        """
        Get the last message content.
        
        Returns:
            Tuple of (role, content) or (None, None) if no messages
        """
        if not self.messages:
            return None, None
        
        last_msg = self.messages[-1]
        return last_msg.role, last_msg.content
    
    def export_conversation(self) -> list[dict]:
        """
        Export conversation history.
        
        Returns:
            List of message dictionaries
        """
        conversation = []
        for message in self.messages:
            conversation.append({
                "role": message.role,
                "content": message.content,
                "timestamp": message.timestamp.isoformat()
            })
        return conversation