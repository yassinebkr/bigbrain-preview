"""Measure model packet sizes and the upper bound for static CAD context reuse."""

import argparse
import json
from pathlib import Path

STATIC_FIELDS = (
    'definition', 'execution_authorization', 'native_compatibility',
    'command_reference', 'available_commands', 'observation_coverage',
    'geometry_record_encoding',
)


def packet_size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())


def measure_packets(paths):
    snapshots = {}
    total = reusable = 0
    for path in paths:
        packet = json.loads(path.read_text(encoding='utf-8'))['packet']
        total += packet_size(packet)
        for field in STATIC_FIELDS:
            if field not in packet:
                continue
            value = packet[field]
            if field in snapshots and value == snapshots[field]:
                reusable += packet_size(value)
            snapshots[field] = value
    return {'packets': len(paths), 'packet_bytes': total,
            'repeated_static_value_bytes': reusable}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint_directory', type=Path)
    args = parser.parse_args()
    decisions = sorted(args.checkpoint_directory.glob('decision-*.json'),
                       key=lambda path: int(path.stem.rsplit('-', 1)[1]))
    if not decisions:
        parser.error('checkpoint directory must contain retained decision packets')
    print(json.dumps(measure_packets(decisions), indent=2))
