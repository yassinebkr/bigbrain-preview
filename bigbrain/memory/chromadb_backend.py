"""ChromaDB backend for BigBrain persistent memory.

Uses a single collection with scope/workspace metadata for unified
Tier 2+3 storage. Falls back gracefully when chromadb is not installed.
"""

import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Default storage path
DEFAULT_STORAGE = Path.home() / ".bigbrain" / "memory" / "chroma"
COLLECTION_NAME = "bigbrain_memory"

# Check if chromadb is available
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


class ChromaMemoryBackend:
    """
    Unified persistent memory backend using ChromaDB.

    Single collection with `scope` metadata field:
    - scope="workspace" + workspace="X" → project memory (Tier 2)
    - scope="global" → long-term memory (Tier 3)

    Falls back to in-memory dict when ChromaDB is not installed.
    """

    def __init__(self, storage_dir: Path = None):
        # Env override is read LAZILY (not at import) so tests and
        # subprocesses can redirect storage per-process.
        default = Path(os.environ.get("BIGBRAIN_MEMORY_DIR",
                                      str(DEFAULT_STORAGE)))
        self.storage_dir = storage_dir or default
        self._fallback_entries: List[Dict[str, Any]] = []
        self._collection = None
        self._client = None

        if CHROMADB_AVAILABLE:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            try:
                self._client = chromadb.PersistentClient(
                    path=str(self.storage_dir),
                    settings=Settings(anonymized_telemetry=False),
                )
                self._collection = self._client.get_or_create_collection(
                    name=COLLECTION_NAME,
                    metadata={"description": "BigBrain unified memory"},
                )
            except Exception as e:
                print(f"⚠️  ChromaDB init failed ({e}), using in-memory fallback")
                self._collection = None

    @property
    def is_persistent(self) -> bool:
        return self._collection is not None

    def store(
        self,
        content: str,
        scope: str = "workspace",
        workspace: str = "",
        brain: str = "",
        memory_type: str = "fact",
        tags: str = "",
        task_id: str = "",
        extra_metadata: Dict[str, Any] = None,
    ) -> str:
        """Store content in memory. Returns entry ID."""
        entry_id = str(uuid.uuid4())
        metadata = {
            "scope": scope,
            "workspace": workspace,
            "brain": brain,
            "memory_type": memory_type,
            "timestamp": time.time(),
            "task_id": task_id,
            "tags": tags,
        }
        if extra_metadata:
            for k, v in extra_metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    metadata[k] = v

        if self._collection is not None:
            self._collection.add(
                ids=[entry_id],
                documents=[content],
                metadatas=[metadata],
            )
        else:
            self._fallback_entries.append({
                "id": entry_id,
                "content": content,
                "metadata": metadata,
            })

        return entry_id

    def query(
        self,
        query_text: str,
        limit: int = 5,
        scope: str = None,
        workspace: str = None,
        memory_type: str = None,
        brain: str = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search. Returns list of {id, content, metadata, distance}."""
        where_filter = self._build_where(scope, workspace, memory_type, brain)

        if self._collection is not None:
            try:
                kwargs = {"query_texts": [query_text], "n_results": limit}
                if where_filter:
                    kwargs["where"] = where_filter
                results = self._collection.query(**kwargs)
                return self._unpack_chroma_results(results)
            except Exception:
                return []
        else:
            return self._fallback_search(query_text, limit, where_filter)

    def get_by_id(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific entry by ID."""
        if self._collection is not None:
            try:
                result = self._collection.get(ids=[entry_id])
                if result and result["ids"]:
                    return {
                        "id": result["ids"][0],
                        "content": result["documents"][0],
                        "metadata": result["metadatas"][0],
                    }
            except Exception:
                pass
            return None
        else:
            for entry in self._fallback_entries:
                if entry["id"] == entry_id:
                    return entry
            return None

    def delete(
        self,
        entry_id: str = None,
        scope: str = None,
        workspace: str = None,
    ) -> int:
        """Delete entries by ID or filter. Returns count deleted."""
        if self._collection is not None:
            try:
                if entry_id:
                    self._collection.delete(ids=[entry_id])
                    return 1
                elif workspace or scope:
                    where_filter = self._build_where(scope, workspace)
                    if where_filter:
                        # ChromaDB delete with where
                        self._collection.delete(where=where_filter)
                        return -1  # ChromaDB doesn't return count
                return 0
            except Exception:
                return 0
        else:
            before = len(self._fallback_entries)
            if entry_id:
                self._fallback_entries = [
                    e for e in self._fallback_entries if e["id"] != entry_id
                ]
            elif workspace:
                self._fallback_entries = [
                    e for e in self._fallback_entries
                    if e["metadata"].get("workspace") != workspace
                    or e["metadata"].get("scope") == "global"
                ]
            return before - len(self._fallback_entries)

    def count(self, scope: str = None, workspace: str = None) -> int:
        """Count entries matching filter."""
        if self._collection is not None:
            try:
                where = self._build_where(scope, workspace)
                if where:
                    result = self._collection.get(where=where, limit=1)
                    # ChromaDB get returns all matches; use count
                    return self._collection.count()  # Approximate
                return self._collection.count()
            except Exception:
                return 0
        else:
            if not scope and not workspace:
                return len(self._fallback_entries)
            return sum(
                1 for e in self._fallback_entries
                if (not scope or e["metadata"].get("scope") == scope)
                and (not workspace or e["metadata"].get("workspace") == workspace)
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        total = self.count()
        return {
            "backend": "chromadb" if self.is_persistent else "in-memory",
            "total_entries": total,
            "storage_path": str(self.storage_dir) if self.is_persistent else "N/A",
            "collection": COLLECTION_NAME if self.is_persistent else "N/A",
        }

    # --- User preferences (key-value, stored as global scope) ---

    def store_preference(self, key: str, value: Any) -> None:
        """Store a user preference (global scope)."""
        # Check if preference already exists
        existing = self.query(
            f"preference:{key}",
            limit=1,
            scope="global",
            memory_type="preference",
        )
        for entry in existing:
            if entry.get("metadata", {}).get("pref_key") == key:
                self.delete(entry_id=entry["id"])

        self.store(
            content=f"preference:{key}={value}",
            scope="global",
            memory_type="preference",
            extra_metadata={"pref_key": key, "pref_value": str(value)},
        )

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference."""
        results = self.query(
            f"preference:{key}",
            limit=5,
            scope="global",
            memory_type="preference",
        )
        for r in results:
            meta = r.get("metadata", {})
            if meta.get("pref_key") == key:
                return meta.get("pref_value", default)
        return default

    # --- Internal helpers ---

    @staticmethod
    def _build_where(
        scope: str = None,
        workspace: str = None,
        memory_type: str = None,
        brain: str = None,
    ) -> Optional[Dict]:
        """Build a ChromaDB where filter."""
        conditions = []
        if scope:
            conditions.append({"scope": scope})
        if workspace:
            conditions.append({"workspace": workspace})
        if memory_type:
            conditions.append({"memory_type": memory_type})
        if brain:
            conditions.append({"brain": brain})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    @staticmethod
    def _unpack_chroma_results(results: dict) -> List[Dict[str, Any]]:
        """Convert ChromaDB query results to flat list."""
        entries = []
        if not results or not results.get("ids"):
            return entries
        ids = results["ids"][0]
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results.get("distances", [[]])[0]

        for i, entry_id in enumerate(ids):
            entries.append({
                "id": entry_id,
                "content": docs[i],
                "metadata": metas[i],
                "distance": dists[i] if i < len(dists) else None,
            })
        return entries

    def _fallback_search(
        self, query: str, limit: int, where: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Simple keyword search for in-memory fallback."""
        query_words = set(query.lower().split())
        scored = []

        for entry in self._fallback_entries:
            # Apply where filter
            if where and not self._matches_where(entry["metadata"], where):
                continue

            content_words = set(entry["content"].lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0 or not query_words:
                scored.append((overlap, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {**e, "distance": 1.0 - (s / max(len(query_words), 1))}
            for s, e in scored[:limit]
        ]

    @staticmethod
    def _matches_where(metadata: Dict, where: Dict) -> bool:
        """Check if metadata matches a where filter."""
        if "$and" in where:
            return all(
                ChromaMemoryBackend._matches_where(metadata, cond)
                for cond in where["$and"]
            )
        for key, value in where.items():
            if metadata.get(key) != value:
                return False
        return True
