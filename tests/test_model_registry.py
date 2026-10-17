"""Tests for the model registry (Phase 3)."""

import pytest

from bigbrain.llm import model_registry
from bigbrain.llm.model_registry import (
    get_model,
    list_models,
    role_default_key,
    verify_model,
)


def test_registry_contains_all_phase3_models():
    keys = {entry["key"] for entry in list_models()}
    expected = {
        "openrouter-gpt-sol",
        "openrouter-kimi-k3",
        "openrouter-opus-5.5",
        "openrouter-mistral-large-4",
        "openrouter-kimi-k2.7-code",
        "openrouter-luna",
        "kimi-k3",
        "mistral-vibe",
        "mistral-studio-large-4",
        "codex-chatgpt",
        "anthropic-oauth",
    }
    assert expected <= keys


def test_all_openrouter_entries_share_one_key_env():
    entries = [get_model(k) for k in (
        "openrouter-gpt-sol", "openrouter-kimi-k3", "openrouter-opus-5.5",
        "openrouter-mistral-large-4", "openrouter-kimi-k2.7-code",
        "openrouter-luna",
    )]
    assert all(e.api_key_env == "OPENROUTER_API_KEY" for e in entries)
    assert all(e.base_url == "https://openrouter.ai/api/v1" for e in entries)
    assert all(e.health_path == "/auth/key" for e in entries)


def test_env_overrides_read_at_call_time(monkeypatch):
    monkeypatch.setenv("OPENROUTER_GPT_SOL_MODEL", "openai/gpt-9-test")
    monkeypatch.setenv("OPENROUTER_GPT_SOL_BASE_URL", "https://example.test/v1")
    entry = get_model("openrouter-gpt-sol")
    assert entry.model_id == "openai/gpt-9-test"
    assert entry.base_url == "https://example.test/v1"


def test_reasoning_models_declare_efforts():
    entry = get_model("openrouter-kimi-k3")
    assert entry.reasoning is True
    assert entry.reasoning_effort_default == "low"
    assert "low" in entry.reasoning_efforts


def test_role_defaults_are_distinct():
    roles = {r: role_default_key(r) for r in ("front", "code", "planner", "subagent")}
    assert roles["subagent"] == "openrouter-luna"
    assert roles["code"] == "openrouter-kimi-k2.7-code"
    assert len(set(roles.values())) >= 3


def test_unknown_key_raises():
    with pytest.raises(KeyError):
        get_model("no-such-model")


def test_availability_follows_env(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    models = {m["key"]: m for m in list_models()}
    assert models["openrouter-gpt-sol"]["available"] is False
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert {m["key"]: m for m in list_models()}["openrouter-gpt-sol"]["available"] is True


@pytest.mark.asyncio
async def test_verify_model_no_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert await verify_model("openrouter-gpt-sol") == "no_key"


@pytest.mark.asyncio
async def test_verify_model_ok_and_cached(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    model_registry._health_cache.clear()

    async def fake_probe(url, api_key):
        assert "auth/key" in url
        return 200

    monkeypatch.setattr(model_registry, "_probe", fake_probe)
    assert await verify_model("openrouter-gpt-sol") == "ok"
    # Cached: second call must not re-probe (probe would raise).
    async def exploding_probe(url, api_key):
        raise AssertionError("probe should be cached")
    monkeypatch.setattr(model_registry, "_probe", exploding_probe)
    assert await verify_model("openrouter-gpt-sol") == "ok"


@pytest.mark.asyncio
async def test_verify_model_auth_failed(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-bad")
    model_registry._health_cache.clear()

    async def fake_probe(url, api_key):
        return 401

    monkeypatch.setattr(model_registry, "_probe", fake_probe)
    assert await verify_model("openrouter-gpt-sol") == "auth_failed"


def test_model_entry_is_frozen():
    entry = get_model("mistral-vibe")
    with pytest.raises(Exception):
        entry.model_id = "changed"


def test_vision_capability_is_explicit_and_exposed():
    assert get_model("openrouter-gpt-sol").vision is True
    assert get_model("openrouter-kimi-k3").vision is True
    assert get_model("kimi-k3").vision is True
    assert get_model("mistral-glm-5.3").vision is False
    assert get_model("openrouter-kimi-k2.7-code").vision is True
    assert get_model("openrouter-mistral-large-4").vision is False
    assert get_model("mistral-studio-large-4").vision is True
    models = {m["key"]: m for m in list_models()}
    assert models["openrouter-gpt-sol"]["vision"] is True
    assert models["openrouter-kimi-k3"]["vision"] is True
    assert models["kimi-k3"]["vision"] is True
    assert models["mistral-glm-5.3"]["vision"] is False
    assert models["openrouter-kimi-k2.7-code"]["vision"] is True
    assert models["openrouter-mistral-large-4"]["vision"] is False
    assert models["mistral-studio-large-4"]["vision"] is True
