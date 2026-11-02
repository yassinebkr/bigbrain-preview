"""Conversation-owned CAD continuation checkpoints tied to confirmed contracts."""

import hashlib
import json

from .cad_store import CadStore
from .solidcraft import CadError


class CadRunCheckpoint:
    def __init__(self, store, spec, session_id):
        self.store, self.spec, self.session_id = store, spec, session_id
        recorded = spec.metadata.get('cad', {})
        if recorded.get('session_id') != session_id:
            raise CadError('CAD continuation belongs to another conversation')
        self.digest = hashlib.sha256(json.dumps(spec.model_dump(mode='json'), sort_keys=True,
            separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        self.path = store.root / '.runs' / (self.digest + '.json')

    def load(self):
        if not self.path.exists():
            return None
        if self.path.is_symlink():
            raise CadError('CAD continuation identity changed')
        value = json.loads(self.path.read_text())
        if value.get('contract_sha256') != self.digest or value.get('session_id') != self.session_id:
            raise CadError('CAD continuation contract changed')
        self.store.authorize(value['document_id'], self.session_id)
        return value

    def save(self, document_id, recipe, *, kind):
        from .cad_stages import CadConstruction
        from .cad_planning import CadPlan
        model = CadConstruction if kind == 'construction' else CadPlan if kind == 'inspection' else None
        if model is None:
            raise CadError('Unknown CAD continuation stage')
        model.model_validate(recipe.model_dump())
        root = self.store.authorize(document_id, self.session_id)
        value = {'contract_sha256': self.digest, 'session_id': self.session_id,
            'document_id': document_id, 'contract_revision': {'design_id': self.spec.design_id, 'revision': self.spec.revision},
            'approval_plan_id': self.spec.metadata['approval']['plan_id'],
            'kind': kind, 'recipe': recipe.model_dump(mode='json')}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.store._write(self.path, value)
        self.store._write(root / 'continuation.json', {'contract_revision': value['contract_revision']})


def confirmed_continuation(document_id, session_id):
    """Resolve an owned document to its exact retained contract and recipe."""
    from .verification.evidence import default_repository
    store = CadStore()
    root = store.authorize(document_id, session_id)
    if (root / 'current.json').exists():
        raise CadError('CAD document already has a delivered revision')
    try:
        ref = json.loads((root / 'continuation.json').read_text())['contract_revision']
        spec = default_repository().load_spec(ref['design_id'], ref['revision'])
        if not spec or spec.metadata.get('approval', {}).get('decision') != 'approved':
            raise CadError('CAD continuation requires its confirmed contract')
        latest = default_repository().load_latest_spec(spec.design_id)
        if latest is None or latest.revision != spec.revision:
            raise CadError('CAD continuation contract was superseded')
        checkpoint = CadRunCheckpoint(store, spec, session_id)
        state = checkpoint.load()
        if not state or state['document_id'] != document_id:
            raise CadError('CAD continuation document changed')
        return spec, state
    except (OSError, KeyError, ValueError) as error:
        raise CadError('CAD continuation is unavailable') from error
