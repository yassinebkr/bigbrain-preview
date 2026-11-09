"""Native CAD inventory and evidence-separated qualification records."""

import hashlib
import json

from .cad_workflow import allowed_cad_command


def command_inventory(catalog):
    """Account for every installed command, including commands outside worker scope."""
    records = []
    seen = set()
    for entry in catalog:
        command = entry['id']
        if not isinstance(command, str) or command in seen:
            raise ValueError('Native CAD catalog requires unique string command IDs')
        seen.add(command)
        records.append({
            'id': command,
            # Namespace grouping is descriptive. Qualification requires case evidence.
            'namespace': command.split('.')[0],
            'native': entry,
            'worker_scope': 'allowed' if allowed_cad_command(command) else 'outside_current_scope',
            'description_status': 'pending',
            'description': None,
            'description_error': None,
            'qualification': {
                'isolated_execution': 'untested',
                'geometric_checks': 'untested',
                'parameter_edit': 'untested',
                'combined_execution': 'untested',
                'evidence': [],
            },
        })
    return sorted(records, key=lambda item: item['id'])


def attach_description(record, description):
    """Bind an installed description to the corresponding command identity."""
    if not isinstance(description, dict) or description.get('id') != record['id']:
        raise ValueError('Native CAD description identity mismatch')
    record['description'] = description
    record['description_status'] = 'available'


def catalog_digest(catalog):
    data = json.dumps(catalog, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(data.encode()).hexdigest()


def inventory_summary(records):
    """Keep native availability, worker scope and execution evidence independent."""
    namespaces = {}
    for record in records:
        row = namespaces.setdefault(record['namespace'], {'native': 0, 'allowed': 0, 'described': 0})
        row['native'] += 1
        row['allowed'] += record['worker_scope'] == 'allowed'
        row['described'] += record['description_status'] == 'available'
    return dict(sorted(namespaces.items()))
