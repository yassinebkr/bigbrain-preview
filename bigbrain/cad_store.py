"""Owned CAD revision storage and exact artifact reads for the Atelier."""

import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from .cad_contracts import CadDelivery, CadPreview, CadRevision, GeometryObservation
from .solidcraft import CadCapture, CadError

DOCUMENT_ID = re.compile(r'^[a-f0-9]{32}$')


def cad_root():
    return Path(os.environ.get('BIGBRAIN_CAD_DIR', Path.home() / '.bigbrain/cad'))


class CadStore:
    """Keep application-owned CAD artifacts separate from attached user sources."""

    def __init__(self, root=None):
        self.root = Path(root) if root is not None else cad_root()

    def directory(self, document_id):
        if not isinstance(document_id, str) or not DOCUMENT_ID.fullmatch(document_id):
            raise CadError('Invalid CAD document identity')
        path = self.root / document_id
        if path.is_symlink():
            raise CadError('CAD document root has been replaced')
        return path

    def create(self, session_id):
        if not isinstance(session_id, str) or not session_id:
            raise CadError('CAD work requires its conversation scope')
        document_id = uuid.uuid4().hex
        path = self.directory(document_id)
        path.mkdir(parents=True, mode=0o700)
        self._write(path / 'owner.json', {'session_id': session_id})
        return document_id

    @staticmethod
    def _write(path, value):
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                json.dump(value, stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def authorize(self, document_id, session_id):
        root = self.directory(document_id)
        try:
            owner = json.loads((root / 'owner.json').read_text())
        except (OSError, ValueError) as error:
            raise CadError('CAD document is unavailable') from error
        if not session_id or owner.get('session_id') != session_id:
            raise CadError('CAD document belongs to another conversation')
        return root

    def publish(self, session_id, capture: CadCapture, *, delivery=None, base_revision=0, title='Pièce CAO'):
        document = capture.document
        root = self.authorize(document.document_id, session_id)
        if document.project_id != document.document_id:
            raise CadError('CAD owned project/document identity mismatch')
        if capture.geometry.source_sha256 != document.native.sha256:
            raise CadError('CAD measurement belongs to another revision')
        if capture.preview and not capture.preview.is_current(document):
            raise CadError('CAD capture preview belongs to another revision')
        if delivery is not None:
            delivery = CadDelivery.model_validate(delivery)
            if delivery.document != document or delivery.geometry != capture.geometry:
                raise CadError('CAD delivery differs from its captured observations')
        record = {'title': str(title)[:160], 'document': document.model_dump(mode='json'),
                  'geometry': capture.geometry.model_dump(mode='json'),
                  'preview': capture.preview.model_dump(mode='json') if capture.preview else None,
                  'preview_error': capture.preview_error,
                  'delivery': delivery.model_dump(mode='json') if delivery else None}
        # Each immutable capture remains readable after later edits or restarts.
        lock = root / '.publication'
        try:
            lock.mkdir()
        except FileExistsError as error:
            raise CadError('CAD publication is busy or requires interrupted-state inspection') from error
        try:
            current = self.view(document.document_id, session_id)['document']['revision'] if (root / 'current.json').exists() else 0
            if current != base_revision or document.revision <= current:
                raise CadError('CAD base revision changed before publication')
            record_path = root / f'revision-{document.revision}' / 'capture.json'
            with record_path.open('x', encoding='utf-8') as stream:
                json.dump(record, stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            self._write(root / 'current.json', {'revision': document.revision})
        finally:
            lock.rmdir()
        return self.view(document.document_id, session_id, document.revision)

    def view(self, document_id, session_id, revision=None):
        root = self.authorize(document_id, session_id)
        try:
            if revision is None:
                revision = json.loads((root / 'current.json').read_text())['revision']
            if type(revision) is not int or revision < 1:
                raise CadError('Invalid CAD revision')
            data = json.loads((root / f'revision-{revision}' / 'capture.json').read_text())
            document = CadRevision.model_validate(data['document'])
            geometry = GeometryObservation.model_validate(data['geometry'])
            preview = CadPreview.model_validate(data['preview']) if data.get('preview') else None
            delivery = CadDelivery.model_validate(data['delivery']) if data.get('delivery') else None
        except (OSError, ValueError, KeyError) as error:
            raise CadError('CAD revision is unavailable or invalid') from error
        if (document.document_id != document_id or document.revision != revision
                or document.native.sha256 != geometry.source_sha256):
            raise CadError('CAD capture revision mismatch')
        if delivery and (delivery.document != document or delivery.geometry != geometry):
            raise CadError('CAD delivery evidence differs from its stored capture')
        return {'title': data.get('title', 'Pièce CAO'),
                'document': document.model_dump(mode='json'), 'geometry': geometry.model_dump(mode='json'),
                'preview': preview.model_dump(mode='json') if preview else None,
                'preview_state': 'current' if preview and preview.is_current(document)
                    else 'stale' if preview else 'failed' if data.get('preview_error') else 'absent',
                'preview_error': data.get('preview_error'),
                'checks': [check.model_dump(mode='json') for check in delivery.checks] if delivery else []}

    def list(self, session_id):
        """Return bounded identity pointers; callers request geometry separately."""
        if not session_id:
            raise CadError('CAD memory requires its conversation scope')
        items = []
        if not self.root.is_dir():
            return {'status': 'empty', 'documents': []}
        for index, path in enumerate(self.root.iterdir()):
            if index >= 1000:
                return {'status': 'limited', 'documents': items[:5], 'reason': 'CAD inventory scan limit reached'}
            if not DOCUMENT_ID.fullmatch(path.name) or path.is_symlink() or not path.is_dir():
                continue
            try:
                view = self.view(path.name, session_id)
                items.append({'document_id': path.name, 'revision': view['document']['revision'],
                              'title': view['title'], 'updated': (path / 'current.json').stat().st_mtime})
            except CadError:
                continue
        items.sort(key=lambda item: item['updated'], reverse=True)
        return {'status': 'ok' if items else 'empty', 'documents': items[:5]}

    def artifact(self, document_id, session_id, revision, kind):
        view = self.view(document_id, session_id, revision)
        document = CadRevision.model_validate(view['document'])
        if kind == 'native':
            artifact = document.native
        elif kind in {'step', 'stl'}:
            artifact = next((item for item in document.exports if item.format == kind), None)
        elif kind == 'preview':
            artifact = CadPreview.model_validate(view['preview']).image if view['preview'] else None
        else:
            artifact = None
        if artifact is None:
            raise CadError('Requested CAD artifact is unavailable')
        root = self.authorize(document_id, session_id)
        path = root / artifact.path
        if (path.resolve() != path.absolute() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve())
                or not path.is_file() or path.stat().st_nlink != 1
                or path.stat().st_size != artifact.size_bytes or artifact.size_bytes > 32_000_000):
            raise CadError('CAD artifact identity changed')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise CadError('CAD artifact bytes changed')
        return artifact, data
