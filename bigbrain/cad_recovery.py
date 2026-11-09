"""Typed CAD recovery actions tied to retained checkpoints and failure evidence."""

from typing import Literal
import json

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
        head = json.loads((path.parent / 'head.json').read_text()).get('active', [])
        action = recovery_action(state.get('recovery'))
        if action['checkpoint'] != (head[-1] if head else None):
            return recovery_action(None)
        if (root / '.cad-execution').exists():
            action['enabled'] = False
        return action
    except (OSError, ValueError, TypeError, AttributeError):
        return recovery_action(None)
