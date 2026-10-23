"""Choose the next actor from recorded facts, never error-message keywords."""


def verification_disposition(failures):
    """Blocking uncertainty takes precedence over concurrent executable failures."""
    causes = set()
    for failure in failures:
        details = failure.get('details') or {}
        cause = details.get('cause')
        if failure.get('mandatory') is False or (failure.get('status') == 'not_applicable' and not cause):
            continue
        if details.get('requires_arbitration'):
            causes.add('contradiction' if cause == 'contradiction' else 'explicit_blocker')
        if cause in {'contradiction', 'environment_blocked', 'review_blocked'}:
            causes.add(cause or 'contradiction')
        elif cause:
            causes.add(cause)
        elif failure.get('status') == 'failed' and failure.get('stage') != 'semantics':
            causes.add('reproduced_defect')
        else:
            causes.add('unclassified')
    if causes - {'uninspected_evidence', 'missing_test', 'reproduced_defect', 'awaiting_checks'}:
        action = 'stop'
    elif 'uninspected_evidence' in causes:
        action = 'inspect'
    elif 'missing_test' in causes:
        action = 'extend_validation'
    elif 'reproduced_defect' in causes:
        action = 'repair'
    else:
        action = 'stop'
    return {'causes': sorted(causes), 'action': action}
