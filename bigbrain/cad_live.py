"""Durable presentation state for conversation-owned CAD construction."""

import json
import time

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
    execution = CadExecutionStore(root, value['contract_sha256'], value['engine_version'])
    chain = execution.active()
    if not chain:
        return None
    checkpoint = chain[-1]
    observations = execution.observations(checkpoint)
    # Keep the checkpoint distinct from the independently verified delivery.
    # Consumers use its hash when accepting asynchronous presentation results.
    return {'checkpoint_id': checkpoint.id, 'parent': checkpoint.parent,
            'contract_sha256': checkpoint.contract_sha256,
            'engine_version': checkpoint.engine_version,
            'engine_sha256': checkpoint.engine_sha256,
            'native': checkpoint.native.model_dump(mode='json'),
            'accepted_steps': len(chain), 'design': observations['design']}


def retain_progress(store, document_id, session_id, context, progress):
    """Commit the presentation identity before broadcasting its progress event."""
    root = store.authorize(document_id, session_id)
    value = {'schema_version': '1.0', 'session_id': session_id,
             'document_id': document_id, 'updated_at': time.time(),
             'context': context, 'progress': progress}
    store._write(root / 'working-state.json', value)
    return value
