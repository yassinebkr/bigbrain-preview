"""Provider selection facade — one place that decides which provider to build.

Priority order (first available wins, overridable with ``BIGBRAIN_PROVIDER``):
1. ``anthropic-oauth``  — stored Claude Pro/Max OAuth token
2. ``openrouter-*``    — OPENROUTER_API_KEY (Sol 6.1/5.6, Kimi K3, Opus 5.5, Luna)
3. ``mistral-studio-large-4`` — MISTRAL_STUDIO_API_KEY (developer API)
4. ``mistral-vibe``    — MISTRAL_API_KEY (set by the browser sign-in wizard)
5. ``kimi-k3``         — KIMI_API_KEY (direct)
6. litellm keys        — OPENAI/ANTHROPIC/GOOGLE_API_KEY (legacy env keys)
7. ``codex-chatgpt``   — codex CLI on PATH with stored credentials
8. mock

Subscription-backed providers (codex, anthropic-oauth) are picked by the
presence of their local credential store, never by an env API key.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

# Registry keys selectable through BIGBRAIN_PROVIDER.
KNOWN_PROVIDER_KEYS = {
    "anthropic-oauth", "codex-chatgpt", "mistral-vibe", "mistral-studio-large-4", "kimi-k3",
    "openrouter-gpt-6.1-sol", "openrouter-gpt-sol", "openrouter-kimi-k3",
    "openrouter-opus-5.5", "openrouter-luna",
}

_CODEX_CREDS = Path.home() / ".codex" / "auth.json"


def anthropic_oauth_token() -> Optional[str]:
    """Stored Claude Pro/Max OAuth token, if present (no network)."""
    try:
        from .oauth import get_api_key

        return get_api_key()
    except Exception:
        return None


def codex_available() -> bool:
    """Cheap check: codex CLI installed and credentials file present.

    Full account validation happens through the app-server
    (``llm.codex_provider.codex_auth_status``) — this is only the cheap
    gate for provider selection.
    """
    return shutil.which("codex") is not None and _CODEX_CREDS.exists()


def select_registry_key() -> Optional[str]:
    """Registry key of the best available provider, or None for litellm/mock."""
    forced = os.getenv("BIGBRAIN_PROVIDER", "").strip()
    if forced:
        if forced not in KNOWN_PROVIDER_KEYS:
            raise ValueError(
                f"unknown BIGBRAIN_PROVIDER '{forced}' (known: {sorted(KNOWN_PROVIDER_KEYS)})"
            )
        return forced
    if anthropic_oauth_token():
        return "anthropic-oauth"
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter-gpt-6.1-sol"
    if os.environ.get("MISTRAL_STUDIO_API_KEY"):
        return "mistral-studio-large-4"
    if os.environ.get("MISTRAL_API_KEY"):
        return "mistral-vibe"
    if os.environ.get("KIMI_API_KEY"):
        return "kimi-k3"
    if codex_available():
        return "codex-chatgpt"
    return None


def build_provider(registry_key: str):
    """Instantiate the LLMProvider for a registry key."""
    from ..llm.model_registry import get_model

    entry = get_model(registry_key)
    if entry.provider == "anthropic_oauth":
        from ..llm.anthropic_oauth import AnthropicOAuthProvider

        token = anthropic_oauth_token()
        if not token:
            raise RuntimeError("anthropic-oauth selected but no token stored")
        model = os.environ.get("BIGBRAIN_FRONT_MODEL") or entry.model_id
        return AnthropicOAuthProvider(token=token, default_model=model)
    if entry.provider == "codex":
        from ..llm.codex_provider import CodexProvider

        return CodexProvider(registry_key)
    if entry.provider == "openai_compat":
        from ..llm.openai_compat_provider import OpenAICompatProvider

        return OpenAICompatProvider(registry_key)
    raise ValueError(f"registry key '{registry_key}' has no provider builder")
