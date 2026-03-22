"""Abstract LLM Provider interface."""

import asyncio
from abc import ABC, abstractmethod
from typing import AsyncIterator, Union


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    Provides a unified interface for different LLM backends (OpenAI, Anthropic, local models, etc).
    Supports both streaming and non-streaming responses.
    """
    
    @abstractmethod
    async def complete(
        self, 
        prompt: str, 
        model: str = "default", 
        stream: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> Union[str, AsyncIterator[str]]:
        """
        Generate a completion for the given prompt.
        
        Args:
            prompt: Input prompt text
            model: Model name/identifier
            stream: Whether to stream the response
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-2.0)
            **kwargs: Additional provider-specific parameters
            
        Returns:
            If stream=False: Complete response as string
            If stream=True: AsyncIterator yielding token chunks
        """
        pass
    
    @abstractmethod
    async def chat_complete(
        self,
        messages: list[dict],
        model: str = "default",
        stream: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> Union[str, AsyncIterator[str]]:
        """
        Generate a chat completion for the given messages.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name/identifier
            stream: Whether to stream the response
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-2.0)
            **kwargs: Additional provider-specific parameters
            
        Returns:
            If stream=False: Complete response as string
            If stream=True: AsyncIterator yielding token chunks
        """
        pass
    
    @abstractmethod
    def get_available_models(self) -> list[str]:
        """
        Get list of available models for this provider.
        
        Returns:
            List of model names/identifiers
        """
        pass
    
    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for given text.
        
        Args:
            text: Text to estimate
            
        Returns:
            Estimated token count
        """
        pass