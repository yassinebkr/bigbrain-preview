"""Durable presentation state for conversation-owned CAD construction."""

import json
import time
import hashlib

from .cad_execution import CadExecutionStore
from .solidcraft import CadError


def working_checkpoint(store, document_id, session_id):
    """Resolve the accepted head through the validated native checkpoint chain."""
    root = store.authorize(document_id, session_id)
    head = root / 'execution-checkpoints' / 'head.json'
    if not head.exists():
        return None
    if head.is_symlink() or head.parent.is_symlink():
        raise CadError('CAD construction head identity changed')
    value = json.loads(head.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise CadError('CAD construction head is invalid')
    execution = CadExecutionStore(root, value.get('contract_sha256'), value.get('engine_version'))
    chain = execution.active()
    if not chain:
        return None
    checkpoint = chain[-1]
    observations = execution.observations(checkpoint)
    # The native document carries curves and constraints. Progress needs only
    # their inventory and sketch identities to configure the observation view.
    fields = {'id', 'name', 'status', 'dof', 'fully_constrained', 'plane'}
    inventory = {kind: [{key: value for key, value in item.items() if key in fields}
                        for item in items]
                 for kind, items in observations['design'].items()}
    # Keep the checkpoint distinct from the independently verified delivery.
    # Consumers use its hash when accepting asynchronous presentation results.
    return {'checkpoint_id': checkpoint.id, 'parent': checkpoint.parent,
            'contract_sha256': checkpoint.contract_sha256,
            'engine_version': checkpoint.engine_version,
            'engine_sha256': checkpoint.engine_sha256,
            'native': checkpoint.native.model_dump(mode='json'),
            'mesh': checkpoint.mesh.model_dump(mode='json') if checkpoint.mesh else None,
            'accepted_steps': len(chain), 'design': inventory}


def retain_progress(store, document_id, session_id, context, progress):
    """Commit the presentation identity before broadcasting its progress event."""
    root = store.authorize(document_id, session_id)
    if context.get('session_id') != session_id:
        raise CadError('CAD presentation conversation changed')
    runs = root / 'presentation-runs'
    runs.mkdir(exist_ok=True)
    if runs.is_symlink():
        raise CadError('CAD presentation directory identity changed')
    identity = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
    path = runs / (identity + '.json')
    if path.exists():
        if path.is_symlink():
            raise CadError('CAD presentation record identity changed')
        previous = json.loads(path.read_text(encoding='utf-8'))
        # A resumed execution can restart its local counter. Keep the public
        # sequence monotonic within the same conversation/run/step identity.
        progress['cad']['sequence'] = max(progress['cad']['sequence'],
                                         previous['progress']['cad']['sequence'] + 1)
    value = {'schema_version': '1.0', 'session_id': session_id,
             'document_id': document_id, 'updated_at': time.time(),
             'context': context, 'progress': progress}
    store._write(path, value)
    store._write(root / 'working-state.json', value)
    return value


def retained_activities(store, session_id):
    """Recover conversation activities from document-owned presentation records."""
    values = []
    if not store.root.exists():
        return values
    from .cad_store import DOCUMENT_ID
    for root in store.root.iterdir():
        if not DOCUMENT_ID.fullmatch(root.name) or root.is_symlink() or not root.is_dir():
            continue
        try:
            store.authorize(root.name, session_id)
        except CadError:
            continue
        folder = root / 'presentation-runs'
        if folder.is_symlink():
            raise CadError('CAD presentation directory identity changed')
        for path in folder.glob('*.json'):
            if path.is_symlink() or path.stat().st_size > 8_000_000:
                raise CadError('CAD presentation record identity changed')
            value = json.loads(path.read_text(encoding='utf-8'))
            if value.get('session_id') != session_id or value.get('document_id') != root.name:
                raise CadError('CAD presentation ownership changed')
            values.append(value)
    return sorted(values, key=lambda value: value['updated_at'])
