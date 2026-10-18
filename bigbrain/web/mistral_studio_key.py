"""Direct Mistral Studio API-key connection.

This credential is intentionally separate from the Vibe browser-sign-in key:
Studio billing/credits belong to the developer API account and must never be
silently overwritten by either connection flow.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import httpx

MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
API_KEY_ENV = "MISTRAL_STUDIO_API_KEY"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROOT_ENV = _REPO_ROOT / ".env"
_DURABLE_KEYS_FILE = _REPO_ROOT / "data" / "provider_keys.env"


class MistralStudioKeyError(RuntimeError):
    """Client-safe failure that never includes the submitted secret."""


async def verify_key(api_key: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{MISTRAL_BASE_URL}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if 200 <= response.status_code < 300:
            return "ok"
        if response.status_code in (401, 403):
            return "auth_failed"
        return "unreachable"
    except Exception:
        return "unreachable"


def _upsert_assignment(path: Path, name: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(rf"(?m)^(?P<prefix>\s*){re.escape(name)}\s*=.*$")
    replacement = rf"\g<prefix>{name}={value}"
    text = pattern.sub(replacement, text, count=1) if pattern.search(text) else (
        text + ("" if not text or text.endswith("\n") else "\n") + f"{name}={value}\n"
    )
    tmp = path.with_name(f".{path.name}.mistral-studio.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.chmod(0o600)
    os.replace(tmp, path)


async def connect_key(api_key: str) -> dict:
    if not api_key or any(char.isspace() for char in api_key):
        raise MistralStudioKeyError("invalid API key")
    health = await verify_key(api_key)
    if health != "ok":
        raise MistralStudioKeyError(f"key rejected ({health})")
    for path in (_ROOT_ENV, _DURABLE_KEYS_FILE):
        _upsert_assignment(path, API_KEY_ENV, api_key)
        _upsert_assignment(path, "BIGBRAIN_PROVIDER", "mistral-studio-large-4")
    os.environ[API_KEY_ENV] = api_key
    os.environ["BIGBRAIN_PROVIDER"] = "mistral-studio-large-4"
    return {"health": health, "env_path": str(_ROOT_ENV)}
