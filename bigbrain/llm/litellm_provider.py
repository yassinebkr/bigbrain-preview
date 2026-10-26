"""Real LLM Provider using litellm — supports OpenAI, Anthropic, Google, and 100+ models."""

import asyncio
import json
from typing import AsyncIterator, Union

from .provider import LLMProvider


class LiteLLMProvider(LLMProvider):
    """
    Production LLM provider using litellm for unified multi-provider access.

    Supports any model litellm supports:
      - "gpt-4o", "gpt-4o-mini" (OpenAI)
      - "claude-sonnet-4-20250514", "claude-opus-4-20250514" (Anthropic)
      - "gemini/gemini-2.0-flash" (Google)
      - And 100+ more: https://docs.litellm.ai/docs/providers

    API keys are read from environment variables automatically by litellm:
      OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, etc.
    """

    def __init__(self, default_model: str = "gpt-4o-mini"):
        """
        Initialize litellm provider.

        Args:
            default_model: Default model to use (litellm format)
        """
        try:
            import litellm
            self._litellm = litellm
            # Suppress litellm's verbose logging
            litellm.suppress_debug_info = True
            litellm.set_verbose = False
        except ImportError:
            raise ImportError(
                "litellm is required for real LLM access.\n"
                "Install it: pip install litellm"
            )

        self.default_model = default_model

    async def complete(
        self,
        prompt: str,
        model: str = None,
        stream: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs,
    ) -> Union[str, AsyncIterator[str]]:
        """Generate completion for a prompt."""
        messages = [{"role": "user", "content": prompt}]
        return await self.chat_complete(
            messages=messages,
            model=model,
            stream=stream,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    async def chat_complete(
        self,
        messages: list[dict],
        model: str = None,
        stream: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs,
    ) -> Union[str, AsyncIterator[str]]:
        """Generate chat completion."""
        model = model or self.default_model

        tool_schema = kwargs.pop("tool_schema", None)
        if tool_schema:
            if stream:
                raise ValueError("Single-action decisions require non-streaming completion")
            kwargs.update(tools=[{"type":"function","function":tool_schema}],
                          tool_choice={"type":"function","function":{"name":tool_schema["name"]}},
                          parallel_tool_calls=False)

        if stream:
            return self._stream_chat(messages, model, max_tokens, temperature, **kwargs)
        else:
            response = await self._litellm.acompletion(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False,
                **kwargs,
            )
            if tool_schema:
                choice = response.choices[0]
                calls = choice.message.tool_calls or []
                if choice.finish_reason == "length" or len(calls) != 1 or calls[0].function.name != tool_schema["name"]:
                    raise ValueError("Provider must return exactly the requested complete decision")
                arguments = calls[0].function.arguments
                if not isinstance(json.loads(arguments), dict):
                    raise ValueError("Decision arguments must be a JSON object")
                return arguments
            return response.choices[0].message.content

    async def _stream_chat(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream chat completion tokens."""
        response = await self._litellm.acompletion(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            **kwargs,
        )

        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    def get_available_models(self) -> list[str]:
        """Get commonly used models."""
        return [
            "gpt-4o",
            "gpt-4o-mini",
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "gemini/gemini-2.0-flash",
            "gemini/gemini-2.5-pro",
        ]

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count."""
        try:
            from litellm import token_counter
            return token_counter(model=self.default_model, text=text)
        except Exception:
            return max(1, len(text) // 4)
