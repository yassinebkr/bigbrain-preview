"""Resolve Python execution intent from approval rather than source patterns."""


def interaction_mode(payload):
    """Execution intent comes from approval, never source imports or prose."""
    executable = payload.get('executable', True) is not False
    mode = payload.get('interaction_mode')
    if payload.get('deliverable_type', 'python') != 'python':
        raise ValueError('PythonBrain requires a Python deliverable; web apps belong to WebAppBrain')
    ref = payload.get('contract_revision')
    if ref:
        from ..verification.evidence import default_repository
        spec = default_repository().load_spec(ref['design_id'], ref['revision'])
        if not spec or spec.metadata.get('approval', {}).get('decision') != 'approved':
            raise ValueError('Python execution requires its approved contract revision')
        delivery = spec.metadata.get('delivery', {})
        if delivery.get('deliverable_type', 'python') != 'python':
            raise ValueError('Approved browser application belongs to WebAppBrain')
        approved_executable = delivery.get('executable', executable) is not False
        if 'executable' in payload and executable != approved_executable:
            raise ValueError('Python executable declaration differs from approved architecture')
        executable = approved_executable
        approved = spec.metadata.get('execution', {}).get('interaction_mode')
        # Old approvals did not declare a service capability. Keep their finite
        # CLI/library semantics rather than granting a persistent process.
        approved = approved or ('cli' if executable else 'library')
        if mode is not None and mode != approved:
            raise ValueError('Python interaction differs from the approved execution mode; approve again')
        mode = approved
    mode = mode or ('cli' if executable else 'library')
    if mode not in {'cli', 'library', 'service'}:
        raise ValueError(f'Unsupported Python interaction mode: {mode!r}')
    if executable != (mode != 'library'):
        raise ValueError('Python interaction and executable declaration disagree')
    return mode
