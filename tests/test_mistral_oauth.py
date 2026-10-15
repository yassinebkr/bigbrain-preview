"""Tests for the Mistral browser sign-in wizard (Phase 4b).

Mocks the console gateway calls — no network, and the API key never leaks
into any summary.
"""

import pytest

from bigbrain.auth import mistral_oauth
from bigbrain.auth.mistral_oauth import (
    SetupError,
    complete_browser_sign_in,
    generate_pkce_pair,
    poll_browser_sign_in,
    save_api_key_to_env,
    start_browser_sign_in,
    validate_url,
    verify_api_key,
)


def test_pkce_pair_is_s256_consistent():
    verifier, challenge = generate_pkce_pair()
    import base64
    import hashlib
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    assert challenge == expected
    assert len(verifier) >= 40


def test_validate_url_rejects_foreign_origin():
    with pytest.raises(SetupError):
        validate_url("https://evil.example/sign-in", "https://console.mistral.ai")
    with pytest.raises(SetupError):
        validate_url("not a url", "https://console.mistral.ai")
    good = validate_url(
        "https://console.mistral.ai/other/path", "https://console.mistral.ai"
    )
    assert good.endswith("/other/path")


@pytest.mark.asyncio
async def test_full_flow_start_poll_complete(monkeypatch, tmp_path):
    """Happy path: start → pending → completed → exchange → stored + live."""
    captured = {}

    async def fake_post_json(url, payload, timeout):
        captured["post_url"] = url
        if url.endswith("/vibe/sign-in"):
            return {
                "process_id": "proc-1",
                "sign_in_url": "https://console.mistral.ai/sign-in/abc",
                "poll_url": f"{mistral_oauth.BROWSER_AUTH_API_BASE_URL}/vibe/sign-in/proc-1/poll",
                "expires_at": "2099-01-01T00:00:00Z",
            }
        if url.endswith("/exchange"):
            return {"api_key": "test-key-123"}
        raise AssertionError(f"unexpected POST {url}")

    poll_states = iter(["pending", "completed"])

    async def fake_get_json(url, timeout, headers=None):
        captured["poll_url"] = url
        if "poll" in url:
            state = next(poll_states)
            if state == "pending":
                return 200, {"status": "pending"}
            return 200, {"status": "completed", "exchange_token": "tok-1"}
        if "whoami" in url:
            return 200, {"api_base": "https://api.tenant.example"}
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(mistral_oauth, "_post_json", fake_post_json)
    monkeypatch.setattr(mistral_oauth, "_get_json", fake_get_json)

    async def fake_verify(api_key, base_url=None):
        assert api_key == "test-key-123"
        return "ok"

    monkeypatch.setattr(mistral_oauth, "verify_api_key", fake_verify)

    # Redirect the env stores to tmp so the test never touches a real .env.
    monkeypatch.setattr(mistral_oauth, "_ROOT_ENV", tmp_path / ".env")
    monkeypatch.setattr(mistral_oauth, "_DURABLE_KEYS_FILE",
                        tmp_path / "data" / "provider_keys.env")

    summary = await start_browser_sign_in()
    assert summary["status"] == "waiting"
    assert summary["sign_in_url"].startswith("https://console.mistral.ai")

    pending = await poll_browser_sign_in()
    assert pending["status"] == "waiting"

    completed = await poll_browser_sign_in()
    assert completed["status"] == "completed"

    result = await complete_browser_sign_in()
    assert result["health"] == "ok"
    assert "api_key" not in result
    assert result["tenant_api_base"] == "https://api.tenant.example"
    assert (tmp_path / ".env").read_text().strip() == "MISTRAL_API_KEY=test-key-123"
    assert (tmp_path / "data" / "provider_keys.env").exists()


@pytest.mark.asyncio
async def test_save_refuses_to_clobber_without_force(tmp_path, monkeypatch):
    monkeypatch.setattr(mistral_oauth, "_ROOT_ENV", tmp_path / ".env")
    monkeypatch.setattr(mistral_oauth, "_DURABLE_KEYS_FILE",
                        tmp_path / "data" / "provider_keys.env")
    path = save_api_key_to_env("key-one")
    assert path == tmp_path / ".env"
    with pytest.raises(SetupError):
        save_api_key_to_env("key-two")
    # Force overwrites.
    save_api_key_to_env("key-two", force=True)
    assert "MISTRAL_API_KEY=key-two" in (tmp_path / ".env").read_text()


@pytest.mark.asyncio
async def test_verify_api_key_statuses(monkeypatch):
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            if request.headers.get("Authorization") == "Bearer good":
                return httpx.Response(200, json={"data": []})
            return httpx.Response(401)
        return httpx.Response(404)

    real_client = mistral_oauth.httpx.AsyncClient

    def client_factory(timeout=None):
        return real_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(mistral_oauth.httpx, "AsyncClient", client_factory)
    assert await verify_api_key("good") == "ok"
    assert await verify_api_key("bad") == "auth_failed"
