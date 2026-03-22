"""Project Memory - Persistent project-scoped storage for BigBrain."""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class MockEmbedding:
    """Mock embedding system for semantic search simulation."""
    
    @staticmethod
    def embed_text(text: str) -> List[float]:
        """
        Generate mock embeddings for text.
        
        In production, this would use Google text-embedding-004 or similar.
        For preview, we create deterministic pseudo-embeddings based on text.
        """
        # Simple hash-based pseudo-embedding
        hash_val = hash(text.lower()) % 1000000
        
        # Create 128-dim embedding with some randomness based on content
        embedding = []
        for i in range(128):
            val = (hash_val + i * 37) % 200 - 100  # Range -100 to 100
            embedding.append(val / 100.0)  # Normalize to -1 to 1
        
        return embedding
    
    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two embeddings."""
        import math
        
        if len(a) != len(b):
            return 0.0
        
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)


class ProjectMemoryEntry:
    """Single entry in project memory."""
    
    def __init__(self, content: str, metadata: Dict[str, Any] = None):
        self.id = str(uuid.uuid4())
        self.content = content
        self.metadata = metadata or {}
        self.timestamp = time.time()
        self.embedding = MockEmbedding.embed_text(content)
        
        # Auto-populate some metadata
        if "source" not in self.metadata:
            self.metadata["source"] = "unknown"
        if "type" not in self.metadata:
            self.metadata["type"] = "text"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "embedding": self.embedding
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectMemoryEntry':
        """Create from dictionary."""
        entry = cls.__new__(cls)
        entry.id = data["id"]
        entry.content = data["content"]
        entry.metadata = data["metadata"]
        entry.timestamp = data["timestamp"]
        entry.embedding = data["embedding"]
        return entry


class ProjectMemory:
    """
    Tier 2: Project Memory - Persistent project-scoped storage.
    
    Provides ChromaDB-like interface with vector similarity search
    for project-specific knowledge and context. Each workspace has
    its own project memory namespace.
    
    Key Features:
    - Persistent JSON-based storage (ChromaDB alternative for preview)
    - Semantic search via mock embeddings
    - Metadata filtering and tagging
    - Workspace-scoped namespacing
    - Chunk-based storage for efficient retrieval
    - Source attribution and timestamps
    """
    
    def __init__(self, project_name: str, workspace: str = None, 
                 storage_dir: Path = None):
        """
        Initialize project memory.
        
        Args:
            project_name: Name of the project
            workspace: Workspace name for namespacing
            storage_dir: Directory for persistent storage
        """
        self.project_name = project_name
        self.workspace = workspace or "default"
        
        # Setup storage
        self.storage_dir = storage_dir or Path("memory") / "projects"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.storage_file = self.storage_dir / f"{self.workspace}_{project_name}.json"
        
        # In-memory index for fast access
        self.entries: Dict[str, ProjectMemoryEntry] = {}
        self._load_from_disk()
    
    def store(self, content: str, metadata: Dict[str, Any] = None,
              chunk_size: int = 500) -> List[str]:
        """
        Store content in project memory with chunking.
        
        Args:
            content: Text content to store
            metadata: Associated metadata
            chunk_size: Size of chunks for large content
            
        Returns:
            List of entry IDs created
        """
        if not content.strip():
            return []
        
        metadata = metadata or {}
        entry_ids = []
        
        # Split into chunks if content is large
        chunks = self._chunk_content(content, chunk_size)
        
        for i, chunk in enumerate(chunks):
            chunk_metadata = metadata.copy()
            if len(chunks) > 1:
                chunk_metadata["chunk_index"] = i
                chunk_metadata["total_chunks"] = len(chunks)
                chunk_metadata["chunk_id"] = f"{metadata.get('id', 'content')}_{i}"
            
            entry = ProjectMemoryEntry(chunk, chunk_metadata)
            self.entries[entry.id] = entry
            entry_ids.append(entry.id)
        
        # Save to disk
        self._save_to_disk()
        
        return entry_ids
    
    def search(self, query: str, limit: int = 5, 
              metadata_filter: Dict[str, Any] = None,
              similarity_threshold: float = 0.1) -> List[Dict[str, Any]]:
        """
        Semantic search through project memory.
        
        Args:
            query: Search query
            limit: Maximum results to return
            metadata_filter: Filter by metadata fields
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of matching entries with similarity scores
        """
        if not query.strip():
            return []
        
        query_embedding = MockEmbedding.embed_text(query)
        results = []
        
        for entry in self.entries.values():
            # Apply metadata filter
            if metadata_filter:
                if not self._matches_filter(entry.metadata, metadata_filter):
                    continue
            
            # Calculate similarity
            similarity = MockEmbedding.cosine_similarity(query_embedding, entry.embedding)
            
            if similarity >= similarity_threshold:
                results.append({
                    "id": entry.id,
                    "content": entry.content,
                    "metadata": entry.metadata,
                    "similarity": similarity,
                    "timestamp": entry.timestamp
                })
        
        # Sort by similarity and limit
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]
    
    def get_by_id(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Get entry by ID."""
        entry = self.entries.get(entry_id)
        if not entry:
            return None
        
        return {
            "id": entry.id,
            "content": entry.content,
            "metadata": entry.metadata,
            "timestamp": entry.timestamp
        }
    
    def update_metadata(self, entry_id: str, metadata_update: Dict[str, Any]) -> bool:
        """
        Update metadata for an entry.
        
        Args:
            entry_id: Entry ID
            metadata_update: Metadata fields to update
            
        Returns:
            True if updated, False if entry not found
        """
        entry = self.entries.get(entry_id)
        if not entry:
            return False
        
        entry.metadata.update(metadata_update)
        self._save_to_disk()
        return True
    
    def delete(self, entry_id: str) -> bool:
        """
        Delete an entry.
        
        Args:
            entry_id: Entry ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        if entry_id in self.entries:
            del self.entries[entry_id]
            self._save_to_disk()
            return True
        return False
    
    def get_by_metadata(self, metadata_filter: Dict[str, Any], 
                       limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get entries matching metadata criteria.
        
        Args:
            metadata_filter: Metadata criteria
            limit: Maximum results
            
        Returns:
            List of matching entries
        """
        results = []
        
        for entry in self.entries.values():
            if self._matches_filter(entry.metadata, metadata_filter):
                results.append({
                    "id": entry.id,
                    "content": entry.content,
                    "metadata": entry.metadata,
                    "timestamp": entry.timestamp
                })
                
                if len(results) >= limit:
                    break
        
        # Sort by timestamp (newest first)
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get project memory statistics."""
        if not self.entries:
            return {
                "total_entries": 0,
                "storage_size_mb": 0,
                "oldest_entry": None,
                "newest_entry": None,
                "sources": [],
                "types": []
            }
        
        timestamps = [entry.timestamp for entry in self.entries.values()]
        sources = set()
        types = set()
        
        for entry in self.entries.values():
            sources.add(entry.metadata.get("source", "unknown"))
            types.add(entry.metadata.get("type", "text"))
        
        return {
            "total_entries": len(self.entries),
            "storage_size_mb": self._estimate_storage_size(),
            "oldest_entry": min(timestamps),
            "newest_entry": max(timestamps),
            "sources": list(sources),
            "types": list(types),
            "workspace": self.workspace,
            "project": self.project_name
        }
    
    def clear(self) -> None:
        """Clear all entries from project memory."""
        self.entries.clear()
        self._save_to_disk()
    
    def _chunk_content(self, content: str, chunk_size: int) -> List[str]:
        """Split content into chunks at natural boundaries."""
        if len(content) <= chunk_size:
            return [content]
        
        chunks = []
        current_chunk = ""
        
        # Split by paragraphs first
        paragraphs = content.split('\n\n')
        
        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph) + 2 <= chunk_size:
                if current_chunk:
                    current_chunk += '\n\n' + paragraph
                else:
                    current_chunk = paragraph
            else:
                # Save current chunk if not empty
                if current_chunk:
                    chunks.append(current_chunk)
                
                # Handle oversized paragraphs
                if len(paragraph) > chunk_size:
                    # Split by sentences
                    sentences = paragraph.split('. ')
                    current_chunk = ""
                    
                    for sentence in sentences:
                        if len(current_chunk) + len(sentence) + 2 <= chunk_size:
                            if current_chunk:
                                current_chunk += '. ' + sentence
                            else:
                                current_chunk = sentence
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = sentence
                else:
                    current_chunk = paragraph
        
        # Add final chunk
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _matches_filter(self, metadata: Dict[str, Any], 
                       filter_criteria: Dict[str, Any]) -> bool:
        """Check if metadata matches filter criteria."""
        for key, expected_value in filter_criteria.items():
            if key not in metadata:
                return False
            
            actual_value = metadata[key]
            
            # Handle different comparison types
            if isinstance(expected_value, str):
                if expected_value.lower() not in str(actual_value).lower():
                    return False
            else:
                if actual_value != expected_value:
                    return False
        
        return True
    
    def _load_from_disk(self) -> None:
        """Load entries from disk storage."""
        if not self.storage_file.exists():
            return
        
        try:
            with open(self.storage_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for entry_data in data.get("entries", []):
                entry = ProjectMemoryEntry.from_dict(entry_data)
                self.entries[entry.id] = entry
                
        except Exception as e:
            # Log error but continue with empty memory
            print(f"Warning: Failed to load project memory from {self.storage_file}: {e}")
    
    def _save_to_disk(self) -> None:
        """Save entries to disk storage."""
        try:
            data = {
                "project": self.project_name,
                "workspace": self.workspace,
                "last_updated": time.time(),
                "entries": [entry.to_dict() for entry in self.entries.values()]
            }
            
            # Write atomically
            temp_file = self.storage_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            temp_file.replace(self.storage_file)
            
        except Exception as e:
            print(f"Warning: Failed to save project memory to {self.storage_file}: {e}")
    
    def _estimate_storage_size(self) -> float:
        """Estimate storage size in MB."""
        try:
            if self.storage_file.exists():
                return self.storage_file.stat().st_size / (1024 * 1024)
        except Exception:
            pass
        
        # Fallback: estimate from memory
        total_size = 0
        for entry in self.entries.values():
            total_size += len(entry.content)
            total_size += len(json.dumps(entry.metadata))
        
        return total_size / (1024 * 1024)