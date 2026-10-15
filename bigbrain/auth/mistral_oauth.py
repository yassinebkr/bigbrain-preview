"""Mistral "Connect with Vibe" browser sign-in wizard.

Faithful port of ``fpga/backend/mistral_setup.py``, which is itself a port of
Mistral Vibe's own ``vibe --setup`` flow (upstream:
github.com/mistralai/mistral-vibe, ``vibe/cli-rust/src/setup/auth/
sign_in_flow.rs`` / ``sign_in_gateway.rs`` / ``whoami.rs``): a PKCE (S256)
browser handshake against the console's ``/api/vibe/sign-in`` endpoints,
polled until the user finishes in the browser, then exchanging the token
for an API key — the same credential a user would paste by hand from
console.mistral.ai.

Safety rules carried over from the upstream port:
- The wizard never prints or returns the key to a client; only the free
  ``GET /v1/models`` health of the stored credential.
- The key is stored in the project ``.env`` (atomic, chmod 0600), mirrored
  to a durable store under ``data/`` (survives container restarts), and
  exported into ``os.environ`` so a running process adopts it without a
  restart.
- Server-returned URLs are validated against the configured console origin
  (split-horizon rules from the upstream wizard).

Exposed as a library (used by the web settings pipeline), as a CLI
(``python -m bigbrain.auth.mistral_oauth``), and through REST endpoints in
``bigbrain/web/server.py``.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import re
import secrets
import sys
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

# Upstream constants (mistralai/mistral-vibe, vibe/core/config/_defaults.py).
CONSOLE_BASE_URL = "https://console.mistral.ai"          # DEFAULT_MISTRAL_BROWSER_AUTH_BASE_URL
BROWSER_AUTH_API_BASE_URL = f"{CONSOLE_BASE_URL}/api"    # DEFAULT_MISTRAL_BROWSER_AUTH_API_BASE_URL
DEFAULT_MISTRAL_SERVER_URL = "https://api.mistral.ai"    # DEFAULT_MISTRAL_SERVER_URL
API_KEY_ENV = "MISTRAL_API_KEY"

_POLL_INTERVAL_S = 3          # upstream: poll every 3 s
_MAX_POLL_FAILURES = 3        # upstream: three consecutive failures abort
_EXCHANGE_TIMEOUT_S = 15
_WHOAMI_TIMEOUT_S = 10
_PROBE_TIMEOUT_S = 5


class SetupError(RuntimeError):
    """Wizard failure; the message is safe for clients (never the key)."""


# -- PKCE (upstream: generate_pkce_pair, method S256) ---------------------------

def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) with method S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


# -- URL validation (upstream: sign_in_url.rs _validate_url_against_base_url) -----

def validate_url(url: str, base_url: str, *, allow_origin_rewrite: bool = False) -> str:
    """Validate a server-returned URL against a configured base.

    Rejects foreign origins (unless rewrite is allowed) and paths outside
    the base path, mirroring the upstream wizard's split-horizon rules.
    """
    parsed = urlparse(url)
    base = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise SetupError("URL validation failed.")
    if (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
        if not allow_origin_rewrite:
            raise SetupError("URL origin validation failed.")
    base_path = (base.path or "/").rstrip("/") or "/"
    if not (parsed.path or "/").startswith(base_path):
        raise SetupError("URL path validation failed.")
    return url


# -- wizard state (single-user app: one active browser flow) ---------------------

@dataclass
class BrowserFlow:
    """One in-flight browser sign-in process (never more than one)."""

    process_id: str = ""
    sign_in_url: str = ""
    poll_url: str = ""
    expires_at: str = ""                     # RFC 3339 with Z suffix
    verifier: str = ""                       # server-side only
    exchange_token: str = ""                  # server-side only
    status: str = "idle"    # idle|waiting|completed|denied|expired|error
    message: str | None = None
    api_base_url: str = BROWSER_AUTH_API_BASE_URL
    console_base_url: str = CONSOLE_BASE_URL

    def summary(self) -> dict[str, Any]:
        """Client-safe view: no verifier, no exchange token, no key."""
        return {
            "status": self.status,
            "message": self.message,
            "sign_in_url": self.sign_in_url or None,
            "expires_at": self.expires_at or None,
        }


_flow = BrowserFlow()


def flow_state() -> BrowserFlow:
    return _flow


def _reset_flow(console: str = CONSOLE_BASE_URL,
                api: str = BROWSER_AUTH_API_BASE_URL) -> BrowserFlow:
    global _flow
    _flow = BrowserFlow(console_base_url=console.rstrip("/"),
                         api_base_url=api.rstrip("/"))
    return _flow


# -- gateway calls (upstream: sign_in_gateway.rs) --------------------------------

async def _post_json(url: str, payload: Mapping[str, Any], timeout: float) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=dict(payload))
        if response.status_code >= 400:
            raise SetupError(f"request failed with HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise SetupError("failed to parse response") from exc
        if not isinstance(body, dict):
            raise SetupError("failed to parse response")
        return body


async def _get_json(url: str, timeout: float, *,
                    headers: Mapping[str, str] | None = None) -> tuple[int, dict[str, Any] | None]:
    """GET returning (status, parsed body or None); 410 is a legitimate
    'expired' answer, so it is returned rather than raised."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, headers=dict(headers or {}))
    try:
        body = response.json()
    except ValueError:
        body = None
    return response.status_code, body if isinstance(body, dict) else None


async def start_browser_sign_in(console_base_url: str | None = None,
                                api_base_url: str | None = None) -> dict[str, Any]:
    """Start the PKCE browser flow: create the sign-in process.

    Returns the client-safe flow summary including ``sign_in_url`` — the
    URL the browser (the "button") must open.
    """
    console = (console_base_url or CONSOLE_BASE_URL).strip()
    if console and not urlparse(console).scheme:
        console = f"https://{console}"
    api = (api_base_url or (
        f"{console.rstrip('/')}/api" if console else BROWSER_AUTH_API_BASE_URL
    )).rstrip("/")
    flow = _reset_flow(console=console, api=api)

    verifier, challenge = generate_pkce_pair()
    url = f"{flow.api_base_url}/vibe/sign-in"
    body = await _post_json(
        url,
        {"code_challenge": challenge, "code_challenge_method": "S256"},
        _EXCHANGE_TIMEOUT_S,
    )
    process_id = body.get("process_id")
    sign_in_url = body.get("sign_in_url")
    poll_url = body.get("poll_url")
    expires_at = body.get("expires_at")
    if not isinstance(process_id, str) or not process_id:
        raise SetupError("sign-in response is missing a process id")
    if not isinstance(sign_in_url, str) or not isinstance(poll_url, str):
        raise SetupError("sign-in response is missing its URLs")
    flow.process_id = process_id
    flow.verifier = verifier
    flow.sign_in_url = validate_url(sign_in_url, flow.console_base_url)
    flow.poll_url = validate_url(poll_url, flow.api_base_url)
    flow.status = "waiting"
    flow.expires_at = expires_at if isinstance(expires_at, str) else ""
    return flow.summary()


def _flow_expired(flow: BrowserFlow) -> bool:
    if not flow.expires_at:
        return False
    try:
        deadline = datetime.fromisoformat(flow.expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) >= deadline


async def poll_browser_sign_in() -> dict[str, Any]:
    """Poll the in-flight process once (upstream cadence is left to callers)."""
    flow = _flow
    if flow.status not in ("waiting",):
        return flow.summary()
    if _flow_expired(flow):
        flow.status = "expired"
        flow.message = "Browser sign-in expired."
        return flow.summary()
    failures = 0
    while True:
        try:
            status, body = await _get_json(
                validate_url(flow.poll_url, flow.api_base_url), _EXCHANGE_TIMEOUT_S
            )
        except Exception:
            status, body = 0, None
        if status == 410:
            flow.status = "expired"
            flow.message = "Browser sign-in expired."
            return flow.summary()
        if status >= 400 or body is None:
            failures += 1
            if failures >= _MAX_POLL_FAILURES:
                flow.status = "error"
                flow.message = (
                    "Browser sign-in poll failed." if body is None
                    else "Failed to parse poll response."
                )
                return flow.summary()
            await asyncio.sleep(1)
            continue
        status_value = body.get("status")
        if status_value == "pending":
            return flow.summary()
        if status_value == "completed":
            exchange_token = body.get("exchange_token")
            if not isinstance(exchange_token, str) or not exchange_token:
                flow.status = "error"
                flow.message = "Missing exchange token."
                return flow.summary()
            flow.exchange_token = exchange_token
            flow.status = "completed"
            flow.message = None
            return flow.summary()
        if status_value in ("expired", "denied"):
            flow.status = status_value
            flow.message = (
                "Browser sign-in expired." if status_value == "expired"
                else "Browser sign-in was denied."
            )
            return flow.summary()
        if status_value == "error":
            flow.status = "error"
            flow.message = str(body.get("message") or "Sign-in failed.")
            return flow.summary()
        flow.status = "error"
        flow.message = "Unknown poll status."
        return flow.summary()


async def complete_browser_sign_in() -> dict[str, Any]:
    """Exchange the completed flow for an API key, verify, and store it.

    The key itself never appears in the returned summary — only the
    free-probe health of the stored credential and any tenant domains the
    console advertises.
    """
    flow = _flow
    if flow.status != "completed" or not flow.exchange_token:
        raise SetupError("browser sign-in is not completed yet")
    url = f"{flow.api_base_url}/vibe/sign-in/{flow.process_id}/exchange"
    body = await _post_json(
        url,
        {"exchange_token": flow.exchange_token, "code_verifier": flow.verifier},
        _EXCHANGE_TIMEOUT_S,
    )
    api_key = body.get("api_key")
    if not isinstance(api_key, str) or not api_key:
        raise SetupError("exchange did not return an API key")
    health = await verify_api_key(api_key)
    tenant = await resolve_tenant_domains(flow.console_base_url, api_key)
    path = save_api_key_to_env(api_key)
    _reset_flow()  # the credential now lives only in the env file / process
    return {"health": health, "env_path": str(path), **tenant}


# -- whoami (upstream: whoami.rs resolve_tenant_domains) -------------------------

async def resolve_tenant_domains(console_base_url: str, api_key: str) -> dict[str, Any]:
    """Ask the console for tenant-specific API hosts (custom domains).

    Any failure degrades to the defaults, exactly like the upstream wizard.
    The key is only sent to the console that issued it.
    """
    url = f"{console_base_url.rstrip('/')}/api/vibe/whoami"
    try:
        status, body = await _get_json(
            url, _WHOAMI_TIMEOUT_S, headers={"Authorization": f"Bearer {api_key}"}
        )
    except Exception:
        return {}
    if status >= 400 or body is None:
        return {}
    result: dict[str, Any] = {}
    api_base = body.get("api_base")
    if isinstance(api_base, str) and api_base.strip():
        result["tenant_api_base"] = api_base.strip().rstrip("/")
    vibe_base = body.get("vibe_base")
    if isinstance(vibe_base, str) and vibe_base.strip():
        result["tenant_vibe_base"] = vibe_base.strip().rstrip("/")
    return result


# -- free key verification (probe, never a paid completion call) -----------------

async def verify_api_key(api_key: str, base_url: str = DEFAULT_MISTRAL_SERVER_URL) -> str:
    """Health of a Mistral key: ok | auth_failed | unreachable."""
    url = f"{base_url.rstrip('/')}/v1/models"
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


# -- persistence (same .env precedence as config.py) -----------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ROOT_ENV = _PROJECT_ROOT / ".env"
_DURABLE_KEYS_FILE = _PROJECT_ROOT / "data" / "provider_keys.env"


def env_file_path() -> Path:
    """The .env the app actually reads (project root)."""
    return _ROOT_ENV


def provider_keys_file() -> Path:
    """The durable wizard key store (survives container restarts)."""
    return _DURABLE_KEYS_FILE


def _upsert_assignment(path: Path, api_key: str, *, force: bool) -> None:
    """Atomically upsert ``MISTRAL_API_KEY=<key>`` into a KEY=VALUE env file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(r"(?m)^(?P<prefix>\s*)MISTRAL_API_KEY\s*=(?P<value>.*)$")
    if pattern.search(text):
        if not force:
            raise SetupError("MISTRAL_API_KEY is already set in the .env (use force)")
        text = pattern.sub(
            lambda m: f"{m.group('prefix')}MISTRAL_API_KEY={api_key}", text, count=1
        )
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"MISTRAL_API_KEY={api_key}\n"
    tmp = path.with_name(f".{path.name}.wizard.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.chmod(0o600)
    os.replace(tmp, path)


def save_api_key_to_env(api_key: str, *, force: bool = False) -> Path:
    """Persist MISTRAL_API_KEY and make it live in this process.

    Three effects: the project ``.env`` (what config.py loads), the durable
    store under ``data/`` (what survives a container rebuild), and
    ``os.environ`` so a running process adopts the key without a restart.
    Refuses to replace an existing non-comment assignment unless ``force``.
    """
    if not api_key or any(ch.isspace() for ch in api_key):
        raise SetupError("invalid API key")
    _upsert_assignment(_ROOT_ENV, api_key, force=force)
    _upsert_assignment(_DURABLE_KEYS_FILE, api_key, force=True)  # wizard-owned
    os.environ[API_KEY_ENV] = api_key
    return _ROOT_ENV


# -- CLI (like ``vibe --setup``) ---------------------------------------------------

async def run_wizard(open_browser: bool = True) -> dict[str, Any]:
    """Interactive wizard: start the flow, open the browser, poll to done."""
    summary = await start_browser_sign_in()
    print("Open this URL in your browser to sign in:")
    print(f"  {summary['sign_in_url']}")
    if open_browser and summary.get("sign_in_url"):
        webbrowser.open(summary["sign_in_url"])
    deadline = time.monotonic() + 15 * 60  # upstream keeps a bounded window
    while time.monotonic() < deadline:
        await asyncio.sleep(_POLL_INTERVAL_S)
        summary = await poll_browser_sign_in()
        print(f"  status: {summary['status']}")
        if summary["status"] == "completed":
            result = await complete_browser_sign_in()
            print(f"Key stored ({result['health']}) in {result['env_path']}")
            return result
        if summary["status"] in ("expired", "denied", "error"):
            raise SetupError(summary.get("message") or "sign-in failed")
    raise SetupError("sign-in window expired")


if __name__ == "__main__":  # pragma: no cover
    try:
        asyncio.run(run_wizard())
    except (SetupError, KeyboardInterrupt) as exc:
        print(f"mistral setup: {exc}", file=sys.stderr)
        sys.exit(1)
