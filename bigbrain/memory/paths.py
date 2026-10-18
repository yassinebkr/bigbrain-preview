"""One persistent-memory root for modern and compatibility stores."""

import os
from pathlib import Path


def legacy_storage_dir(kind: str, explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    root = os.environ.get('BIGBRAIN_MEMORY_DIR')
    return Path(root) / 'legacy' / kind if root else Path('memory') / kind
