"""Bounded, session-scoped project references projected from the durable bus.

Projects come from the journal's authenticated producers. Personal facts are
append-only, sourced user statements interpreted by the front, never arbitrary
worker writes or executable instructions.
"""

import json
import os
import re
import sqlite3
import time
from pathlib import Path, PurePosixPath


MEMORY_TOOL_SCHEMA = {
    'name': 'bigbrain_memory',
    'description': 'Consult shared memory for facts or previous projects, or record an explicitly sourced user fact. Call this tool now when a lookup is needed; do not end with a promise to check later.',
    'parameters': {'type': 'object', 'required': ['tool', 'arguments'], 'additionalProperties': False,
        'properties': {
            'tool': {'type': 'string', 'enum': ['projects.list', 'projects.read', 'facts.search', 'facts.read', 'facts.write', 'memory.search']},
            'arguments': {'type': 'object', 'additionalProperties': False, 'properties': {
                'query': {'type': 'string'}, 'id': {'type': 'string'}, 'key': {'type': 'string'},
                'value': {'type': 'string'}, 'quote': {'type': 'string'},
                'source_message_id': {'type': 'string'}, 'expected_revision': {'type': 'integer'}}},
        }},
}


def _path(value):
    if not isinstance(value, str) or not value or len(value) > 500:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or '\\' in value:
        return None
    return path.as_posix()


class SharedMemory:
    def __init__(self, log_dir: Path, root: Path | None = None):
        self.log_dir = Path(log_dir)
        self.root = Path(root or os.environ.get('BIGBRAIN_MEMORY_DIR')
                         or Path.home() / '.bigbrain' / 'memory' / 'chroma')

    def _connect(self):
        self.root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.root / 'shared.sqlite3', timeout=10)
        connection.row_factory = sqlite3.Row
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS cursors(path TEXT PRIMARY KEY, offset INTEGER);
            CREATE TABLE IF NOT EXISTS projects(
                session TEXT, id TEXT, path TEXT, status TEXT, entry_point TEXT,
                verdict TEXT, evidence TEXT, error TEXT, updated REAL, source TEXT,
                PRIMARY KEY(session,id));
            CREATE TABLE IF NOT EXISTS files(
                session TEXT, id TEXT, path TEXT, PRIMARY KEY(session,id,path));
            CREATE INDEX IF NOT EXISTS projects_session ON projects(session,updated);
            CREATE TABLE IF NOT EXISTS fact_revisions(
                key TEXT, revision INTEGER, value TEXT, quote TEXT,
                source_session TEXT, source_message TEXT, source_time REAL,
                recorded REAL, PRIMARY KEY(key,revision));
        ''')
        return connection

    def facts_read(self, key):
        db = self._connect()
        try:
            rows = db.execute('SELECT * FROM fact_revisions WHERE key=? ORDER BY revision DESC LIMIT 3', (key,)).fetchall()
            return {'status': 'ok' if rows else 'empty', 'fact': dict(rows[0]) if rows else None,
                    'history': [dict(row) for row in rows[1:]]}
        finally:
            db.close()

    def facts_search(self, query):
        # Retrieval, not intent routing. Wildcards never become query syntax.
        pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        db = self._connect()
        try:
            rows = db.execute('''SELECT f.* FROM fact_revisions f
                WHERE f.revision=(SELECT MAX(r.revision) FROM fact_revisions r WHERE r.key=f.key)
                AND EXISTS(SELECT 1 FROM fact_revisions h WHERE h.key=f.key
                    AND (h.key LIKE ? ESCAPE '\\' OR h.value LIKE ? ESCAPE '\\' OR h.quote LIKE ? ESCAPE '\\'))
                ORDER BY f.recorded DESC, f.key LIMIT 5''', (pattern, pattern, pattern)).fetchall()
            return {'status': 'ok' if rows else 'empty', 'facts': [
                {k: row[k] for k in ('key', 'value', 'revision', 'source_time')} for row in rows]}
        finally:
            db.close()

    def facts_write(self, args, session_id):
        from ..web.sessions import SessionStore
        key, value, quote = args['key'], args['value'], args['quote']
        source_id, expected = args['source_message_id'], args['expected_revision']
        if not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,79}', key):
            raise ValueError('Invalid fact key')
        if not isinstance(value, str) or not 0 < len(value.strip()) <= 300:
            raise ValueError('Fact value must contain 1–300 characters')
        if not isinstance(quote, str) or not 0 < len(quote) <= 500 or value not in quote:
            raise ValueError('Value must be literal in a source quote of at most 500 characters')
        if type(expected) is not int or expected < 0 or not isinstance(source_id, str):
            raise ValueError('Invalid source or expected revision')
        session = SessionStore().get(session_id)
        source = next((m for m in (session or {}).get('messages', []) if m.get('id') == source_id), None)
        if not source or source.get('role') != 'user' or quote not in source.get('text', ''):
            raise ValueError('Source must be an exact quote from a user message in this conversation')
        timestamp = source['timestamp']
        db = self._connect()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                current = db.execute('SELECT * FROM fact_revisions WHERE key=? ORDER BY revision DESC LIMIT 1', (key,)).fetchone()
                if current and current['source_session'] == session_id and current['source_message'] == source_id and current['value'] == value:
                    return {'status': 'ok', 'key': key, 'revision': current['revision'], 'duplicate': True}
                revision = current['revision'] if current else 0
                if revision != expected or (current and timestamp < current['source_time']):
                    return {'status': 'conflict', 'key': key, 'current_revision': revision,
                            'reason': 'Read the latest revision; an older source cannot replace a newer statement'}
                db.execute('INSERT INTO fact_revisions VALUES(?,?,?,?,?,?,?,?)',
                           (key, revision + 1, value, quote, session_id, source_id, timestamp, time.time()))
            return {'status': 'ok', 'key': key, 'revision': revision + 1}
        finally:
            db.close()

    def _sync(self, connection):
        # Each complete line is consumed once, shared across readers/processes.
        # An incomplete final line is retried after the writer finishes it.
        for path in sorted(self.log_dir.glob('bus-*.jsonl')):
            row = connection.execute('SELECT offset FROM cursors WHERE path=?', (str(path.resolve()),)).fetchone()
            offset = row['offset'] if row else 0
            if path.stat().st_size < offset:
                offset = 0
            with path.open('rb') as handle:
                handle.seek(offset)
                while True:
                    line = handle.readline()
                    if not line or not line.endswith(b'\n'):
                        break
                    offset = handle.tell()
                    try:
                        frame = json.loads(line)
                    except (ValueError, UnicodeError):
                        continue
                    self._record(connection, frame)
            connection.execute('INSERT OR REPLACE INTO cursors VALUES(?,?)', (str(path.resolve()), offset))

    def _record(self, db, frame):
        if not isinstance(frame, dict) or not isinstance(frame.get('payload'), dict):
            return
        data = frame['payload']
        event = data.get('event')
        session, task = data.get('session_id'), data.get('task_id') or data.get('plan_id')
        if not isinstance(session, str) or not isinstance(task, str) or not session or not task:
            return
        if event not in {'contracts.proposal', 'workspace.file_written', 'verification.run_recorded',
                         'task.complete', 'task.failed', 'task.cancelled'}:
            return
        # Only the orchestrator can declare the project's destination/terminal.
        source = frame.get('source', '')
        if not isinstance(source, str):
            return
        if event in {'contracts.proposal', 'task.complete', 'task.failed', 'task.cancelled'} and not source.startswith('orchestrator_'):
            return
        target = data.get('project_target')
        project_path = _path(data.get('project_path')) or (_path(target.get('path')) if isinstance(target, dict) else None)
        db.execute('INSERT OR IGNORE INTO projects(session,id,status,updated,source) VALUES(?,?,?,?,?)',
                   (session, task, 'unknown', 0, str(frame.get('id', ''))))
        if project_path:
            db.execute('UPDATE projects SET path=? WHERE session=? AND id=?', (project_path, session, task))
        file_path = _path(data.get('path')) if event == 'workspace.file_written' else None
        if file_path:
            db.execute('INSERT OR IGNORE INTO files VALUES(?,?,?)', (session, task, file_path))
        status = {'task.complete': 'done', 'task.failed': 'failed', 'task.cancelled': 'cancelled'}.get(event)
        if status:
            db.execute('UPDATE projects SET status=? WHERE session=? AND id=?', (status, session, task))
            error = data.get('error')
            if isinstance(error, str):
                db.execute('UPDATE projects SET error=? WHERE session=? AND id=?', (error[:1000], session, task))
        entry = _path(data.get('entry_point'))
        if entry:
            db.execute('UPDATE projects SET entry_point=? WHERE session=? AND id=?', (entry, session, task))
        if event == 'verification.run_recorded':
            verdict = data.get('verdict')
            if verdict in ('passed', 'failed', 'inconclusive'):
                db.execute('UPDATE projects SET verdict=?,evidence=? WHERE session=? AND id=?',
                           (verdict, str(data.get('run_id') or '')[:150], session, task))
        timestamp = frame.get('timestamp')
        if isinstance(timestamp, (int, float)):
            db.execute('UPDATE projects SET updated=MAX(updated,?),source=? WHERE session=? AND id=?',
                       (timestamp, str(frame.get('id', ''))[:150], session, task))

    def owns_partial_project(self, session_id: str, path: str) -> bool:
        """Require a scoped journal target AND a recorded write, not a guessed folder."""
        from ..web.sessions import SessionStore
        if not session_id or SessionStore().is_deleted(session_id) or _path(path) != path:
            return False
        db = self._connect()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                self._sync(db)
            return db.execute('''SELECT 1 FROM projects p WHERE p.session=? AND p.path=?
                AND EXISTS (SELECT 1 FROM files f WHERE f.session=p.session AND f.id=p.id)
                LIMIT 1''', (session_id, path)).fetchone() is not None
        finally:
            db.close()

    def projects(self, session_id: str, project_id: str | None = None):
        from ..web.sessions import SessionStore
        if not session_id:
            return {'status': 'unavailable', 'reason': 'No conversation scope'}
        if SessionStore().is_deleted(session_id):
            return {'status': 'unavailable', 'reason': 'Conversation deleted'}
        db = self._connect()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                self._sync(db)
            rows = db.execute('SELECT * FROM projects WHERE session=? AND path IS NOT NULL' + (' AND id=?' if project_id else '')
                              + ' ORDER BY updated DESC LIMIT 5',
                              (session_id, project_id) if project_id else (session_id,)).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                if not item['path']:
                    continue  # Never guess a root from similar names or navigation.
                item.pop('session')
                if project_id:
                    files = db.execute('SELECT path FROM files WHERE session=? AND id=? ORDER BY path LIMIT 21',
                                       (session_id, project_id)).fetchall()
                    item['files'] = [f['path'] for f in files[:20]]
                    item['files_truncated'] = len(files) > 20
                else:
                    item = {key: item[key] for key in ('id', 'path', 'status', 'updated')}
                items.append(item)
            return {'status': 'ok' if items else 'empty', 'projects': items}
        finally:
            db.close()


def memory_request(response: str):
    """Closed intermediate JSON contract; never parse instructions from prose."""
    text = response.strip()
    if text.startswith('```json') and text.endswith('```'):
        text = text[7:-3].strip()
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    if isinstance(value, dict) and 'memory' in value:
        return value['memory'] if set(value) == {'memory'} and isinstance(value['memory'], dict) else {}
    return None


def execute_memory(request, shared: SharedMemory, persistent, session_id: str | None, exclude=(), allow_write=False):
    """Runtime-owned scope/authority; closed reads and sourced fact revisions."""
    try:
        if not isinstance(request, dict) or set(request) != {'tool', 'arguments'}:
            raise ValueError('Expected tool and arguments only')
        tool, args = request['tool'], request['arguments']
        if not isinstance(args, dict):
            raise ValueError('Arguments must be an object')
        if tool == 'facts.read' and set(args) == {'key'} and isinstance(args['key'], str) and len(args['key']) <= 80:
            return shared.facts_read(args['key'])
        if tool == 'facts.search' and set(args) == {'query'} and isinstance(args['query'], str) and 0 < len(args['query'].strip()) <= 80:
            return shared.facts_search(args['query'])
        if tool == 'facts.write' and allow_write and set(args) == {'key', 'value', 'quote', 'source_message_id', 'expected_revision'}:
            if not session_id:
                return {'status': 'unavailable', 'reason': 'No user conversation scope for writing'}
            return shared.facts_write(args, session_id)
        if tool == 'projects.list' and not args:
            return shared.projects(session_id)
        if tool == 'projects.read' and set(args) == {'id'} and isinstance(args['id'], str) and 0 < len(args['id']) <= 150:
            return shared.projects(session_id, args['id'])
        if tool == 'memory.search' and set(args) == {'query'} and isinstance(args['query'], str) and 0 < len(args['query'].strip()) <= 500:
            if os.environ.get('BIGBRAIN_RECALL', '1') == '0':
                return {'status': 'disabled', 'items': []}
            result = persistent.query_report(args['query'], limit=24)
            seen = {text.strip().casefold() for text in exclude}
            selected = []
            for item in result.get('items', []):
                text = str(item.get('content', '')).strip()
                role = (item.get('metadata') or {}).get('role')
                if role in ('user', 'assistant') and text.startswith(f'{role}: '):
                    text = text[len(role) + 2:]
                key = text.casefold()
                if not key or key in seen:
                    continue
                seen.add(key)
                selected.append(item)
                if len(selected) == 4:
                    break
            result['items'] = [{
                'id': item.get('id'), 'content': str(item.get('content', ''))[:700],
                'source': {key: (item.get('metadata') or {}).get(key)
                           for key in ('role', 'session_id', 'message_id', 'timestamp', 'brain', 'memory_type')},
            } for item in selected]
            if result['status'] == 'ok' and not selected:
                result['status'] = 'empty'
            return result
        raise ValueError('Unknown tool or invalid arguments')
    except ValueError as exc:
        return {'status': 'invalid', 'reason': str(exc)}
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Shared memory consultation failed')
        return {'status': 'error', 'reason': 'Memory consultation failed; do not conclude the information was never supplied'}
