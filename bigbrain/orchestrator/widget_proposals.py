"""Closed presentation-only contract. No geometry, actions, paths or content."""

WIDGET_KINDS = frozenset({'files', 'verification', 'console', 'preview'})


def validate_widget_proposal(value):
    if (not isinstance(value, dict) or set(value) != {'version', 'revision', 'widgets'}
            or type(value['version']) is not int or value['version'] != 1
            or type(value['revision']) is not int or not 1 <= value['revision'] <= 9007199254740991):
        raise ValueError('Invalid widget proposal envelope')
    widgets = value['widgets']
    if (not isinstance(widgets, list) or not 1 <= len(widgets) <= 2
            or any(not isinstance(item, str) or item not in WIDGET_KINDS for item in widgets)
            or len(set(widgets)) != len(widgets)):
        raise ValueError('workspace_widgets must contain 1-2 distinct catalog identifiers')
    return {'version': 1, 'revision': value['revision'], 'widgets': list(widgets)}


def widget_proposal(widgets):
    if widgets is None:
        return None
    return validate_widget_proposal({'version': 1, 'revision': 1, 'widgets': widgets})
