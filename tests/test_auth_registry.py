"""Tests for the provider selection facade (Phase 2b/3)."""

import pytest

from bigbrain.auth import registry


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in (
        "BIGBRAIN_PROVIDER", "OPENROUTER_API_KEY", "MISTRAL_API_KEY", "MISTRAL_STUDIO_API_KEY",
        "KIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(registry, "anthropic_oauth_token", lambda: None)
    monkeypatch.setattr(registry, "codex_available", lambda: False)


def test_priority_oauth_first(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(registry, "anthropic_oauth_token", lambda: "tok")
    assert registry.select_registry_key() == "anthropic-oauth"


def test_priority_openrouter_before_mistral(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    assert registry.select_registry_key() == "openrouter-gpt-sol"


def test_priority_mistral_then_kimi_then_codex(monkeypatch):
    monkeypatch.setenv("MISTRAL_STUDIO_API_KEY", "k")
    assert registry.select_registry_key() == "mistral-studio-large-4"
    monkeypatch.delenv("MISTRAL_STUDIO_API_KEY")
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    assert registry.select_registry_key() == "mistral-vibe"
    monkeypatch.delenv("MISTRAL_API_KEY")
    monkeypatch.setenv("KIMI_API_KEY", "k")
    assert registry.select_registry_key() == "kimi-k3"
    monkeypatch.delenv("KIMI_API_KEY")
    monkeypatch.setattr(registry, "codex_available", lambda: True)
    assert registry.select_registry_key() == "codex-chatgpt"


def test_no_provider_returns_none():
    assert registry.select_registry_key() is None


def test_forced_provider_validated():
    import os
    os.environ["BIGBRAIN_PROVIDER"] = "openrouter-luna"
    try:
        assert registry.select_registry_key() == "openrouter-luna"
    finally:
        del os.environ["BIGBRAIN_PROVIDER"]
    os.environ["BIGBRAIN_PROVIDER"] = "not-a-key"
    try:
        with pytest.raises(ValueError, match="unknown BIGBRAIN_PROVIDER"):
            registry.select_registry_key()
    finally:
        del os.environ["BIGBRAIN_PROVIDER"]


def test_build_provider_openai_compat(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    from bigbrain.llm.openai_compat_provider import OpenAICompatProvider

    provider = registry.build_provider("openrouter-kimi-k3")
    assert isinstance(provider, OpenAICompatProvider)
    assert provider.entry.model_id == "moonshotai/kimi-k3"
    assert provider.api_key == "k"


def test_build_provider_codex():
    from bigbrain.llm.codex_provider import CodexProvider

    provider = registry.build_provider("codex-chatgpt")
    assert isinstance(provider, CodexProvider)
    assert provider.default_model == "gpt-5.6-luna"
