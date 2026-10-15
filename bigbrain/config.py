"""BigBrain configuration — loads from .env or environment variables."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


def _load_dotenv() -> None:
    """Load .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
        # Search up from CWD to find .env
        env_path = Path.cwd() / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            # Check project root
            project_root = Path(__file__).parent.parent / ".env"
            if project_root.exists():
                load_dotenv(project_root)
    except ImportError:
        pass  # python-dotenv not installed, rely on real env vars


# Load .env on import
_load_dotenv()


@dataclass
class BigBrainConfig:
    """System configuration loaded from environment."""

    # --- LLM ---
    # Set ONE of these to enable real LLM responses.
    # If none are set, MockLLMProvider is used automatically.
    openai_api_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    anthropic_api_key: Optional[str] = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    google_api_key: Optional[str] = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY"))
    # Registry-backed API keys (Phase 3): one OpenRouter key covers all
    # openrouter-* models; MISTRAL_API_KEY is set by the browser sign-in
    # wizard (auth/mistral_oauth.py); KIMI_API_KEY is the direct Kimi endpoint.
    openrouter_api_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY"))
    mistral_api_key: Optional[str] = field(default_factory=lambda: os.getenv("MISTRAL_API_KEY"))
    kimi_api_key: Optional[str] = field(default_factory=lambda: os.getenv("KIMI_API_KEY"))

    # Model to use (litellm format: "gpt-4o", "claude-sonnet-4-20250514", "gemini/gemini-2.0-flash", etc.)
    default_model: str = field(default_factory=lambda: os.getenv("BIGBRAIN_MODEL", "gpt-4o-mini"))
    front_brain_model: str = field(default_factory=lambda: os.getenv("BIGBRAIN_FRONT_MODEL", ""))
    code_model: str = field(default_factory=lambda: os.getenv("BIGBRAIN_CODE_MODEL", ""))
    planner_model: str = field(default_factory=lambda: os.getenv("BIGBRAIN_PLANNER_MODEL", ""))
    # Model for sub-brains / sub-agents (defaults to the front brain model).
    subagent_model: str = field(default_factory=lambda: os.getenv("BIGBRAIN_SUBAGENT_MODEL", ""))

    # --- Workspace ---
    workspace: str = field(default_factory=lambda: os.getenv("BIGBRAIN_WORKSPACE", "demo"))
    log_dir: str = field(default_factory=lambda: os.getenv("BIGBRAIN_LOG_DIR", "logs"))

    # --- Limits ---
    max_tokens: int = field(default_factory=lambda: int(os.getenv("BIGBRAIN_MAX_TOKENS", "2048")))
    code_timeout: int = field(default_factory=lambda: int(os.getenv("BIGBRAIN_CODE_TIMEOUT", "30")))
    temperature: float = field(default_factory=lambda: float(os.getenv("BIGBRAIN_TEMPERATURE", "0.7")))

    @property
    def has_api_key(self) -> bool:
        """Check if any LLM API key is configured (includes OAuth tokens)."""
        if (
            self.openai_api_key
            or self.anthropic_api_key
            or self.google_api_key
            or self.openrouter_api_key
            or self.mistral_api_key
            or self.kimi_api_key
        ):
            return True
        # Check for stored OAuth credentials
        try:
            from .auth.oauth import get_api_key
            return get_api_key() is not None
        except Exception:
            return False

    def resolve_anthropic_key(self) -> str | None:
        """Get Anthropic API key from env var OR OAuth token."""
        if self.anthropic_api_key:
            return self.anthropic_api_key
        try:
            from .auth.oauth import get_api_key
            return get_api_key()
        except Exception:
            return None

    @property
    def effective_front_model(self) -> str:
        """Model for the Front Brain (falls back to default)."""
        return self.front_brain_model or self.default_model

    @property
    def effective_code_model(self) -> str:
        """Model for code generation (falls back to default)."""
        return self.code_model or self.default_model

    @property
    def effective_planner_model(self) -> str:
        """Model for orchestrator task planning (falls back to front brain model)."""
        return self.planner_model or self.effective_front_model

    @property
    def effective_subagent_model(self) -> str:
        """Model for sub-brains / sub-agents (falls back to front brain model)."""
        return self.subagent_model or self.effective_front_model

    def summary(self) -> str:
        """Human-readable config summary (no secrets)."""
        provider = "mock"
        if self.openai_api_key:
            provider = "OpenAI"
        elif self.anthropic_api_key:
            provider = "Anthropic"
        elif self.google_api_key:
            provider = "Google"

        return (
            f"LLM: {provider} ({self.default_model}) | "
            f"Max tokens: {self.max_tokens} | "
            f"Code timeout: {self.code_timeout}s"
        )


# Singleton
config = BigBrainConfig()
