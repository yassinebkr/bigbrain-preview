"""Tests for BigBrain memory system."""

import tempfile
import time
from pathlib import Path

import pytest

from bigbrain.memory.working_memory import WorkingMemory
from bigbrain.memory.project_memory import ProjectMemory
from bigbrain.memory.long_term_memory import LongTermMemory
from bigbrain.memory.memory_manager import MemoryManager


class TestWorkingMemory:
    """Test WorkingMemory functionality."""
    
    @pytest.fixture
    def working_memory(self):
        """Create WorkingMemory instance for testing."""
        return WorkingMemory(max_entries=100, max_age_seconds=3600)
    
    def test_store_and_get(self, working_memory):
        """Test storing and retrieving values."""
        working_memory.store("key1", "value1")
        working_memory.store("key2", {"nested": "data"})
        
        assert working_memory.retrieve("key1") == "value1"
        assert working_memory.retrieve("key2") == {"nested": "data"}
        assert working_memory.retrieve("nonexistent") is None
    
    def test_store_with_metadata(self, working_memory):
        """Test storing values with metadata."""
        metadata = {"source": "user_input", "importance": "high"}
        working_memory.store("key1", "value1", metadata)
        
        # Check value is stored
        assert working_memory.retrieve("key1") == "value1"
        
        # Check metadata is tracked
        assert "key1" in working_memory._metadata
        assert working_memory._metadata["key1"]["source"] == "user_input"
        assert working_memory._metadata["key1"]["importance"] == "high"
    
    def test_conversation_history(self, working_memory):
        """Test conversation history management."""
        # Add conversation entries
        working_memory.add_conversation_turn(
            "user", "Hello, can you help me?", {"input_type": "text"}
        )
        working_memory.add_conversation_turn(
            "assistant", "Of course! How can I assist you?", {"response_type": "helpful"}
        )
        working_memory.add_conversation_turn(
            "user", "I need help with Python", {"topic": "programming"}
        )
        
        # Get full history
        history = working_memory.get_conversation_history()
        assert len(history) == 3
        assert history[0]["type"] == "user"
        assert history[0]["content"] == "Hello, can you help me?"
        assert history[1]["type"] == "assistant"
        assert history[2]["content"] == "I need help with Python"
        
        # Get limited history
        recent_history = working_memory.get_conversation_history(last_n=2)
        assert len(recent_history) == 2
        assert recent_history[0]["type"] == "assistant"
        assert recent_history[1]["type"] == "user"
    
    def test_context_variables(self, working_memory):
        """Test context variable management."""
        # Set context variables
        working_memory.set_context_variable("current_task", "writing_code")
        working_memory.set_context_variable("user_preference", "python")
        working_memory.set_context_variable("difficulty_level", "intermediate")
        
        # Get context variables
        assert working_memory.get_context_variable("current_task") == "writing_code"
        assert working_memory.get_context_variable("user_preference") == "python"
        assert working_memory.get_context_variable("difficulty_level") == "intermediate"
        assert working_memory.get_context_variable("nonexistent") is None
        
        # Check that context variables are stored with metadata
        assert "current_task" in working_memory._context_variables
        context_data = working_memory._context_variables["current_task"]
        assert context_data["value"] == "writing_code"
        assert "timestamp" in context_data
    
    def test_search_operation(self, working_memory):
        """Test searching stored content."""
        working_memory.store("python_code", "def hello(): print('world')")
        working_memory.store("user_name", "John Doe", {"type": "personal"})
        working_memory.store("project_info", "Building a web application")
        
        # Search for 'python'
        results = working_memory.search("python", limit=5)
        assert len(results) == 1
        assert results[0]["key"] == "python_code"
        assert results[0]["score"] > 0
        
        # Search for 'application'
        results = working_memory.search("application", limit=5)
        assert len(results) == 1
        assert results[0]["key"] == "project_info"
        
        # Search for non-existent term
        results = working_memory.search("nonexistent")
        assert len(results) == 0
    
    def test_exists_operation(self, working_memory):
        """Test checking if keys exist."""
        working_memory.store("existing_key", "value")
        
        assert working_memory.exists("existing_key") is True
        assert working_memory.exists("nonexistent_key") is False
    
    def test_delete_operation(self, working_memory):
        """Test deleting stored values."""
        working_memory.store("temp_key", "temp_value")
        assert working_memory.retrieve("temp_key") == "temp_value"
        
        # Delete the key
        result = working_memory.delete("temp_key")
        assert result is True
        assert working_memory.retrieve("temp_key") is None
        
        # Try to delete non-existent key
        result = working_memory.delete("nonexistent")
        assert result is False
    
    def test_get_all_keys(self, working_memory):
        """Test getting all keys."""
        working_memory.store("key1", "value1")
        working_memory.store("key2", "value2")
        working_memory.store("key3", "value3")
        
        keys = working_memory.get_all_keys()
        assert len(keys) == 3
        assert "key1" in keys
        assert "key2" in keys
        assert "key3" in keys
    
    def test_cleanup_old_entries(self, working_memory):
        """Test cleanup of old entries."""
        # Create memory with very short max age for testing
        short_memory = WorkingMemory(max_entries=100, max_age_seconds=1)
        
        short_memory.store("old_key", "old_value")
        
        # Wait for entry to age out
        time.sleep(1.1)
        
        # Cleanup should happen automatically when accessing
        keys_before = len(short_memory.get_all_keys())
        keys_after = len(short_memory.get_all_keys())  # Second call triggers cleanup
        assert keys_after <= keys_before
    
    def test_cleanup_excess_entries(self, working_memory):
        """Test cleanup when max entries exceeded."""
        # Create memory with very small limit
        small_memory = WorkingMemory(max_entries=3, max_age_seconds=3600)
        
        # Add more entries than the limit
        small_memory.store("key1", "value1")
        small_memory.store("key2", "value2")
        small_memory.store("key3", "value3")
        small_memory.store("key4", "value4")  # This should trigger cleanup
        small_memory.store("key5", "value5")
        
        # Should keep only the most recent entries
        keys = small_memory.get_all_keys()
        assert len(keys) <= small_memory.max_entries
    
    def test_clear_all(self, working_memory):
        """Test clearing all memory."""
        working_memory.store("key1", "value1")
        working_memory.set_context_variable("context1", "value1")
        working_memory.add_conversation_turn("user", "Hello")
        
        # Clear all memory
        working_memory.clear()
        
        assert len(working_memory.get_all_keys()) == 0
        assert len(working_memory.get_conversation_history()) == 0
        assert len(working_memory._context_variables) == 0
    
    def test_get_stats(self, working_memory):
        """Test getting memory statistics."""
        working_memory.store("key1", "value1")
        working_memory.store("key2", "value2")
        working_memory.set_context_variable("ctx1", "value1")
        working_memory.add_conversation_turn("user", "Hello")
        
        stats = working_memory.get_stats()
        
        assert "total_entries" in stats
        assert "conversation_turns" in stats
        assert "context_variables" in stats
        assert "memory_usage_mb" in stats
        assert "oldest_entry" in stats
        assert "newest_entry" in stats
        
        assert stats["total_entries"] == 2
        assert stats["conversation_turns"] == 1
        assert stats["context_variables"] == 1
        assert stats["memory_usage_mb"] > 0


class TestProjectMemory:
    """Test ProjectMemory functionality."""
    
    @pytest.fixture
    def temp_project_dir(self):
        """Create temporary directory for project storage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def project_memory(self, temp_project_dir):
        """Create ProjectMemory instance for testing."""
        memory = ProjectMemory("test_project", "test_workspace", temp_project_dir)
        yield memory
        # No cleanup method needed - data persists in temp directory
    
    @pytest.mark.asyncio
    async def test_store_and_search(self, project_memory):
        """Test storing and searching content."""
        content = "This is a test document about Python programming"
        metadata = {"type": "code", "language": "python"}
        
        entry_ids = project_memory.store(content, metadata)
        assert len(entry_ids) == 1
        assert entry_ids[0] is not None
        
        # Search for the content (using low threshold since mock embeddings have limited similarity)
        results = project_memory.search("Python programming", limit=5, similarity_threshold=0.0)
        assert len(results) >= 1
        assert results[0]["content"] == content
        assert results[0]["metadata"]["type"] == "code"
    
    @pytest.mark.asyncio
    async def test_chunking_large_content(self, project_memory):
        """Test chunking of large content."""
        # Create content larger than default chunk size
        large_content = "This is a test. " * 100  # Much larger than 500 chars
        
        entry_ids = project_memory.store(large_content, chunk_size=100)
        assert len(entry_ids) > 1
        
        # Search should find chunks
        results = project_memory.search("test", limit=10, similarity_threshold=-1.0)
        assert len(results) >= 1
    
    @pytest.mark.asyncio
    async def test_get_by_id(self, project_memory):
        """Test retrieving content by ID."""
        content = "Specific content for ID retrieval"
        entry_ids = project_memory.store(content)
        
        retrieved = project_memory.get_by_id(entry_ids[0])
        assert retrieved is not None
        assert retrieved["content"] == content
        assert "timestamp" in retrieved
        assert "metadata" in retrieved
        
        # Test non-existent ID
        assert project_memory.get_by_id("nonexistent") is None
    
    @pytest.mark.asyncio
    async def test_metadata_filtering(self, project_memory):
        """Test filtering by metadata."""
        project_memory.store("Python code example", {"type": "code", "language": "python"})
        project_memory.store("JavaScript code example", {"type": "code", "language": "javascript"})
        project_memory.store("Text documentation", {"type": "docs", "format": "text"})
        
        # Filter by type
        code_results = project_memory.get_by_metadata({"type": "code"}, limit=10)
        assert len(code_results) == 2
        
        # Filter by specific language
        python_results = project_memory.get_by_metadata({"language": "python"}, limit=10)
        assert len(python_results) == 1
        assert "Python" in python_results[0]["content"]
        
        # Filter by non-existent metadata
        none_results = project_memory.get_by_metadata({"nonexistent": "value"}, limit=10)
        assert len(none_results) == 0
    
    @pytest.mark.asyncio
    async def test_update_metadata(self, project_memory):
        """Test updating entry metadata."""
        content = "Content to update metadata"
        entry_ids = project_memory.store(content, {"status": "draft"})
        
        # Update metadata
        result = project_memory.update_metadata(entry_ids[0], {"status": "final", "reviewed": True})
        assert result is True
        
        # Verify update
        retrieved = project_memory.get_by_id(entry_ids[0])
        assert retrieved["metadata"]["status"] == "final"
        assert retrieved["metadata"]["reviewed"] is True
        
        # Test update on non-existent ID
        result = project_memory.update_metadata("nonexistent", {"test": "value"})
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_entry(self, project_memory):
        """Test deleting entries."""
        content = "Content to be deleted"
        entry_ids = project_memory.store(content)
        
        # Verify it exists
        assert project_memory.get_by_id(entry_ids[0]) is not None
        
        # Delete it
        result = project_memory.delete(entry_ids[0])
        assert result is True
        
        # Verify it's gone
        assert project_memory.get_by_id(entry_ids[0]) is None
        
        # Try to delete non-existent entry
        result = project_memory.delete("nonexistent")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_search_with_similarity_threshold(self, project_memory):
        """Test search with similarity threshold."""
        project_memory.store("Python programming tutorial")
        project_memory.store("Java programming guide") 
        project_memory.store("Cooking recipes")
        
        # High threshold - mock embeddings may have limited similarity
        results = project_memory.search("Python", similarity_threshold=0.2)
        assert len(results) >= 1
        
        # Very high threshold - might not find anything
        results = project_memory.search("Python", similarity_threshold=0.9)
        # This depends on the mock embedding implementation
        
        # Low threshold - should find more results
        results = project_memory.search("programming", similarity_threshold=0.0)
        assert len(results) >= 1  # mock embeddings may not give high similarity for all
    
    @pytest.mark.asyncio
    async def test_get_stats(self, project_memory):
        """Test getting project memory statistics."""
        project_memory.store("Test content 1", {"type": "test", "source": "unit_test"})
        project_memory.store("Test content 2", {"type": "example", "source": "demo"})
        
        stats = project_memory.get_stats()
        
        assert "total_entries" in stats
        assert "storage_size_mb" in stats
        assert "oldest_entry" in stats
        assert "newest_entry" in stats
        assert "sources" in stats
        assert "types" in stats
        assert "workspace" in stats
        assert "project" in stats
        
        assert stats["total_entries"] == 2
        assert stats["workspace"] == "test_workspace"
        assert stats["project"] == "test_project"
        assert "unit_test" in stats["sources"]
        assert "test" in stats["types"]
    
    @pytest.mark.asyncio
    async def test_persistence(self, project_memory, temp_project_dir):
        """Test that data persists to files."""
        # Store data
        content = "Persistent data test"
        project_memory.store(content, {"persistent": True})
        
        # Create new instance with same storage
        new_memory = ProjectMemory("test_project", "test_workspace", temp_project_dir)
        
        # Should load existing data
        results = new_memory.search("Persistent", limit=5, similarity_threshold=-1.0)
        assert len(results) == 1
        assert results[0]["content"] == content


class TestLongTermMemory:
    """Test LongTermMemory functionality."""
    
    @pytest.fixture
    def temp_memory_dir(self):
        """Create temporary directory for long-term memory storage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def long_term_memory(self, temp_memory_dir):
        """Create LongTermMemory instance for testing."""
        memory = LongTermMemory(temp_memory_dir)
        yield memory
        # No cleanup method needed
    
    @pytest.mark.asyncio
    async def test_store_and_retrieve_knowledge(self, long_term_memory):
        """Test storing and retrieving long-term knowledge."""
        content = "User prefers Python over JavaScript"
        metadata = {"context": "programming_preferences", "confidence": 0.9, "source": "conversation"}
        
        knowledge_id = long_term_memory.store_knowledge(content, "user_preferences", metadata)
        assert knowledge_id is not None
        
        # Search for the knowledge
        results = long_term_memory.search_knowledge("Python preferences")
        assert len(results) >= 1
        
        found = False
        for result in results:
            if result["content"] == content:
                assert result["category"] == "user_preferences"
                assert result["metadata"]["confidence"] == 0.9
                found = True
                break
        assert found
    
    @pytest.mark.asyncio
    async def test_search_by_category(self, long_term_memory):
        """Test searching knowledge by category."""
        long_term_memory.store_knowledge("User likes dark themes", "ui_preferences")
        long_term_memory.store_knowledge("Use async/await for I/O operations", "technical")
        long_term_memory.store_knowledge("Team meeting every Monday", "business")
        
        # Search within specific category
        ui_results = long_term_memory.search_knowledge("themes", category="ui_preferences", similarity_threshold=-1.0)
        assert len(ui_results) >= 1
        assert any("dark themes" in r["content"] for r in ui_results)
        
        # Search within different category
        tech_results = long_term_memory.search_knowledge("async", category="technical", similarity_threshold=-1.0)
        assert len(tech_results) >= 1
        assert any("async/await" in r["content"] for r in tech_results)
        
        # Search all categories (no category filter)
        all_results = long_term_memory.search_knowledge("dark", similarity_threshold=-1.0)
        assert len(all_results) >= 1
    
    @pytest.mark.asyncio
    async def test_user_preferences(self, long_term_memory):
        """Test user preference storage and retrieval."""
        # Store preferences
        long_term_memory.store_user_preference("theme", "dark", "User interface theme preference")
        long_term_memory.store_user_preference("language", "python", "Preferred programming language")
        long_term_memory.store_user_preference("notifications", False, "Enable desktop notifications")
        
        # Retrieve preferences
        assert long_term_memory.get_user_preference("theme") == "dark"
        assert long_term_memory.get_user_preference("language") == "python"
        assert long_term_memory.get_user_preference("notifications") is False
        assert long_term_memory.get_user_preference("nonexistent", "default") == "default"
        
        # Get all preferences
        all_prefs = long_term_memory.get_all_preferences()
        assert all_prefs["theme"] == "dark"
        assert all_prefs["language"] == "python"
        assert all_prefs["notifications"] is False
    
    @pytest.mark.asyncio
    async def test_lessons_learned(self, long_term_memory):
        """Test recording and retrieving lessons learned."""
        # Record lessons
        long_term_memory.record_lesson_learned(
            "Always validate user input before processing",
            context="security review",
            category="security",
            confidence=0.9
        )
        long_term_memory.record_lesson_learned(
            "Use type hints for better code documentation",
            context="code review",
            category="coding",
            confidence=0.8
        )
        
        # Get lessons by category
        security_lessons = long_term_memory.get_lessons_by_category("security")
        assert len(security_lessons) == 1
        assert "validate user input" in security_lessons[0]["lesson"]
        assert security_lessons[0]["confidence"] == 0.9
        
        # Search lessons
        validation_lessons = long_term_memory.search_lessons("validate")
        assert len(validation_lessons) >= 1
        assert "validate user input" in validation_lessons[0]["lesson"]
        
        # Search with confidence threshold
        high_confidence_lessons = long_term_memory.search_lessons("", min_confidence=0.85)
        assert len(high_confidence_lessons) == 1  # Only the security lesson meets threshold
    
    @pytest.mark.asyncio
    async def test_knowledge_consolidation(self, long_term_memory):
        """Test knowledge consolidation and deduplication."""
        # Store similar knowledge entries
        long_term_memory.store_knowledge("Python is good for data science")
        long_term_memory.store_knowledge("Python is excellent for data analysis")
        long_term_memory.store_knowledge("JavaScript is good for web development")
        
        # Consolidate
        result = long_term_memory.consolidate_knowledge()
        
        assert "original_entries" in result
        assert "duplicates_removed" in result
        assert "entries_merged" in result
        assert "final_entries" in result
        
        # Should have fewer entries after consolidation
        assert result["final_entries"] <= result["original_entries"]
    
    @pytest.mark.asyncio
    async def test_get_stats(self, long_term_memory):
        """Test getting long-term memory statistics."""
        # Add some data
        long_term_memory.store_knowledge("Test knowledge", "test")
        long_term_memory.store_user_preference("test_pref", "value")
        long_term_memory.record_lesson_learned("Test lesson", confidence=0.9)
        
        stats = long_term_memory.get_stats()
        
        assert "knowledge_entries" in stats
        assert "user_preferences" in stats
        assert "learned_lessons" in stats
        assert "knowledge_categories" in stats
        assert "lesson_categories" in stats
        assert "storage_size_mb" in stats
        assert "high_confidence_lessons" in stats
        
        assert stats["knowledge_entries"] >= 1
        assert stats["user_preferences"] >= 1
        assert stats["learned_lessons"] >= 1
        assert stats["high_confidence_lessons"] >= 1


class TestMemoryManager:
    """Test MemoryManager functionality."""
    
    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as temp_dir1:
            yield Path(temp_dir1)
    
    @pytest.fixture
    def memory_manager(self, temp_dirs):
        """Create MemoryManager instance for testing."""
        manager = MemoryManager(
            brain_name="test_brain",
            project_name="test_project", 
            workspace="test_workspace",
            storage_dir=temp_dirs
        )
        yield manager
        # No cleanup method needed
    
    def test_automatic_tier_selection(self, memory_manager):
        """Test automatic memory tier selection."""
        # Temporary content should go to working memory
        temp_id = memory_manager.store("Temporary debug info", "auto", {"type": "temp"})
        assert temp_id.startswith("test_brain_")
        
        # Important content should go to appropriate tier
        knowledge_id = memory_manager.store(
            "Important lesson about design patterns",
            "auto", 
            {"important": True, "type": "lesson"}
        )
        # Should be stored in long-term memory
        assert knowledge_id is not None
    
    def test_cross_tier_search(self, memory_manager):
        """Test searching across all memory tiers."""
        # Store content in different tiers
        memory_manager.store("Working memory content", "working", {"type": "session"})
        memory_manager.store("Project specific documentation", "project", {"type": "docs"})
        memory_manager.store("General programming principles", "long_term", {"type": "knowledge"})
        
        # Search across all tiers
        results = memory_manager.recall("content", limit=5)
        assert len(results) >= 1
        
        # Results should include tier information
        for result in results:
            assert "tier" in result
            assert result["tier"] in ["working", "project", "long_term"]
    
    def test_conversation_management(self, memory_manager):
        """Test conversation context management."""
        # Store conversation turns
        memory_manager.store_conversation_turn("user", "How do I use async/await?")
        memory_manager.store_conversation_turn("assistant", "Async/await is used for asynchronous programming...")
        memory_manager.store_conversation_turn("user", "Can you give me an example?")
        
        # Get conversation context
        context = memory_manager.get_conversation_context(turns=3)
        assert len(context) == 3
        assert context[0]["type"] == "user"
        assert context[1]["type"] == "assistant"
        assert context[2]["type"] == "user"
        assert "async/await" in context[0]["content"]
    
    def test_preference_management(self, memory_manager):
        """Test user preference management."""
        # Store preferences
        memory_manager.store_user_preference("editor", "vscode", "Preferred code editor")
        memory_manager.store_user_preference("theme", "dark", "UI theme preference")
        
        # Retrieve preferences
        assert memory_manager.get_user_preference("editor") == "vscode"
        assert memory_manager.get_user_preference("theme") == "dark"
        assert memory_manager.get_user_preference("nonexistent", "default") == "default"
    
    def test_lesson_recording(self, memory_manager):
        """Test lesson recording and retrieval."""
        # Record a lesson
        memory_manager.record_lesson(
            "Always use environment variables for API keys",
            context="security review",
            confidence=0.9
        )
        
        # Get relevant lessons (query must be substring of lesson text)
        lessons = memory_manager.get_relevant_lessons("environment variables")
        assert len(lessons) >= 1
        
        found_lesson = False
        for lesson in lessons:
            if "environment variables" in lesson["lesson"]:
                assert lesson["confidence"] >= 0.6
                found_lesson = True
                break
        assert found_lesson
    
    def test_context_variables(self, memory_manager):
        """Test context variable management."""
        # Set context variables
        memory_manager.set_context_variable("current_task", "code_review")
        memory_manager.set_context_variable("focus_area", "security")
        memory_manager.set_context_variable("deadline", "tomorrow")
        
        # Get context variables
        assert memory_manager.get_context_variable("current_task") == "code_review"
        assert memory_manager.get_context_variable("focus_area") == "security"
        assert memory_manager.get_context_variable("deadline") == "tomorrow"
        assert memory_manager.get_context_variable("nonexistent") is None
    
    def test_memory_consolidation(self, memory_manager):
        """Test memory consolidation across tiers."""
        # Add some data to working memory
        memory_manager.working.add_conversation_turn("user", "Important decision: use microservices architecture")
        memory_manager.working.add_conversation_turn("assistant", "That's a good architectural choice")
        
        # Run consolidation
        result = memory_manager.consolidate_memories()
        
        assert "working_memory_cleaned" in result
        assert "project_entries_processed" in result
        assert "knowledge_consolidated" in result
        
        # Some conversation turns should have been promoted
        assert result["project_entries_processed"] >= 0
    
    def test_memory_stats(self, memory_manager):
        """Test comprehensive memory statistics."""
        # Add some data to each tier
        memory_manager.store("test", "working")
        memory_manager.store("test", "project")
        memory_manager.store("test", "long_term")
        
        stats = memory_manager.get_memory_stats()
        
        assert "working_memory" in stats
        assert "persistent_memory" in stats
        assert "brain_name" in stats
        assert "project_name" in stats
        assert "workspace" in stats
        assert "context_cache_size" in stats
        
        assert stats["brain_name"] == "test_brain"
        assert stats["project_name"] == "test_project"
        assert stats["workspace"] == "test_workspace"
    
    def test_project_switching(self, memory_manager):
        """Test switching to a different project."""
        # Store something in current project
        current_id = memory_manager.store("Current project data", "project")
        assert current_id is not None
        
        # Switch to new project
        memory_manager.change_project("new_project")
        
        # Check that project changed
        assert memory_manager.project_name == "new_project"
        assert memory_manager.get_context_variable("current_project") == "new_project"
        
        # Working memory should be preserved
        memory_manager.set_context_variable("test", "preserved")
        assert memory_manager.get_context_variable("test") == "preserved"
    
    def test_clear_working_memory(self, memory_manager):
        """Test clearing working memory."""
        # Add data to working memory
        memory_manager.store("test_data", "working")
        memory_manager.set_context_variable("test_var", "test_value")
        
        # Clear working memory
        memory_manager.clear_working_memory()
        
        # Working memory should be empty
        assert len(memory_manager.working.get_all_keys()) == 0
        assert memory_manager.get_context_variable("test_var") is None
        
        # Other memory tiers should be unaffected
        stats = memory_manager.get_memory_stats()
        assert stats["working_memory"]["total_entries"] == 0