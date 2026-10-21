"""One transport envelope; consumers operate on its application data."""
def result_data(payload):
    if not isinstance(payload, dict):
        raise ValueError('Worker result must be an object')
    if isinstance(payload.get('success'), bool) and isinstance(payload.get('data'), dict):
        data = dict(payload['data'])
        data['success'] = payload['success'] and data.get('success', True)
        if not data['success']:
            data['error'] = payload.get('error') or data.get('error') or 'Worker failed'
        return data
    return dict(payload)  # Legacy participants already publish application data.
