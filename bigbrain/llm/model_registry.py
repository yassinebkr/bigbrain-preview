"""Provider/model registry for BigBrain.

Maps a short key to everything needed to build a provider client: display
name, provider kind, base URL, the env var holding the API key, the
provider-side model id, and capability flags (reasoning, streaming). The
pattern is ported from ``fpga/backend/model_registry.py`` (Phase 0 of the
multi-provider plan there) and adapted to BigBrain's LLMProvider interface.

Design rules (carried over from fpga, verified live there):
- ``verify_model(key)`` uses only FREE authenticated GETs (OpenRouter
  ``/auth/key`` credit metadata, Mistral/Kimi ``/models``), so a health
  check never makes a paid completion call.
- Env overrides are read at call time, not import time, so tests and the
  Mistral setup wizard can monkeypatch the environment.
- Model ids evolve quickly on OpenRouter: every id is overridable via env
  (documented in docs/MODELS.md) and the registry is the single place to
  update them.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field

import httpx

# -- defaults -----------------------------------------------------------------

# Roles used by BigBrainConfig (front / code / web / planner / subagent).
DEFAULT_FRONT_MODEL_KEY = os.getenv("BIGBRAIN_FRONT_MODEL_KEY", "openrouter-gpt-6.1-sol")
DEFAULT_CODE_MODEL_KEY = os.getenv("BIGBRAIN_CODE_MODEL_KEY", "openrouter-gpt-6.1-sol")
DEFAULT_PLANNER_MODEL_KEY = os.getenv("BIGBRAIN_PLANNER_MODEL_KEY", "openrouter-gpt-6.1-sol")
DEFAULT_SUBAGENT_MODEL_KEY = os.getenv("BIGBRAIN_SUBAGENT_MODEL_KEY", "openrouter-gpt-6.1-sol")

_OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class ModelEntry:
    """One provider/model combo the system knows how to talk to."""

    key: str
    display_name: str
    provider: str            # openai_compat | codex | anthropic_oauth | litellm
    model_id: str
    api_key_env: str
    base_url: str = ""
    health_path: str = ""    # FREE auth-check GET (never a paid completion)
    # Streams private reasoning via the reasoning_content delta field;
    # thinking tokens are billed against the completion budget.
    reasoning: bool = False
    reasoning_efforts: list[str] = field(default_factory=list)
    reasoning_effort_default: str | None = None
    # Accepts OpenAI-style image_url content blocks.
    vision: bool = False
    # Some reasoning endpoints reject temperature rather than sampling with it.
    supports_temperature: bool = True
    # Optional monthly context window, for budget heuristics only.
    context_window: int | None = None

    def with_env_overrides(self) -> "ModelEntry":
        """Apply per-key env overrides (base URL and model id) at call time."""
        prefix = self.key.upper().replace("-", "_")
        base_url = os.environ.get(f"{prefix}_BASE_URL", self.base_url)
        model_id = os.environ.get(f"{prefix}_MODEL", self.model_id)
        effort = os.environ.get(f"{prefix}_REASONING_EFFORT")
        if effort and self.reasoning_efforts and effort in self.reasoning_efforts:
            reasoning_effort_default = effort
        else:
            reasoning_effort_default = self.reasoning_effort_default
        return ModelEntry(
            key=self.key,
            display_name=self.display_name,
            provider=self.provider,
            model_id=model_id,
            api_key_env=self.api_key_env,
            base_url=base_url,
            health_path=self.health_path,
            reasoning=self.reasoning,
            reasoning_efforts=list(self.reasoning_efforts),
            reasoning_effort_default=reasoning_effort_default,
            vision=self.vision,
            supports_temperature=self.supports_temperature,
            context_window=self.context_window,
        )


_REGISTRY: dict[str, ModelEntry] = {
    # -- OpenRouter (one key covers all models below) -------------------------
    "openrouter-gpt-6.1-sol": ModelEntry(
        key="openrouter-gpt-6.1-sol",
        display_name="GPT-6.1 Sol (OpenRouter)",
        provider="openai_compat",
        model_id="openai/gpt-6.1-sol",
        api_key_env="OPENROUTER_API_KEY",
        base_url=_OPENROUTER_DEFAULT_BASE_URL,
        health_path="/auth/key",
        reasoning=True,
        reasoning_efforts=["low", "medium", "high", "xhigh", "max"],
        reasoning_effort_default="medium",
        supports_temperature=False,
        vision=True,
        context_window=1_050_000,
    ),
    "openrouter-gpt-sol": ModelEntry(
        key="openrouter-gpt-sol",
        display_name="ChatGPT Sol (OpenRouter)",
        provider="openai_compat",
        # Reference model used by the near_agi campaigns via OpenRouter.
        model_id="openai/gpt-5.6-sol",
        api_key_env="OPENROUTER_API_KEY",
        base_url=_OPENROUTER_DEFAULT_BASE_URL,
        health_path="/auth/key",
        reasoning=True,
        reasoning_efforts=["low", "medium", "high"],
        reasoning_effort_default="low",
        vision=True,
    ),
    "openrouter-kimi-k3": ModelEntry(
        key="openrouter-kimi-k3",
        display_name="Kimi K3 (OpenRouter)",
        provider="openai_compat",
        model_id="moonshotai/kimi-k3",
        api_key_env="OPENROUTER_API_KEY",
        base_url=_OPENROUTER_DEFAULT_BASE_URL,
        health_path="/auth/key",
        reasoning=True,
        reasoning_efforts=["low", "medium", "high"],
        reasoning_effort_default="low",
        vision=True,
    ),
    "openrouter-opus-5.5": ModelEntry(
        key="openrouter-opus-5.5",
        display_name="Claude Opus 5.5 (OpenRouter)",
        provider="openai_compat",
        model_id="anthropic/claude-opus-5.5",
        api_key_env="OPENROUTER_API_KEY",
        base_url=_OPENROUTER_DEFAULT_BASE_URL,
        health_path="/auth/key",
        reasoning=False,
        vision=True,
    ),
    "openrouter-mistral-large-4": ModelEntry(
        key="openrouter-mistral-large-4",
        display_name="Mistral Large 4 (OpenRouter)",
        provider="openai_compat",
        model_id="mistralai/mistral-large-4-0",
        api_key_env="OPENROUTER_API_KEY",
        base_url=_OPENROUTER_DEFAULT_BASE_URL,
        health_path="/auth/key",
        reasoning=False,
        # The native model is multimodal, but OpenRouter currently exposes
        # text/JSON-state input only for this route.
        vision=False,
    ),
    "openrouter-luna": ModelEntry(
        key="openrouter-luna",
        display_name="GPT Luna (OpenRouter)",
        provider="openai_compat",
        # Luna is the codex app-server's small default; the OpenRouter id
        # mirrors it for sub-agent (sub-brain) calls.
        model_id="openai/gpt-5.6-luna",
        api_key_env="OPENROUTER_API_KEY",
        base_url=_OPENROUTER_DEFAULT_BASE_URL,
        health_path="/auth/key",
        reasoning=False,
    ),
    # -- Direct providers ------------------------------------------------------
    "kimi-k3": ModelEntry(
        key="kimi-k3",
        display_name="Kimi K3 (direct)",
        provider="openai_compat",
        model_id="k3",
        api_key_env="KIMI_API_KEY",
        base_url="https://api.kimi.com/coding/v1",
        health_path="/models",
        reasoning=True,
        reasoning_efforts=["low", "medium", "high"],
        reasoning_effort_default="low",
        vision=True,
    ),
    "mistral-vibe": ModelEntry(
        key="mistral-vibe",
        display_name="Mistral Medium 3.5 (Vibe default)",
        provider="openai_compat",
        model_id="mistral-medium-3-5",
        api_key_env="MISTRAL_API_KEY",
        base_url="https://api.mistral.ai/v1",
        health_path="/models",
        reasoning=False,
    ),
    "mistral-studio-large-4": ModelEntry(
        key="mistral-studio-large-4",
        display_name="Mistral Large 4 (Studio API)",
        provider="openai_compat",
        model_id="mistral-large-4",
        api_key_env="MISTRAL_STUDIO_API_KEY",
        base_url="https://api.mistral.ai/v1",
        health_path="/models",
        reasoning=True,
        reasoning_efforts=["none", "high"],
        reasoning_effort_default="high",
        vision=True,
        context_window=1_000_000,
    ),
    "mistral-glm-5.3": ModelEntry(
        key="mistral-glm-5.3",
        display_name="GLM 5.3 (Mistral hosted)",
        provider="openai_compat",
        # Third-party model on the Mistral platform API (docs.mistral.ai),
        # same MISTRAL_API_KEY as the vibe subscription.
        model_id="zai-glm-5-3",
        api_key_env="MISTRAL_API_KEY",
        base_url="https://api.mistral.ai/v1",
        health_path="/models",
        # GLM 5.3 ALWAYS thinks (rejects effort "none"); thinking streams as
        # typed chunks inside delta.content and shares the completion budget,
        # so low effort by default (fpga's measured lesson: high burned ~30k
        # thinking tokens on a small round).
        reasoning=True,
        reasoning_efforts=["low", "high", "max"],
        reasoning_effort_default="low",
    ),
    # -- Subscription-backed (no API key; local credential store) --------------
    "codex-sol-6.1": ModelEntry(
        key="codex-sol-6.1", display_name="GPT-6.1 Sol (Codex)",
        provider="codex", model_id="gpt-6.1-sol", api_key_env="",
        reasoning=True, reasoning_efforts=["low", "medium", "high", "xhigh", "max"],
        reasoning_effort_default="low", vision=True, context_window=1_050_000,
    ),
    "codex-luna-6": ModelEntry(
        key="codex-luna-6", display_name="GPT-6 Luna (Codex)",
        provider="codex", model_id="gpt-6-luna", api_key_env="",
        reasoning=True, reasoning_efforts=["none", "low", "medium", "high", "xhigh", "max"],
        reasoning_effort_default="low", vision=True, context_window=1_050_000,
    ),
    "codex-chatgpt": ModelEntry(
        key="codex-chatgpt",
        display_name="Codex (ChatGPT subscription)",
        provider="codex",
        # Default model of the app-server; per-turn override possible.
        model_id="gpt-5.6-luna",
        api_key_env="",  # auth owned by `codex app-server` (~/.codex creds)
    ),
    "anthropic-oauth": ModelEntry(
        key="anthropic-oauth",
        display_name="Claude (Pro/Max subscription)",
        provider="anthropic_oauth",
        model_id="claude-sonnet-4-6",
        api_key_env="",  # auth handled by llm.anthropic_oauth token store
    ),
}


def get_model(key: str) -> ModelEntry:
    """Resolve a registry key to an entry (env overrides applied).

    Raises KeyError on unknown keys.
    """
    return _REGISTRY[key].with_env_overrides()


def list_models() -> list[dict]:
    """All registry entries with an availability flag (key env var set)."""
    entries = []
    for key, entry in _REGISTRY.items():
        available = (
            True  # subscription-backed: availability checked via account/read
            if entry.provider in ("codex",)
            else bool(entry.api_key_env and os.environ.get(entry.api_key_env))
        )
        if entry.provider == "anthropic_oauth":
            available = _has_anthropic_oauth_token()
        entries.append(
            {
                "key": key,
                "display_name": entry.display_name,
                "provider": entry.provider,
                "available": available,
                "reasoning": entry.reasoning,
                "reasoning_efforts": list(entry.reasoning_efforts),
                "reasoning_effort_default": entry.reasoning_effort_default,
                "vision": entry.vision,
            }
        )
    return entries


def _has_anthropic_oauth_token() -> bool:
    try:
        from ..auth.oauth import get_api_key

        return get_api_key() is not None
    except Exception:
        return False


def role_default_key(role: str) -> str:
    """Registry key for a BigBrain role: front | code | planner | subagent."""
    mapping = {
        "front": DEFAULT_FRONT_MODEL_KEY,
        "code": DEFAULT_CODE_MODEL_KEY,
        "planner": DEFAULT_PLANNER_MODEL_KEY,
        "subagent": DEFAULT_SUBAGENT_MODEL_KEY,
        "research": DEFAULT_SUBAGENT_MODEL_KEY,
    }
    return mapping.get(role, DEFAULT_FRONT_MODEL_KEY)


# -- proactive key verification (free auth-check GETs, cached) ----------------

HEALTH_TTL_S = 60       # cache probe results so UI polling doesn't hammer
_HEALTH_TIMEOUT_S = 5    # per-provider probe timeout cap

_health_cache: dict[str, tuple[float, str]] = {}


async def _probe(url: str, api_key: str) -> int:
    """GET a provider's free auth-check endpoint; returns the HTTP status code."""
    async with httpx.AsyncClient(timeout=_HEALTH_TIMEOUT_S) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        return response.status_code


async def verify_model(key: str) -> str:
    """Health of a registry entry: ok | auth_failed | unreachable | unknown | no_key.

    Never logs or returns the key or response bodies — only the status word.
    Subscription-backed entries (codex) are checked through their provider.
    """
    entry = get_model(key)
    if entry.provider == "codex":
        status = await codex_account_status()
        return "ok" if status.get("authenticated") else "no_key"
    if entry.provider == "anthropic_oauth":
        return "ok" if _has_anthropic_oauth_token() else "no_key"
    if not entry.api_key_env:
        return "no_key"
    api_key = os.environ.get(entry.api_key_env)
    if not api_key:
        return "no_key"
    now = time.monotonic()
    cached = _health_cache.get(key)
    if cached and now - cached[0] < HEALTH_TTL_S:
        return cached[1]
    url = entry.base_url.rstrip("/") + entry.health_path
    try:
        status = await _probe(url, api_key)
    except Exception:  # DNS/connect/timeout — provider (or network) down
        health = "unreachable"
    else:
        if 200 <= status < 300:
            health = "ok"
        elif status in (401, 403):
            health = "auth_failed"
        elif status == 404:
            health = "unknown"
        else:
            health = "unreachable"
    _health_cache[key] = (now, health)
    return health


async def verify_all() -> dict[str, str]:
    """Verify every registry entry concurrently; key -> health status."""
    keys = list(_REGISTRY)
    statuses = await asyncio.gather(*(verify_model(key) for key in keys))
    return dict(zip(keys, statuses))


async def codex_account_status() -> dict:
    """Who is signed in to the codex app-server (used by settings + polling).

    Delegates to llm.codex_provider; kept here so the registry is the single
    facade for provider availability.
    """
    from .codex_provider import codex_auth_status

    return await codex_auth_status()
