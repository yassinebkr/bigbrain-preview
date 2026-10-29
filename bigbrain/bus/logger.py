"""BusLogger - JSONL disk logging for BigBrain message bus."""

import asyncio
import json
import os
from pathlib import Path
from typing import AsyncIterator, Optional

from .message import BusMessage


class BusLogger:
    """
    JSONL disk logger for BigBrain message bus.
    
    Provides full message replay capability for debugging and auditing.
    Each message is written as a single JSON line with a timestamp.
    
    Why JSONL over database:
    - Simple, human-readable format
    - Easy to grep/filter with standard tools  
    - No external dependencies
    - Append-only for crash safety
    - Works well with log rotation
    """
    
    def __init__(self, log_dir: Path = Path("logs")):
        """Initialize logger with specified log directory."""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True, parents=True)
        self._current_file: Optional[Path] = None
        self._file_handle = None
        self._write_lock = asyncio.Lock()
    
    def _get_log_file(self) -> Path:
        """Get current log file path (one per day for rotation)."""
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"bus-{date_str}.jsonl"
    
    async def log_message(self, message: BusMessage) -> None:
        """Persist a message before delivery while keeping the event loop available."""
        await self._durable_io(self._write_message, message)

    async def _durable_io(self, operation, *args):
        # Keep file rotation, fsync and close ordered. Cancellation drains the
        # current write before releasing the lock or closing its descriptor.
        async with self._write_lock:
            task = asyncio.create_task(asyncio.to_thread(operation, *args))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise

    def _write_message(self, message: BusMessage) -> None:
        """
        Log a message to disk.
        
        Messages are written immediately (not buffered) to ensure
        crash safety and real-time visibility for debugging.
        """
        log_file = self._get_log_file()
        
        # Rotate to new file if date changed
        if self._current_file != log_file:
            self._rotate_file(log_file)
        
        try:
            # Write message as single JSON line
            log_data = message.to_log_dict()
            json_line = json.dumps(log_data, separators=(',', ':')) + '\n'
            
            self._file_handle.write(json_line)
            self._file_handle.flush()  # Immediate write for crash safety
            os.fsync(self._file_handle.fileno())  # Force OS to write to disk
            
        except Exception as e:
            # Log to stderr if we can't write to file
            import sys
            print(f"BusLogger: Failed to log message {message.id}: {e}", file=sys.stderr)
    
    def _rotate_file(self, new_file: Path) -> None:
        """Rotate to a new log file."""
        if self._file_handle:
            self._file_handle.close()
        
        self._current_file = new_file
        self._file_handle = open(new_file, 'a', encoding='utf-8', buffering=1)
    
    async def read_messages(self, 
                          file_path: Optional[Path] = None,
                          limit: Optional[int] = None) -> AsyncIterator[BusMessage]:
        """
        Read messages from log file for replay/debugging.
        
        Args:
            file_path: Specific file to read, or None for today's file
            limit: Maximum number of messages to read
            
        Yields:
            BusMessage objects in chronological order
        """
        target_file = file_path or self._get_log_file()
        
        if not target_file.exists():
            return
        
        count = 0
        with open(target_file, 'r', encoding='utf-8') as f:
            for line in f:
                if limit and count >= limit:
                    break
                    
                try:
                    data = json.loads(line.strip())
                    # Convert back to BusMessage
                    message = BusMessage(
                        id=data['id'],
                        type=data['type'],
                        source=data['source'],
                        target=data['target'],
                        workspace=data.get('workspace'),
                        project=data.get('project'),
                        payload=data.get('payload', {}),
                        timestamp=data['timestamp'],
                        reply_to=data.get('reply_to'),
                        priority=data.get('priority', 1)
                    )
                    yield message
                    count += 1
                    
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    # Skip malformed lines but log the error
                    import sys
                    print(f"BusLogger: Skipping malformed log line: {e}", file=sys.stderr)
                    continue
    
    async def get_conversation_history(self, 
                                     conversation_id: str,
                                     limit: int = 100) -> list[BusMessage]:
        """
        Get message history for a specific conversation thread.
        
        Traces a conversation by following reply_to chains.
        Useful for debugging request/response flows.
        """
        messages = []
        async for msg in self.read_messages(limit=limit * 5):  # Read extra to find chain
            if msg.id == conversation_id or msg.reply_to == conversation_id:
                messages.append(msg)
                
                # Follow the chain backwards
                if msg.reply_to and len(messages) < limit:
                    async for reply in self.read_messages(limit=limit):
                        if reply.id == msg.reply_to:
                            messages.insert(0, reply)  # Chronological order
                            break
                
                if len(messages) >= limit:
                    break
        
        return sorted(messages, key=lambda m: m.timestamp)
    
    async def close(self) -> None:
        """Close the logger and any open file handles."""
        await self._durable_io(self._close_file)

    def _close_file(self):
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
        self._current_file = None
    
    def __del__(self):
        """Ensure file is closed on garbage collection."""
        if hasattr(self, '_file_handle') and self._file_handle:
            self._file_handle.close()
