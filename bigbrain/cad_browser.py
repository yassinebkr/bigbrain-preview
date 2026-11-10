"""Durable browser CAD command journal and revision ownership.

SQLite commits the operation receipt and native checkpoint together. Browser
execution may repeat from a restored checkpoint; an accepted revision advances
once. Client generations fence responses from replaced browsing contexts.
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from uuid import uuid4

from .cad_workflow import allowed_cad_command


class BridgeConflict(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


class BrowserCadBridge:
    def __init__(self, root):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'browser.sqlite3'
        with self.transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS document (
                    id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER,
                    hash TEXT, native BLOB, owner TEXT, generation TEXT,
                    pause INTEGER, capabilities TEXT);
                CREATE TABLE IF NOT EXISTS operation (
                    id TEXT PRIMARY KEY, request TEXT, status TEXT,
                    result TEXT, revision INTEGER);
                CREATE TABLE IF NOT EXISTS checkpoint (
                    revision INTEGER PRIMARY KEY, hash TEXT, native BLOB);
            ''')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def row(db):
        row = db.execute('SELECT * FROM document WHERE id=1').fetchone()
        if row is None:
            raise BridgeConflict('Browser document is uninitialized')
        return row

    @staticmethod
    def check(row, revision, sha256, generation=None):
        if row['revision'] != revision or row['hash'] != sha256:
            raise BridgeConflict('Browser CAD checkpoint changed')
        if generation is not None and row['generation'] != generation:
            raise BridgeConflict('Browser CAD connection replaced')

    def initialize(self, native):
        if not native or len(native) > 96 * 1024**2:
            raise ValueError('Native checkpoint size outside browser bridge limits')
        with self.transaction() as db:
            db.execute('INSERT OR IGNORE INTO document VALUES (1,0,?,?,?,NULL,0,?)',
                       (digest(native), native, 'user', '{}'))
            row = self.row(db)
            db.execute('INSERT OR IGNORE INTO checkpoint VALUES (?,?,?)',
                       (row['revision'], row['hash'], row['native']))

    def connect(self, capabilities):
        if not isinstance(capabilities, dict) or not capabilities.get('build'):
            raise ValueError('Browser build identity required')
        generation = uuid4().hex
        with self.transaction() as db:
            row = self.row(db)
            previous = json.loads(row['capabilities'])
            if previous and previous != capabilities:
                raise BridgeConflict('Browser capabilities changed; qualify the new build')
            # A reconnect always restores the accepted bytes before another claim.
            db.execute("UPDATE operation SET status='queued' WHERE status='running'")
            if row['pause']:
                db.execute("UPDATE operation SET status='cancelled' WHERE status='queued'")
                db.execute("UPDATE document SET owner='user',pause=0 WHERE id=1")
            db.execute('UPDATE document SET generation=?,capabilities=? WHERE id=1',
                       (generation, json.dumps(capabilities, sort_keys=True)))
        return self.state()

    def state(self):
        with self.transaction() as db:
            row = dict(self.row(db))
            del row['native']
            row.pop('id')
            row['capabilities'] = json.loads(row['capabilities'])
            row['operations'] = [dict(r) for r in db.execute(
                'SELECT id,status,revision FROM operation ORDER BY rowid')]
            return row

    def checkpoint(self, revision=None):
        with self.transaction() as db:
            if revision is None:
                return bytes(self.row(db)['native'])
            row = db.execute('SELECT native FROM checkpoint WHERE revision=?', (revision,)).fetchone()
            if row is None:
                raise BridgeConflict('Checkpoint revision unavailable')
            return bytes(row['native'])

    def enqueue(self, operation_id, revision, sha256, command, params):
        if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 128:
            raise ValueError('Operation identity required')
        if not allowed_cad_command(command) or not isinstance(params, dict):
            raise ValueError('Command outside browser construction scope')
        request = json.dumps({'baseRevision': revision, 'baseHash': sha256,
                              'command': command, 'params': params}, sort_keys=True, allow_nan=False)
        with self.transaction() as db:
            existing = db.execute('SELECT * FROM operation WHERE id=?', (operation_id,)).fetchone()
            if existing:
                if existing['request'] != request:
                    raise BridgeConflict('Operation identity reused with different content')
                return dict(existing)
            row = self.row(db)
            self.check(row, revision, sha256)
            capabilities = json.loads(row['capabilities'])
            if 'commands' in capabilities and command not in capabilities['commands']:
                raise BridgeConflict('Command absent from the connected browser build')
            if any(item.get('id') == command and item.get('planned') for item in capabilities.get('catalog', [])):
                raise BridgeConflict('Browser command is advertised as planned')
            if row['owner'] != 'agent' or row['pause']:
                raise BridgeConflict('Agent editing is paused')
            if db.execute("SELECT 1 FROM operation WHERE status IN ('queued','running')").fetchone():
                raise BridgeConflict('A browser operation is already pending')
            db.execute("INSERT INTO operation VALUES (?,?,'queued',NULL,NULL)", (operation_id, request))
        return {'id': operation_id, 'status': 'queued'}

    def claim(self, generation):
        with self.transaction() as db:
            row = self.row(db)
            if row['generation'] != generation:
                raise BridgeConflict('Browser CAD connection replaced')
            op = db.execute("SELECT * FROM operation WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if row['owner'] != 'agent' or row['pause'] or op is None:
                return None
            request = json.loads(op['request'])
            self.check(row, request['baseRevision'], request['baseHash'])
            db.execute("UPDATE operation SET status='running' WHERE id=?", (op['id'],))
            return {'id': op['id'], 'generation': generation, **request}

    def accept(self, operation_id, generation, native, result):
        if not native or len(native) > 96 * 1024**2:
            raise ValueError('Invalid browser checkpoint size')
        result = json.dumps({'checkpointHash': digest(native), 'result': result}, sort_keys=True, allow_nan=False)
        with self.transaction() as db:
            row = self.row(db)
            if row['generation'] != generation:
                raise BridgeConflict('Browser CAD connection replaced')
            op = db.execute('SELECT * FROM operation WHERE id=?', (operation_id,)).fetchone()
            if op is None:
                raise BridgeConflict('Unknown browser operation')
            if op['status'] == 'accepted':
                if op['result'] != result:
                    raise BridgeConflict('Accepted operation result changed')
                return {'id': operation_id, 'revision': op['revision'], 'status': 'accepted'}
            request = json.loads(op['request'])
            self.check(row, request['baseRevision'], request['baseHash'])
            if op['status'] != 'running' or row['owner'] != 'agent':
                raise BridgeConflict('Operation has no active editing lease')
            revision = row['revision'] + 1
            db.execute("UPDATE operation SET status='accepted',result=?,revision=? WHERE id=?",
                       (result, revision, operation_id))
            db.execute('UPDATE document SET revision=?,hash=?,native=?,owner=?,pause=0 WHERE id=1',
                       (revision, digest(native), native, 'user' if row['pause'] else 'agent'))
            db.execute('INSERT INTO checkpoint VALUES (?,?,?)', (revision, digest(native), native))
            return {'id': operation_id, 'revision': revision, 'status': 'accepted'}

    def result(self, operation_id):
        with self.transaction() as db:
            op = db.execute('SELECT * FROM operation WHERE id=?', (operation_id,)).fetchone()
            if op is None:
                raise BridgeConflict('Unknown browser operation')
            return {'operationId': operation_id, 'status': op['status'], 'revision': op['revision'],
                    'request': json.loads(op['request']),
                    'observation': json.loads(op['result']) if op['result'] else None}

    def fail(self, operation_id, generation, error):
        with self.transaction() as db:
            row = self.row(db)
            if row['generation'] != generation:
                raise BridgeConflict('Browser CAD connection replaced')
            op = db.execute('SELECT status FROM operation WHERE id=?', (operation_id,)).fetchone()
            if op is None or op['status'] != 'running':
                raise BridgeConflict('Operation has no active editing lease')
            db.execute("UPDATE operation SET status='failed',result=? WHERE id=? AND status='running'",
                       (json.dumps({'error': str(error)[:2000]}), operation_id))
            db.execute("UPDATE document SET owner='user',pause=0 WHERE id=1")
        return self.state()

    def control(self, action, revision, sha256):
        with self.transaction() as db:
            row = self.row(db)
            self.check(row, revision, sha256)
            running = db.execute("SELECT 1 FROM operation WHERE status='running'").fetchone()
            if action == 'resume':
                if row['pause'] or running:
                    raise BridgeConflict('Wait for the current operation to settle')
                db.execute("UPDATE document SET owner='agent',pause=0 WHERE id=1")
            elif action == 'pause':
                db.execute('UPDATE document SET pause=?,owner=? WHERE id=1',
                           (int(bool(running)), 'agent' if running else 'user'))
                if not running:
                    db.execute("UPDATE operation SET status='cancelled' WHERE status='queued'")
            elif action == 'stop':
                # Revoking the generation fences an in-flight completion. The client
                # reloads the accepted native checkpoint to discard partial geometry.
                db.execute("UPDATE document SET owner='user',pause=0,generation=NULL WHERE id=1")
                db.execute("UPDATE operation SET status='cancelled' WHERE status IN ('queued','running')")
            else:
                raise ValueError('Unknown browser ownership action')
        return self.state()

    def save_manual(self, generation, revision, sha256, native):
        if not native or len(native) > 96 * 1024**2:
            raise ValueError('Invalid manual checkpoint size')
        with self.transaction() as db:
            row = self.row(db)
            self.check(row, revision, sha256, generation)
            if row['owner'] != 'user' or row['pause']:
                raise BridgeConflict('Pause agent editing before changing the document')
            db.execute('UPDATE document SET revision=revision+1,hash=?,native=? WHERE id=1',
                       (digest(native), native))
            db.execute('INSERT INTO checkpoint VALUES (?,?,?)', (revision + 1, digest(native), native))
            db.execute("UPDATE operation SET status='cancelled' WHERE status='queued'")
        return self.state()
