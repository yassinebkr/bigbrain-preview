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
        if self.is_deleted(session_id):
            raise SessionError('Cette conversation a été supprimée.')
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
        if self.is_deleted(session_id):
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
            if self.is_deleted(path.stem):
                continue
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

    def append_message(self, session_id: str, role: str, text: str,
                       attachments: list | None = None) -> Dict[str, Any]:
        session = self.ensure(session_id)
        messages: List[Dict[str, Any]] = session.setdefault("messages", [])
        messages.append({
            "id": f"m-{len(messages) + 1}-{uuid.uuid4().hex[:6]}",
            "role": role,
            "text": text,
            "timestamp": time.time(),
        })
        if role == 'user' and attachments:
            from .attachments import read_attachment
            import hashlib
            refs = []
            for item in attachments:
                path = read_attachment(item.get('id', ''))
                if path is None:
                    raise SessionError('Pièce jointe indisponible. Joins le fichier à nouveau.')
                refs.append({key: item[key] for key in ('id', 'name', 'type') if key in item}
                            | {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            messages[-1]['attachments'] = refs
            # The inventory survives the rolling message window. New uploads
            # retain separate identities; the model explicitly chooses sources.
            inventory = {item['id']: item for item in session.get('image_sources', [])}
            for item in refs:
                if item.get('type', '').startswith('image/'):
                    inventory[item['id']] = item
            session['image_sources'] = list(inventory.values())
        if len(messages) > MAX_MESSAGES:
            del messages[:len(messages) - MAX_MESSAGES]
        # Auto-title from the first user message.
        if role == "user" and not session.get('title_custom') and session.get("title") in (None, "", "New conversation"):
            session["title"] = (text.strip().splitlines() or ['New conversation'])[0][:60]
        session["updated_at"] = time.time()
        self._atomic_write(self._path(session["id"]), session)
        return session

    def set_cad_context(self, session_id: str, context: dict, *, expected_revision: int | None = None) -> dict:
        """Persist a conversation-owned design snapshot beside its transcript."""
        session = self.get(session_id)
        if session is None:
            raise SessionError('Conversation introuvable.')
        previous = session.get('cad_context') or {}
        if expected_revision is not None and previous.get('revision', 0) != expected_revision:
            raise SessionError('La définition de la pièce a évolué pendant cette réponse. Reprends les dernières précisions.')
        context = dict(context, revision=previous.get('revision', 0) + 1)
        session['cad_context'] = context
        self._atomic_write(self._path(session_id), session)
        return context

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if not path.is_file():
            return False
        deleted = self.root / '.deleted'
        deleted.mkdir(exist_ok=True)
        # Persist the tombstone first: delayed replies cannot recreate a chat,
        # including after restart or a crash between these two operations.
        self._atomic_write(deleted / path.name, {'id': session_id})
        path.unlink(missing_ok=True)
        return True

    def is_deleted(self, session_id: str) -> bool:
        return (self.root / '.deleted' / self._path(session_id).name).is_file()

    def deleted_ids(self) -> List[str]:
        return [p.stem for p in (self.root / '.deleted').glob('*.json')]

    def rename(self, session_id: str, title: str) -> Dict[str, Any]:
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
            raise SessionError('Le titre doit contenir entre 1 et 120 caractères.')
        session = self.get(session_id)
        if session is None:
            raise SessionError('Conversation introuvable.')
        session['title'] = ' '.join(title.split())
        session['title_custom'] = True
        self._atomic_write(self._path(session_id), session)
        return session
