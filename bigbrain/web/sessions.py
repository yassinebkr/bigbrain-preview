"""Persistent chat sessions — one JSON file per conversation.

The chat history used to be a single in-memory buffer: one conversation
per process, lost on restart. Sessions are now first-class: created
explicitly (or lazily on first message), titled from the first user
message, persisted atomically under ``data/sessions/`` and listed for
the UI's history panel. ``BIGBRAIN_SESSIONS_DIR`` moves the root.

Message cap: a session keeps its last ``MAX_MESSAGES`` messages —
long-lived conversations stay bounded on disk.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_MESSAGES = 500
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")

_REPO_ROOT = Path(__file__).resolve().parents[2]


class SessionError(ValueError):
    """Raised for invalid session operations."""


class SessionStore:
    def __init__(self, root: str | os.PathLike[str] | None = None):
        self.root = Path(root or os.environ.get("BIGBRAIN_SESSIONS_DIR")
                         or (_REPO_ROOT / "data" / "sessions")).absolute()
        self.root.mkdir(parents=True, exist_ok=True)

    # ── helpers ─────────────────────────────────────────────────────

    def _path(self, session_id: str) -> Path:
        if not isinstance(session_id, str) or not _SAFE_ID.fullmatch(session_id):
            raise SessionError(f"invalid session id: {session_id!r}")
        return self.root / f"{session_id}.json"

    def _atomic_write(self, path: Path, data: Dict[str, Any]) -> None:
        content = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
                                             suffix=".tmp", delete=False) as handle:
                temporary = handle.name
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    # ── API ──────────────────────────────────────────────────────────

    def create(self, title: str = "New conversation") -> Dict[str, Any]:
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        session = {
            "id": session_id,
            "title": title or "New conversation",
            "created_at": time.time(),
            "updated_at": time.time(),
            "messages": [],
        }
        self._atomic_write(self._path(session_id), session)
        return session

    def ensure(self, session_id: Optional[str]) -> Dict[str, Any]:
        """Get a session, creating it if it does not exist yet.

        The web client may reference a session id it created earlier in
        another process; an unknown id is not an error — the conversation
        starts empty.
        """
        if not session_id:
            return self.create()
        path = self._path(session_id)
        if path.is_file():
            return self.get(session_id)  # type: ignore[return-value]
        session = {
            "id": session_id,
            "title": "New conversation",
            "created_at": time.time(),
            "updated_at": time.time(),
            "messages": [],
        }
        self._atomic_write(path, session)
        return session

    def get(self, session_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not session_id:
            return None
        path = self._path(session_id)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def list(self) -> List[Dict[str, Any]]:
        sessions: List[Dict[str, Any]] = []
        for path in self.root.glob("sess-*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            sessions.append({
                "id": data.get("id") or path.stem,
                "title": data.get("title") or "New conversation",
                "updated_at": data.get("updated_at") or 0,
                "message_count": len(data.get("messages") or []),
            })
        sessions.sort(key=lambda s: s["updated_at"], reverse=True)
        return sessions

    def append_message(self, session_id: str, role: str, text: str) -> Dict[str, Any]:
        session = self.ensure(session_id)
        messages: List[Dict[str, Any]] = session.setdefault("messages", [])
        messages.append({
            "id": f"m-{len(messages) + 1}-{uuid.uuid4().hex[:6]}",
            "role": role,
            "text": text,
            "timestamp": time.time(),
        })
        if len(messages) > MAX_MESSAGES:
            del messages[:len(messages) - MAX_MESSAGES]
        # Auto-title from the first user message.
        if role == "user" and session.get("title") in (None, "", "New conversation"):
            session["title"] = text.strip().splitlines()[0][:60] or "New conversation"
        session["updated_at"] = time.time()
        self._atomic_write(self._path(session["id"]), session)
        return session

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if not path.is_file():
            return False
        path.unlink()
        return True
