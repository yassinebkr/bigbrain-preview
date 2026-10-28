"""Stable public delivery envelopes backed by immutable worker-result artifacts."""
from copy import deepcopy
import json
import hashlib


class DeliveryUnavailable(ValueError):
    """A public output cannot be loaded from its correlated immutable archive."""


def archive_delivery(data, *, task_id, subtask_id, session_id=None):
    """Preserve public output independently of compacted dependency context."""
    from ..research_acquisition import artifact
    body = json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
    reference = artifact(body, name='worker-result.json', media_type='application/json',
                         metadata={'task_id': task_id, 'subtask_id': subtask_id})
    envelope = deepcopy(data.get('delivery') or {})
    envelope.update(version=1, result_artifact=reference, task_id=task_id,
                    subtask_id=subtask_id, session_id=session_id)
    envelope.setdefault('status', data.get('execution_outcome') or data.get('research_status')
                        or data.get('delivery_status') or data.get('status')
                        or ('complete' if data.get('success') else 'failed'))
    message = data.get('public_message') or data.get('message')
    envelope['has_public_message'] = bool(isinstance(message, str) and message
                                          or envelope.get('public_message'))
    envelope.pop('public_message', None)
    for key in ('research_id', 'attempt_id'):
        if data.get(key):
            envelope.setdefault(key, data[key])
    return envelope


def public_delivery(data, *, session_id=None):
    """Read the stable envelope, retaining legacy worker compatibility."""
    envelope = data.get('delivery')
    if isinstance(envelope, dict) and envelope.get('version') == 1:
        if session_id is not None and envelope.get('session_id') != session_id:
            raise DeliveryUnavailable('Public delivery belongs to another conversation')
        message = envelope.get('public_message')
        if isinstance(message, str) and message:
            return message
        if envelope.get('has_public_message'):
            from ..research_acquisition import repository
            try:
                reference = envelope['result_artifact']
                body = repository().get_artifact(reference['sha256'])
                if body is None or hashlib.sha256(body).hexdigest() != reference['sha256']:
                    raise ValueError('Worker result archive is unavailable or changed')
                archived = json.loads(body)
                message = archived.get('public_message') or archived.get('message')
                if not message and isinstance(archived.get('delivery'), dict):
                    message = archived['delivery'].get('public_message')
                if not isinstance(message, str) or not message:
                    raise ValueError('Worker archive has no public output')
                return message
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise DeliveryUnavailable('Public output archive could not be loaded') from exc
    message = data.get('public_message')
    return message if isinstance(message, str) and message else None
