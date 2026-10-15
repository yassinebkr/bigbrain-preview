"""Voice Layer for BigBrain - STT, TTS, and Voice Management.

The real STT/TTS backends are OPTIONAL runtime dependencies (the ``voice``
extra: websockets, sounddevice, numpy). This package must import cleanly
without them — brains, the system and the tests import bigbrain.voice for
the manager and the mocks, and a missing optional dependency is reported
at USE time (create_voice_manager), never at import time.
"""

import importlib

from .stt import MockSTT
from .tts import MockTTS
from .voice_manager import VoiceManager, create_voice_manager

__all__ = [
    "MockSTT",
    "MockTTS",
    "VoiceManager",
    "create_voice_manager",
]


def _try_export(module_name: str, attr: str):
    """Import an optional real backend; None when its deps are missing."""
    try:
        value = getattr(
            importlib.import_module(f".{module_name}", __package__), attr)
    except ImportError:
        return None
    globals()[attr] = value
    __all__.append(attr)
    return value


# Real backends — present only when their dependencies are installed.
DeepgramSTT = _try_export("deepgram_stt", "DeepgramSTT")
AssemblyAISTT = _try_export("assemblyai_stt", "AssemblyAISTT")
CartesiaTTS = _try_export("cartesia_tts", "CartesiaTTS")
