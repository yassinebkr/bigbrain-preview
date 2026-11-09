"""Capture installed CAD discovery coverage in a fresh machine-local evidence folder."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import platform
from pathlib import Path

from bigbrain.cad_capabilities import (
    attach_description, catalog_digest, command_inventory, inventory_summary,
)
from bigbrain.solidcraft import CadError, SolidCraftSession, solidcraft_executable


async def collect(output):
    # Exclusive output creation preserves previous inventories and qualification evidence.
    output.mkdir(parents=True, exist_ok=False)
    async with SolidCraftSession(output) as session:
        catalog = await session.tool('list_commands')
    records = command_inventory(catalog)
    # Short-lived read-only sessions respect the transport's observation allowance.
    for start in range(0, len(records), 96):
        async with SolidCraftSession(output) as session:
            for record in records[start:start + 96]:
                try:
                    description = await session.tool('describe_command', {'id': record['id']})
                    attach_description(record, description)
                except (CadError, ValueError) as error:
                    record['description_status'] = 'failed'
                    record['description_error'] = str(error)
        # Preserve completed batches if acquisition is interrupted later.
        snapshot = {
            'schema_version': '1.0', 'captured_at': datetime.now(timezone.utc).isoformat(),
            'platform': platform.system(), 'executable': str(solidcraft_executable()),
            'catalog_sha256': catalog_digest(catalog), 'commands': records,
        }
        (output / 'inventory.json').write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
    summary = inventory_summary(records)
    lines = ['# Installed CAD capability inventory', '',
             'Descriptions were read from the installed engine. Execution qualification is pending.', '',
             '| Namespace | Native commands | Worker-allowed | Descriptions read |',
             '| --- | ---: | ---: | ---: |']
    for name, counts in summary.items():
        lines.append(f"| {name} | {counts['native']} | {counts['allowed']} | {counts['described']} |")
    (output / 'SUMMARY.md').write_text('\n'.join(lines) + '\n')
    failures = [record['id'] for record in records if record['description_status'] != 'available']
    print(json.dumps({'output': str(output), 'native_commands': len(records),
                      'worker_allowed': sum(row['allowed'] for row in summary.values()),
                      'description_failures': failures}, indent=2))
    return bool(failures)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New local evidence directory')
    arguments = parser.parse_args()
    raise SystemExit(asyncio.run(collect(arguments.output.resolve())))
