"""OpenRouter API-key connection (the "OpenRouter (API)" provider button).

Same discipline as the Mistral wizard: the key is validated with the FREE
``GET /api/v1/auth/key`` credit endpoint (never a paid completion), stored
atomically (0600) in the project ``.env`` + the durable ``data/`` store, and
exported into ``os.environ`` so a running system adopts it without restart.
The key never appears in any response.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
API_KEY_ENV = "OPENROUTER_API_KEY"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROOT_ENV = _REPO_ROOT / ".env"
_DURABLE_KEYS_FILE = _REPO_ROOT / "data" / "provider_keys.env"

_PROBE_TIMEOUT_S = 5


class OpenRouterKeyError(RuntimeError):
    """Message safe for clients (never contains the key)."""


async def verify_key(api_key: str) -> str:
    """Health of an OpenRouter key: ok | auth_failed | unreachable."""
    url = f"{OPENROUTER_BASE_URL}/auth/key"
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
            response = await client.get(
                url, headers={"Authorization": f"Bearer {api_key}"}
            )
        if 200 <= response.status_code < 300:
            return "ok"
        if response.status_code in (401, 403):
            return "auth_failed"
        return "unreachable"
    except Exception:
        return "unreachable"


def _upsert_env_file(path: Path, api_key: str) -> None:
    """Atomically upsert OPENROUTER_API_KEY=<key> into a KEY=VALUE env file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(r"(?m)^(?P<prefix>\s*)OPENROUTER_API_KEY\s*=(?P<value>.*)$")
    if pattern.search(text):
        text = pattern.sub(
            lambda m: f"{m.group('prefix')}OPENROUTER_API_KEY={api_key}", text, count=1
        )
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"OPENROUTER_API_KEY={api_key}\n"
    tmp = path.with_name(f".{path.name}.or.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.chmod(0o600)
    os.replace(tmp, path)


async def connect_key(api_key: str) -> dict:
    """Validate, persist and activate an OpenRouter API key."""
    if not api_key or any(ch.isspace() for ch in api_key):
        raise OpenRouterKeyError("invalid API key")
    health = await verify_key(api_key)
    if health != "ok":
        raise OpenRouterKeyError(f"key rejected ({health})")
    _upsert_env_file(_ROOT_ENV, api_key)
    _upsert_env_file(_DURABLE_KEYS_FILE, api_key)
    os.environ[API_KEY_ENV] = api_key
    return {"health": health, "env_path": str(_ROOT_ENV)}
