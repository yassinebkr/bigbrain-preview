"""BigBrain authentication — OAuth flows and provider selection.

Unified surface (Phase 2 refactor): every way BigBrain obtains credentials
lives here — Claude Pro/Max OAuth (``oauth``), Mistral browser sign-in
(``mistral_oauth``), codex/ChatGPT subscription (via ``llm.codex_provider``,
owned by the codex CLI) — plus the ``registry`` facade that decides which
provider the system should build.
"""

from . import mistral_oauth, registry

__all__ = ["mistral_oauth", "registry"]
