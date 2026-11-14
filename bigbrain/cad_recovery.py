"""Typed CAD recovery actions tied to retained checkpoints and failure evidence."""

from typing import Literal
import json
import hashlib
import re

from pydantic import BaseModel, ConfigDict, Field


class Recovery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['response_validation', 'geometry', 'interrupted', 'provider',
                  'budget', 'input', 'inspection', 'unknown']
    checkpoint: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    decision: int | None = Field(default=None, strict=True, ge=1)


def recovery_action(value):
    """Choose from recorded failure categories; diagnostic prose remains display-only."""
    try:
        recovery = Recovery.model_validate(value)
    except (ValueError, TypeError):
        recovery = Recovery(kind='unknown')
    actions = {
        'response_validation': ('replay_response', 'Retraiter la réponse conservée', False),
        'geometry': ('diagnose_geometry', 'Examiner l’échec géométrique', False),
        'interrupted': ('restore', 'Vérifier et restaurer l’état conservé', True),
        'provider': ('retry_provider', 'Réessayer l’appel interrompu', True),
        'budget': ('extend_budget', 'Examiner le budget de reprise', False),
        'input': ('complete_input', 'Compléter les informations', False),
        'inspection': ('inspect', 'Reprendre l’inspection', True),
        'unknown': ('diagnose', 'Examiner le blocage', False),
    }
    action, label, enabled = actions[recovery.kind]
    return {**recovery.model_dump(), 'action': action, 'label': label, 'enabled': enabled}


def retained_recovery(root):
    """Recheck the recovery checkpoint before offering a resumable action."""
    path = root / 'execution-checkpoints/controller.json'
    if not path.is_file() or path.is_symlink():
        return recovery_action(None)
    try:
        state = json.loads(path.read_text())
        head_record = json.loads((path.parent / 'head.json').read_text())
        head = head_record.get('active', [])
        action = recovery_action(state.get('recovery'))
        if action['checkpoint'] != (head[-1] if head else None):
            return recovery_action(None)
        if action['kind'] == 'geometry':
            # A recorded native diagnosis can authorize another proposal from
            # this exact checkpoint. The execution path still enforces the
            # confirmed contract, continuation allowance and mutation guards.
            for item in state.get('offline_diagnostics', []):
                name = item.get('name', '')
                if not re.fullmatch(r'offline-diagnosis-[a-z0-9-]+\.json', name):
                    continue
                diagnostic = path.parent / name
                if diagnostic.is_symlink() or not diagnostic.is_file() or diagnostic.stat().st_size > 1_000_000:
                    continue
                data = diagnostic.read_bytes()
                if hashlib.sha256(data).hexdigest() != item.get('sha256'):
                    continue
                value = json.loads(data)
                if (value.get('resume_ready') is True
                        and action['checkpoint'] is not None
                        and re.fullmatch(r'[a-f0-9]{64}', str(value.get('contract_sha256', '')))
                        and re.fullmatch(r'[a-f0-9]{64}', str(value.get('engine_sha256', '')))
                        and value.get('contract_sha256') == head_record.get('contract_sha256')
                        and value.get('checkpoint') == action['checkpoint']
                        and value.get('contract_sha256') == state.get('contract_sha256')
                        and value.get('engine_sha256') == head_record.get('engine_sha256')):
                    action.update(action='resume_diagnosed_geometry',
                                  label='Reprendre après diagnostic', enabled=True)
                    break
        if (root / '.cad-execution').exists():
            action['enabled'] = False
        return action
    except (OSError, ValueError, TypeError, AttributeError):
        return recovery_action(None)
