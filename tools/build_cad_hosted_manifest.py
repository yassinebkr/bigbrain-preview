"""Record an isolated SolidCraft hosted viewer and Worker distribution."""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    required = ('index.html', 'worker/bigbrain_worker_probe.js', 'worker/bigbrain_worker_probe_bg.wasm')
    if not all((args.build / name).is_file() for name in required):
        raise SystemExit('Hosted distribution is incomplete')
    if args.manifest.resolve().is_relative_to(args.build.resolve()):
        raise SystemExit('Keep the manifest outside the distribution')
    assets = {path.relative_to(args.build).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(args.build.rglob('*')) if path.is_file()}
    args.manifest.write_text(json.dumps({
        'source_tag': 'v0.28.0', 'source_commit': 'ee6b85605a32948bcbd9ae437a564cab826689ec',
        'patches': ['bigbrain-hosted-cache-v1'], 'assets': assets,
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
