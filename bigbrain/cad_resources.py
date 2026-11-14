"""Runtime-scoped CAD capacity and inference phase for explicit continuations."""

import os
from contextvars import ContextVar

MAX_EXECUTION_SECONDS = 3600


def proposal_execution_seconds():
    """Read the operator's window when creating a new confirmation contract."""
    value = int(os.environ.get('BIGBRAIN_CAD_EXECUTION_SECONDS', '600'))
    if not 1 <= value <= MAX_EXECUTION_SECONDS:
        raise ValueError(f'CAD execution window must be within 1..{MAX_EXECUTION_SECONDS} seconds')
    return value


command_capacity = ContextVar('cad_command_capacity', default=64)
inference_phase = ContextVar('cad_inference_phase', default='construction')


class CadBudgetExceeded(RuntimeError):
    """An authorized inference ceiling prevents another provider request."""


def check_commands(value):
    if len(value) > command_capacity.get():
        raise ValueError('CAD commands exceed the runtime-authorized capacity')
    return value


def check_cut_index(value):
    if value >= command_capacity.get():
        raise ValueError('CAD cut index exceeds the runtime-authorized capacity')
    return value


def authorized_capacity(root, contract, definition):
    """Check the exact resource record before widening validation in this task."""
    from .cad_controller import ContinuationAllowance
    from .cad_execution import CadExecutionStore, digest
    from .solidcraft import CadError
    store = CadExecutionStore(root, contract)
    path = store.directory / 'continuation.json'
    if not path.exists():
        return 64
    grant = ContinuationAllowance.model_validate(store._read(path))
    state = store._read(store.directory / 'controller.json')
    engine = store._read(store.engine_identity)
    failures = len(state['failures']) + state.get('inspection_repairs', 0)
    if (grant.contract_sha256 != contract or grant.document_id != store.root.name
            or grant.definition_sha256 != digest(definition.model_dump(mode='json'))
            or grant.engine_sha256 != engine['engine_sha256']
            or state.get('contract_sha256') != contract
            or grant.baseline_decisions > state['decisions'] or grant.baseline_failures > failures):
        raise CadError('CAD resource extension scope changed')
    identity = digest(grant.model_dump(mode='json', exclude_none=True))
    if identity != state.get('continuation_sha256') and (
            grant.previous_authorization_sha256 != state.get('continuation_sha256')
            or grant.baseline_decisions != state['decisions'] or grant.baseline_failures != failures):
        raise CadError('CAD resource extension chain changed')
    return grant.command_capacity or 64
