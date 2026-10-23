"""Durable Codex bindings; stores identifiers/hashes/usage, never prompt sources."""
import asyncio
import hashlib
import json
from weakref import WeakValueDictionary

from ..web.sessions import SessionStore, SessionError

_locks = WeakValueDictionary()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class CodexSessions:
    def __init__(self):
        self.store = SessionStore()
        self.loaded = {}

    def binding(self, session, role, account):
        self.check(session)
        path = self.store.root / 'codex' / digest(session) / (digest([role, account]) + '.json')
        lock = _locks.setdefault((id(asyncio.get_running_loop()), str(path)), asyncio.Lock())
        return path, lock

    def check(self, session):
        self.store._path(session)  # same validated IDs as the visible history
        if self.store.is_deleted(session):
            raise SessionError('Cannot resume a deleted conversation')

    def load(self, path):
        if path in self.loaded:
            return self.loaded[path]
        state = json.loads(path.read_text()) if path.exists() else {'version': 1}
        if state.get('version') != 1:
            raise ValueError('Unsupported Codex binding version; history was not reset')
        self.loaded[path] = state
        return state

    def save(self, path, state, session):
        if self.store.is_deleted(session):
            return  # Stop/delete must not resurrect a binding from a late event
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.store._atomic_write(path, {k: v for k, v in state.items() if not k.startswith('_')})


def incremental_messages(messages, state):
    """Only append the unseen suffix, including rolling visible-history windows."""
    instructions = [m for m in messages if m.get('role') in {'system', 'developer'}]
    body = [m for m in messages if m.get('role') not in {'system', 'developer'}]
    hashes = [digest(m) for m in body]
    previous = state.get('message_hashes', [])
    matched = 0
    for start in range(len(previous)):
        count = 0
        for old, new in zip(previous[start:], hashes):
            if old != new:
                break
            count += 1
        matched = max(matched, count)
    changed_instructions = digest(instructions) != state.get('instructions_hash')
    delta = ([{'role': 'system', 'content': 'Current BigBrain instructions replace previous versions.'},
              *instructions] if changed_instructions else []) + body[matched:]
    if not delta:
        delta = [{'role': 'user', 'content': 'Continue the current request; the supplied input is unchanged.'}]
    return delta, {'message_hashes': hashes[-256:], 'instructions_hash': digest(instructions)}
