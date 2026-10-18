"""Long Term Memory - Cross-project knowledge storage for BigBrain."""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .project_memory import MockEmbedding, ProjectMemoryEntry
from .paths import legacy_storage_dir


class LongTermMemory:
    """
    Tier 3: Long-term Memory - Cross-project, cross-workspace knowledge.
    
    Stores persistent knowledge that transcends individual projects:
    - User preferences and patterns
    - Learned lessons and best practices
    - General domain knowledge
    - Cross-project insights
    - System configuration and rules
    
    Key Features:
    - Global scope across all workspaces and projects
    - Semantic search with confidence scoring
    - Knowledge consolidation and deduplication
    - Automatic categorization
    - Temporal knowledge tracking (what changed when)
    """
    
    def __init__(self, storage_dir: Path = None):
        """
        Initialize long-term memory.
        
        Args:
            storage_dir: Directory for persistent storage
        """
        self.storage_dir = legacy_storage_dir('long_term', storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Storage files
        self.knowledge_file = self.storage_dir / "knowledge.json"
        self.preferences_file = self.storage_dir / "preferences.json"
        self.lessons_file = self.storage_dir / "lessons.json"
        
        # In-memory storage
        self.knowledge_entries: Dict[str, ProjectMemoryEntry] = {}
        self.user_preferences: Dict[str, Any] = {}
        self.learned_lessons: List[Dict[str, Any]] = []
        
        # Load existing data
        self._load_all_data()
    
    def store_knowledge(self, content: str, category: str = "general",
                       metadata: Dict[str, Any] = None) -> str:
        """
        Store long-term knowledge.
        
        Args:
            content: Knowledge content
            category: Knowledge category (user, technical, business, etc.)
            metadata: Additional metadata
            
        Returns:
            Entry ID
        """
        metadata = metadata or {}
        metadata.update({
            "category": category,
            "source": "long_term",
            "type": "knowledge"
        })
        
        # Check for similar existing knowledge to avoid duplication
        similar_entries = self.search_knowledge(content, limit=3, similarity_threshold=0.8)
        if similar_entries:
            # Update existing entry instead of creating duplicate
            existing_id = similar_entries[0]["id"]
            existing_entry = self.knowledge_entries[existing_id]
            
            # Merge content if significantly different
            if similar_entries[0]["similarity"] < 0.95:
                merged_content = f"{existing_entry.content}\n\n---\n\n{content}"
                existing_entry.content = merged_content
                existing_entry.metadata["updated"] = time.time()
                existing_entry.metadata["update_count"] = existing_entry.metadata.get("update_count", 0) + 1
                
                self._save_knowledge()
                return existing_id
        
        # Create new entry
        entry = ProjectMemoryEntry(content, metadata)
        self.knowledge_entries[entry.id] = entry
        
        self._save_knowledge()
        return entry.id
    
    def search_knowledge(self, query: str, category: str = None,
                        limit: int = 5, similarity_threshold: float = 0.2) -> List[Dict[str, Any]]:
        """
        Search through long-term knowledge.
        
        Args:
            query: Search query
            category: Optional category filter
            limit: Maximum results
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of knowledge entries with similarity scores
        """
        if not query.strip():
            return []
        
        query_embedding = MockEmbedding.embed_text(query)
        results = []
        
        for entry in self.knowledge_entries.values():
            # Category filter
            if category and entry.metadata.get("category") != category:
                continue
            
            # Calculate similarity
            similarity = MockEmbedding.cosine_similarity(query_embedding, entry.embedding)
            
            if similarity >= similarity_threshold:
                results.append({
                    "id": entry.id,
                    "content": entry.content,
                    "category": entry.metadata.get("category", "general"),
                    "similarity": similarity,
                    "metadata": entry.metadata,
                    "timestamp": entry.timestamp
                })
        
        # Sort by similarity
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]
    
    def store_user_preference(self, key: str, value: Any, 
                             description: str = None) -> None:
        """
        Store a user preference.
        
        Args:
            key: Preference key
            value: Preference value
            description: Optional description
        """
        self.user_preferences[key] = {
            "value": value,
            "description": description,
            "timestamp": time.time(),
            "updated_count": self.user_preferences.get(key, {}).get("updated_count", 0) + 1
        }
        
        self._save_preferences()
    
    def get_user_preference(self, key: str, default: Any = None) -> Any:
        """
        Get a user preference value.
        
        Args:
            key: Preference key
            default: Default value if not found
            
        Returns:
            Preference value or default
        """
        pref_data = self.user_preferences.get(key)
        return pref_data["value"] if pref_data else default
    
    def get_all_preferences(self) -> Dict[str, Any]:
        """Get all user preferences."""
        return {key: data["value"] for key, data in self.user_preferences.items()}
    
    def record_lesson_learned(self, lesson: str, context: str = None,
                             category: str = "general", 
                             confidence: float = 1.0) -> None:
        """
        Record a lesson learned from experience.
        
        Args:
            lesson: The lesson content
            context: Context where this was learned
            category: Lesson category
            confidence: Confidence in this lesson (0.0-1.0)
        """
        lesson_entry = {
            "id": f"lesson_{int(time.time())}_{len(self.learned_lessons)}",
            "lesson": lesson,
            "context": context,
            "category": category,
            "confidence": confidence,
            "timestamp": time.time(),
            "reinforcement_count": 1  # How many times this lesson was confirmed
        }
        
        # Check for similar lessons
        for existing_lesson in self.learned_lessons:
            if self._lessons_are_similar(lesson, existing_lesson["lesson"]):
                # Reinforce existing lesson instead of adding duplicate
                existing_lesson["reinforcement_count"] += 1
                existing_lesson["confidence"] = min(1.0, existing_lesson["confidence"] + 0.1)
                existing_lesson["last_reinforced"] = time.time()
                if context:
                    existing_lesson["additional_context"] = existing_lesson.get("additional_context", [])
                    existing_lesson["additional_context"].append(context)
                
                self._save_lessons()
                return
        
        self.learned_lessons.append(lesson_entry)
        self._save_lessons()
    
    def get_lessons_by_category(self, category: str = None) -> List[Dict[str, Any]]:
        """
        Get lessons learned, optionally filtered by category.
        
        Args:
            category: Optional category filter
            
        Returns:
            List of lessons
        """
        lessons = self.learned_lessons
        
        if category:
            lessons = [l for l in lessons if l.get("category") == category]
        
        # Sort by confidence and reinforcement
        lessons.sort(key=lambda x: (x["confidence"], x["reinforcement_count"]), reverse=True)
        
        return lessons
    
    def search_lessons(self, query: str, min_confidence: float = 0.5) -> List[Dict[str, Any]]:
        """
        Search through learned lessons.
        
        Args:
            query: Search query
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of matching lessons
        """
        query_lower = query.lower()
        results = []
        
        for lesson in self.learned_lessons:
            if lesson["confidence"] < min_confidence:
                continue
            
            score = 0.0
            
            # Search in lesson content
            if query_lower in lesson["lesson"].lower():
                score += 0.5
            
            # Search in context
            if lesson.get("context") and query_lower in lesson["context"].lower():
                score += 0.3
            
            # Search in category
            if lesson.get("category") and query_lower in lesson["category"].lower():
                score += 0.2
            
            if score > 0:
                results.append({
                    **lesson,
                    "search_score": score
                })
        
        # Sort by search score and confidence
        results.sort(key=lambda x: (x["search_score"], x["confidence"]), reverse=True)
        return results
    
    def consolidate_knowledge(self) -> Dict[str, Any]:
        """
        Consolidate and deduplicate knowledge entries.
        
        Returns:
            Summary of consolidation actions
        """
        original_count = len(self.knowledge_entries)
        duplicates_removed = 0
        entries_merged = 0
        
        # Find and merge similar entries
        entries_list = list(self.knowledge_entries.values())
        to_remove = set()
        
        for i, entry1 in enumerate(entries_list):
            if entry1.id in to_remove:
                continue
            
            for j, entry2 in enumerate(entries_list[i+1:], i+1):
                if entry2.id in to_remove:
                    continue
                
                similarity = MockEmbedding.cosine_similarity(entry1.embedding, entry2.embedding)
                
                if similarity > 0.9:  # Very similar entries
                    # Merge entry2 into entry1
                    entry1.content += f"\n\n--- Merged Content ---\n\n{entry2.content}"
                    entry1.metadata["merged_entries"] = entry1.metadata.get("merged_entries", 0) + 1
                    entry1.metadata["last_merged"] = time.time()
                    
                    to_remove.add(entry2.id)
                    entries_merged += 1
        
        # Remove duplicate entries
        for entry_id in to_remove:
            if entry_id in self.knowledge_entries:
                del self.knowledge_entries[entry_id]
                duplicates_removed += 1
        
        if duplicates_removed > 0:
            self._save_knowledge()
        
        return {
            "original_entries": original_count,
            "duplicates_removed": duplicates_removed,
            "entries_merged": entries_merged,
            "final_entries": len(self.knowledge_entries)
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get long-term memory statistics."""
        categories = {}
        for entry in self.knowledge_entries.values():
            cat = entry.metadata.get("category", "general")
            categories[cat] = categories.get(cat, 0) + 1
        
        lesson_categories = {}
        for lesson in self.learned_lessons:
            cat = lesson.get("category", "general")
            lesson_categories[cat] = lesson_categories.get(cat, 0) + 1
        
        return {
            "knowledge_entries": len(self.knowledge_entries),
            "user_preferences": len(self.user_preferences),
            "learned_lessons": len(self.learned_lessons),
            "knowledge_categories": categories,
            "lesson_categories": lesson_categories,
            "storage_size_mb": self._estimate_storage_size(),
            "high_confidence_lessons": len([l for l in self.learned_lessons if l["confidence"] > 0.8])
        }
    
    def _lessons_are_similar(self, lesson1: str, lesson2: str) -> bool:
        """Check if two lessons are similar enough to merge."""
        # Simple similarity check - in production would use embeddings
        lesson1_words = set(lesson1.lower().split())
        lesson2_words = set(lesson2.lower().split())
        
        if len(lesson1_words) == 0 or len(lesson2_words) == 0:
            return False
        
        intersection = lesson1_words.intersection(lesson2_words)
        union = lesson1_words.union(lesson2_words)
        
        jaccard_similarity = len(intersection) / len(union)
        return jaccard_similarity > 0.6
    
    def _load_all_data(self) -> None:
        """Load all long-term memory data from disk."""
        self._load_knowledge()
        self._load_preferences()
        self._load_lessons()
    
    def _load_knowledge(self) -> None:
        """Load knowledge entries from disk."""
        if not self.knowledge_file.exists():
            return
        
        try:
            with open(self.knowledge_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for entry_data in data.get("entries", []):
                entry = ProjectMemoryEntry.from_dict(entry_data)
                self.knowledge_entries[entry.id] = entry
                
        except Exception as e:
            print(f"Warning: Failed to load long-term knowledge: {e}")
    
    def _load_preferences(self) -> None:
        """Load user preferences from disk."""
        if not self.preferences_file.exists():
            return
        
        try:
            with open(self.preferences_file, 'r', encoding='utf-8') as f:
                self.user_preferences = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load user preferences: {e}")
    
    def _load_lessons(self) -> None:
        """Load learned lessons from disk."""
        if not self.lessons_file.exists():
            return
        
        try:
            with open(self.lessons_file, 'r', encoding='utf-8') as f:
                self.learned_lessons = json.load(f).get("lessons", [])
        except Exception as e:
            print(f"Warning: Failed to load learned lessons: {e}")
    
    def _save_knowledge(self) -> None:
        """Save knowledge entries to disk."""
        try:
            data = {
                "last_updated": time.time(),
                "entries": [entry.to_dict() for entry in self.knowledge_entries.values()]
            }
            
            with open(self.knowledge_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            print(f"Warning: Failed to save long-term knowledge: {e}")
    
    def _save_preferences(self) -> None:
        """Save user preferences to disk."""
        try:
            with open(self.preferences_file, 'w', encoding='utf-8') as f:
                json.dump(self.user_preferences, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save user preferences: {e}")
    
    def _save_lessons(self) -> None:
        """Save learned lessons to disk."""
        try:
            data = {
                "last_updated": time.time(),
                "lessons": self.learned_lessons
            }
            
            with open(self.lessons_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save learned lessons: {e}")
    
    def _estimate_storage_size(self) -> float:
        """Estimate storage size in MB."""
        total_size = 0
        
        for file_path in [self.knowledge_file, self.preferences_file, self.lessons_file]:
            try:
                if file_path.exists():
                    total_size += file_path.stat().st_size
            except Exception:
                pass
        
        return total_size / (1024 * 1024)
