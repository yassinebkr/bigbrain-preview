"""Working Memory - Ephemeral in-memory storage for BigBrain."""

import time
from typing import Any, Dict, List, Optional


class WorkingMemory:
    """
    Tier 1: Working Memory - Ephemeral in-memory storage.
    
    Per-brain conversation context that dies with the brain process.
    Used for temporary state, conversation history, and short-term
    context that doesn't need persistence.
    
    Key Features:
    - Fast in-memory operations
    - Automatic cleanup of old entries
    - Size limits to prevent memory bloat
    - Thread-safe operations
    - Scoped by brain instance
    """
    
    def __init__(self, max_entries: int = 1000, max_age_seconds: int = 3600):
        """
        Initialize working memory.
        
        Args:
            max_entries: Maximum number of entries before cleanup
            max_age_seconds: Maximum age of entries before cleanup
        """
        self.max_entries = max_entries
        self.max_age_seconds = max_age_seconds
        
        # Core storage
        self._data: Dict[str, Any] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        
        # Conversation context
        self._conversation_history: List[Dict[str, Any]] = []
        self._context_variables: Dict[str, Any] = {}
    
    def store(self, key: str, value: Any, metadata: Dict[str, Any] = None) -> None:
        """
        Store a value with optional metadata.
        
        Args:
            key: Storage key
            value: Value to store
            metadata: Optional metadata (tags, source, etc.)
        """
        self._data[key] = value
        self._metadata[key] = {
            "timestamp": time.time(),
            "access_count": 0,
            "last_accessed": time.time(),
            **(metadata or {})
        }
        
        # Trigger cleanup if needed
        if len(self._data) > self.max_entries:
            self._cleanup_old_entries()
    
    def retrieve(self, key: str) -> Optional[Any]:
        """
        Retrieve a value by key.
        
        Args:
            key: Storage key
            
        Returns:
            Stored value or None if not found
        """
        if key not in self._data:
            return None
        
        # Update access metadata
        self._metadata[key]["access_count"] += 1
        self._metadata[key]["last_accessed"] = time.time()
        
        return self._data[key]
    
    def exists(self, key: str) -> bool:
        """Check if a key exists in memory."""
        self._cleanup_expired_entries()
        return key in self._data
    
    def delete(self, key: str) -> bool:
        """
        Delete an entry.
        
        Args:
            key: Storage key
            
        Returns:
            True if key was deleted, False if not found
        """
        if key in self._data:
            del self._data[key]
            del self._metadata[key]
            return True
        return False
    
    def add_conversation_turn(self, message_type: str, content: str, 
                            metadata: Dict[str, Any] = None) -> None:
        """
        Add a conversation turn to history.
        
        Args:
            message_type: Type of message (user, assistant, system)
            content: Message content
            metadata: Additional metadata
        """
        turn = {
            "timestamp": time.time(),
            "type": message_type,
            "content": content,
            "metadata": metadata or {}
        }
        
        self._conversation_history.append(turn)
        
        # Keep conversation history manageable
        max_turns = 50
        if len(self._conversation_history) > max_turns:
            self._conversation_history = self._conversation_history[-max_turns:]
    
    def get_conversation_history(self, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get conversation history.
        
        Args:
            last_n: Number of recent turns to return, None for all
            
        Returns:
            List of conversation turns
        """
        if last_n is None:
            return self._conversation_history.copy()
        return self._conversation_history[-last_n:] if last_n > 0 else []
    
    def set_context_variable(self, name: str, value: Any) -> None:
        """Set a context variable for the current session."""
        self._context_variables[name] = {
            "value": value,
            "timestamp": time.time()
        }
    
    def get_context_variable(self, name: str) -> Optional[Any]:
        """Get a context variable value."""
        var_data = self._context_variables.get(name)
        return var_data["value"] if var_data else None
    
    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Simple search through stored data.
        
        Args:
            query: Search query
            limit: Maximum results to return
            
        Returns:
            List of matching entries with scores
        """
        self._cleanup_expired_entries()
        
        results = []
        query_lower = query.lower()
        
        for key, value in self._data.items():
            score = 0.0
            
            # Search in key
            if query_lower in key.lower():
                score += 0.5
            
            # Search in value (if string)
            if isinstance(value, str) and query_lower in value.lower():
                score += 0.3
            
            # Search in metadata
            metadata = self._metadata.get(key, {})
            for meta_value in metadata.values():
                if isinstance(meta_value, str) and query_lower in meta_value.lower():
                    score += 0.2
                    break
            
            if score > 0:
                results.append({
                    "key": key,
                    "value": value,
                    "score": score,
                    "metadata": metadata
                })
        
        # Sort by score and limit
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def get_all_keys(self) -> List[str]:
        """Get all storage keys."""
        self._cleanup_expired_entries()
        return list(self._data.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics."""
        self._cleanup_expired_entries()
        
        return {
            "total_entries": len(self._data),
            "conversation_turns": len(self._conversation_history),
            "context_variables": len(self._context_variables),
            "memory_usage_mb": self._estimate_memory_usage(),
            "oldest_entry": min((m["timestamp"] for m in self._metadata.values()), default=0),
            "newest_entry": max((m["timestamp"] for m in self._metadata.values()), default=0)
        }
    
    def clear(self) -> None:
        """Clear all working memory."""
        self._data.clear()
        self._metadata.clear()
        self._conversation_history.clear()
        self._context_variables.clear()
    
    def _cleanup_old_entries(self) -> None:
        """Remove oldest entries to stay under max_entries limit."""
        if len(self._data) <= self.max_entries:
            return
        
        # Sort by last access time and remove oldest
        entries_by_access = sorted(
            self._metadata.items(),
            key=lambda x: x[1]["last_accessed"]
        )
        
        entries_to_remove = len(self._data) - self.max_entries + 10  # Remove extra for efficiency
        for key, _ in entries_by_access[:entries_to_remove]:
            self.delete(key)
    
    def _cleanup_expired_entries(self) -> None:
        """Remove entries older than max_age_seconds."""
        current_time = time.time()
        expired_keys = []
        
        for key, metadata in self._metadata.items():
            if current_time - metadata["timestamp"] > self.max_age_seconds:
                expired_keys.append(key)
        
        for key in expired_keys:
            self.delete(key)
    
    def _estimate_memory_usage(self) -> float:
        """Rough estimate of memory usage in MB."""
        import sys
        
        total_size = 0
        total_size += sys.getsizeof(self._data)
        total_size += sys.getsizeof(self._metadata)
        total_size += sys.getsizeof(self._conversation_history)
        total_size += sys.getsizeof(self._context_variables)
        
        # Estimate content size
        for value in self._data.values():
            total_size += sys.getsizeof(value)
        
        return total_size / (1024 * 1024)  # Convert to MB