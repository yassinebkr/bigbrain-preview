"""Memory Manager - Unified memory interface for BigBrain.

Tier 1: Working Memory — ephemeral, in-memory, per-brain.
Tier 2+3: Persistent Memory — single ChromaDB collection with scope field.
  scope="workspace" → project-specific (dies with workspace)
  scope="global" → long-term (survives workspace deletion)
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from .working_memory import WorkingMemory
from .chromadb_backend import ChromaMemoryBackend

# Keep old imports for backward compatibility with tests
from .project_memory import ProjectMemory
from .long_term_memory import LongTermMemory


class MemoryManager:
    """
    Unified memory interface for BigBrain.
    
    Coordinates:
    - Tier 1: Working Memory (ephemeral, per-brain)
    - Tier 2+3: ChromaDB backend (persistent, scope-based)
    
    Also maintains legacy ProjectMemory/LongTermMemory for backward
    compatibility with existing tests.
    """
    
    def __init__(self, brain_name: str, project_name: str = None, 
                 workspace: str = None, storage_dir: Path = None):
        self.brain_name = brain_name
        self.project_name = project_name or "default"
        self.workspace = workspace or "default"
        
        # Tier 1: Working Memory (ephemeral)
        self.working = WorkingMemory()
        
        # Tier 2+3: Unified persistent backend
        self.persistent = ChromaMemoryBackend(storage_dir=storage_dir)
        
        # Legacy interfaces (kept for test compatibility)
        self.project = ProjectMemory(
            project_name=self.project_name,
            workspace=self.workspace,
            storage_dir=storage_dir
        )
        self.long_term = LongTermMemory(storage_dir=storage_dir)
        
        # Cache
        self._context_cache: Dict[str, Any] = {}
    
    def store(self, content: str, memory_type: str = "auto",
              metadata: Dict[str, Any] = None) -> str:
        """
        Store content in appropriate memory tier.
        
        Args:
            content: Content to store
            memory_type: Memory type hint ("working", "project", "long_term", "auto")
            metadata: Associated metadata
            
        Returns:
            Storage key/ID
        """
        metadata = metadata or {}
        metadata.update({
            "brain": self.brain_name,
            "project": self.project_name,
            "workspace": self.workspace
        })
        
        # Automatic tier selection
        if memory_type == "auto":
            memory_type = self._determine_memory_tier(content, metadata)
        
        if memory_type == "working":
            key = f"{self.brain_name}_{len(self.working._data)}"
            self.working.store(key, content, metadata)
            return key
        
        elif memory_type == "project":
            # Store in unified persistent backend (workspace scope)
            tags = ",".join(metadata.get("tags", []))  if isinstance(metadata.get("tags"), list) else metadata.get("tags", "")
            entry_id = self.persistent.store(
                content=content,
                scope="workspace",
                workspace=self.workspace,
                brain=self.brain_name,
                memory_type=metadata.get("type", "fact"),
                tags=tags,
                task_id=metadata.get("task_id", ""),
                extra_metadata=metadata,
            )
            # Also store in legacy for test compat
            self.project.store(content, metadata)
            return entry_id
        
        elif memory_type == "long_term":
            # Store in unified persistent backend (global scope)
            entry_id = self.persistent.store(
                content=content,
                scope="global",
                brain=self.brain_name,
                memory_type=metadata.get("type", "lesson"),
                extra_metadata=metadata,
            )
            # Also store in legacy for test compat
            category = metadata.get("category", "general")
            self.long_term.store_knowledge(content, category, metadata)
            return entry_id
        
        else:
            raise ValueError(f"Unknown memory type: {memory_type}")
    
    def recall(self, query: str, limit: int = 5, 
               tiers: List[str] = None, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Search across memory tiers for relevant content.
        
        Args:
            query: Search query
            limit: Maximum results per tier
            tiers: Specific tiers to search (default: all)
            context: Additional context for filtering
            
        Returns:
            List of results from all tiers with tier information
        """
        tiers = tiers or ["working", "project", "long_term"]
        all_results = []
        
        # Search working memory
        if "working" in tiers:
            working_results = self.working.search(query, limit)
            for result in working_results:
                result["tier"] = "working"
                result["brain_scope"] = True
                all_results.append(result)
        
        # Search persistent memory (unified Tier 2+3)
        if "project" in tiers or "long_term" in tiers:
            scope = None
            workspace = None
            if "project" in tiers and "long_term" not in tiers:
                scope = "workspace"
                workspace = self.workspace
            elif "long_term" in tiers and "project" not in tiers:
                scope = "global"
            # else: search all scopes
            
            if "project" in tiers:
                workspace = self.workspace
            
            brain_filter = None
            if context and context.get("source_brain"):
                brain_filter = context["source_brain"]
            
            persistent_results = self.persistent.query(
                query_text=query,
                limit=limit,
                scope=scope,
                workspace=workspace if "project" in tiers else None,
                brain=brain_filter,
            )
            for result in persistent_results:
                result_scope = result.get("metadata", {}).get("scope", "workspace")
                result["tier"] = "project" if result_scope == "workspace" else "long_term"
                all_results.append(result)
        
        # Sort by relevance (distance for ChromaDB, similarity for working)
        def sort_key(x):
            if "distance" in x and x["distance"] is not None:
                return -x["distance"]  # Lower distance = better
            return x.get("similarity", x.get("score", 0))
        
        all_results.sort(key=sort_key, reverse=True)
        return all_results[:limit * len(tiers)]
    
    def store_conversation_turn(self, message_type: str, content: str,
                               metadata: Dict[str, Any] = None) -> None:
        """Store conversation turn in working memory."""
        enhanced_metadata = {
            "brain": self.brain_name,
            "project": self.project_name,
            **(metadata or {})
        }
        self.working.add_conversation_turn(message_type, content, enhanced_metadata)
    
    def get_conversation_context(self, turns: int = 10) -> List[Dict[str, Any]]:
        """Get recent conversation context."""
        return self.working.get_conversation_history(turns)
    
    def store_user_preference(self, key: str, value: Any, description: str = None) -> None:
        """Store user preference in persistent memory (global scope)."""
        self.persistent.store_preference(key, value)
        # Legacy compat
        self.long_term.store_user_preference(key, value, description)
    
    def get_user_preference(self, key: str, default: Any = None) -> Any:
        """Get user preference from persistent memory."""
        result = self.persistent.get_preference(key)
        if result is not None:
            return result
        # Fallback to legacy
        return self.long_term.get_user_preference(key, default)
    
    def record_lesson(self, lesson: str, context: str = None, 
                     confidence: float = 1.0) -> None:
        """Record a lesson learned."""
        self.long_term.record_lesson_learned(
            lesson=lesson,
            context=context,
            category=self.workspace,
            confidence=confidence
        )
    
    def get_relevant_lessons(self, query: str) -> List[Dict[str, Any]]:
        """Get lessons relevant to current context."""
        return self.long_term.search_lessons(query, min_confidence=0.6)
    
    def set_context_variable(self, name: str, value: Any) -> None:
        """Set context variable for current session."""
        self.working.set_context_variable(name, value)
        
        # Cache frequently accessed context
        self._context_cache[name] = value
    
    def get_context_variable(self, name: str) -> Optional[Any]:
        """Get context variable value."""
        # Check cache first
        if name in self._context_cache:
            return self._context_cache[name]
        
        return self.working.get_context_variable(name)
    
    def consolidate_memories(self) -> Dict[str, Any]:
        """
        Consolidate and optimize memory across all tiers.
        
        Returns:
            Summary of consolidation actions
        """
        actions = {
            "working_memory_cleaned": 0,
            "project_entries_processed": 0,
            "knowledge_consolidated": {},
            "preferences_updated": 0
        }
        
        # Clean up old working memory entries
        old_size = len(self.working._data)
        self.working._cleanup_expired_entries()
        actions["working_memory_cleaned"] = old_size - len(self.working._data)
        
        # Promote important working memory to project memory
        conversation_history = self.working.get_conversation_history()
        important_turns = [
            turn for turn in conversation_history 
            if self._is_worth_preserving(turn)
        ]
        
        for turn in important_turns:
            self.project.store(
                content=turn["content"],
                metadata={
                    "source": self.brain_name,
                    "type": turn["type"],
                    "original_timestamp": turn["timestamp"],
                    "promoted_from": "working_memory"
                }
            )
        
        actions["project_entries_processed"] = len(important_turns)
        
        # Consolidate long-term knowledge
        actions["knowledge_consolidated"] = self.long_term.consolidate_knowledge()
        
        return actions
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics."""
        return {
            "working_memory": self.working.get_stats(),
            "persistent_memory": self.persistent.get_stats(),
            "brain_name": self.brain_name,
            "project_name": self.project_name,
            "workspace": self.workspace,
            "context_cache_size": len(self._context_cache)
        }
    
    def clear_working_memory(self) -> None:
        """Clear all working memory for this brain."""
        self.working.clear()
        self._context_cache.clear()
    
    def change_project(self, new_project: str) -> None:
        """
        Switch to a different project.
        
        This changes the project memory scope but preserves
        working memory and long-term memory.
        """
        self.project_name = new_project
        
        # Reinitialize project memory with new scope
        self.project = ProjectMemory(
            project_name=new_project,
            workspace=self.workspace,
            storage_dir=self.project.storage_dir
        )
        
        # Update context
        self.set_context_variable("current_project", new_project)
    
    def _determine_memory_tier(self, content: str, metadata: Dict[str, Any]) -> str:
        """
        Automatically determine appropriate memory tier for content.
        
        Rules:
        - Temporary/session data → working
        - Project-specific knowledge → project
        - General/cross-project knowledge → long_term
        """
        content_lower = content.lower()
        content_type = metadata.get("type", "")
        
        # Temporary indicators
        temp_indicators = ["temp", "debug", "test", "session", "current"]
        if any(indicator in content_lower or indicator in content_type for indicator in temp_indicators):
            return "working"
        
        # Long-term indicators
        lt_indicators = ["learn", "remember", "always", "rule", "preference", "lesson"]
        if any(indicator in content_lower or indicator in content_type for indicator in lt_indicators):
            return "long_term"
        
        # Project indicators (default for substantial content)
        if len(content) > 200 or metadata.get("important", False):
            return "project"
        
        # Default to working memory for short, unspecified content
        return "working"
    
    def _is_worth_preserving(self, turn: Dict[str, Any]) -> bool:
        """
        Determine if a conversation turn should be promoted to project memory.
        
        Criteria:
        - Contains decisions or important information
        - Has explicit metadata marking it as important
        - Contains code, data, or structured information
        """
        content = turn.get("content", "").lower()
        metadata = turn.get("metadata", {})
        
        # Explicit importance flag
        if metadata.get("important", False):
            return True
        
        # Decision or planning content
        decision_indicators = ["decide", "plan", "strategy", "approach", "solution"]
        if any(indicator in content for indicator in decision_indicators):
            return True
        
        # Code or structured data
        code_indicators = ["def ", "class ", "import ", "```", "{", "SELECT", "CREATE"]
        if any(indicator in content for indicator in code_indicators):
            return True
        
        # Long content (likely substantial)
        if len(content) > 500:
            return True
        
        return False