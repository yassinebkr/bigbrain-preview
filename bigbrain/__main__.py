"""BigBrain entry point — thin shim.

The system coordinator now lives in ``bigbrain.system`` and the CLI in
``bigbrain.cli`` (Phase 2 refactor). This module only keeps
``python -m bigbrain`` working and re-exports ``BigBrainSystem`` for
backwards compatibility.
"""

from .cli import main
from .system import AIOHTTP_AVAILABLE, TEXTUAL_AVAILABLE, BigBrainSystem

__all__ = ["BigBrainSystem", "main", "AIOHTTP_AVAILABLE", "TEXTUAL_AVAILABLE"]


if __name__ == "__main__":
    import asyncio
    import sys

    # Handle missing event loop on Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(main())
