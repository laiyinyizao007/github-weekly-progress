"""LLM client for generating responses."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from openai import OpenAI

from src.config import LLMConfig


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate a response from the LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated response
        """
        pass

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Chat completion with message history.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated response
        """
        pass


class OpenAIClient(LLMClient):
    """OpenAI API client."""

    def __init__(self, config: LLMConfig):
        """Initialize OpenAI client.

        Args:
            config: LLM configuration
        """
        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required")

        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate using OpenAI API."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        return self.chat(messages, temperature, max_tokens)

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Chat completion using OpenAI API."""
        kwargs = {
            "model": self.config.openai_model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""


class AnthropicClient(LLMClient):
    """Anthropic Claude API client."""

    def __init__(self, config: LLMConfig):
        """Initialize Anthropic client.

        Args:
            config: LLM configuration
        """
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "anthropic package is required for Claude. "
                "Install with: pip install anthropic"
            )

        if not config.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")

        self.config = config

        # Support custom base URL (e.g., for Kimi API)
        client_kwargs = {"api_key": config.anthropic_api_key}
        if config.anthropic_base_url:
            client_kwargs["base_url"] = config.anthropic_base_url

        self.client = Anthropic(**client_kwargs)

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate using Anthropic API."""
        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self.config.anthropic_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = self.client.messages.create(**kwargs)
        return response.content[0].text if response.content else ""

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Chat completion using Anthropic API."""
        # Extract system prompt if present
        system_prompt = None
        chat_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                chat_messages.append(msg)

        kwargs = {
            "model": self.config.anthropic_model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = self.client.messages.create(**kwargs)
        return response.content[0].text if response.content else ""


class KimiClient(LLMClient):
    """Kimi API client using Anthropic SDK format."""

    def __init__(self, config: LLMConfig):
        """Initialize Kimi client.

        Args:
            config: LLM configuration
        """
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "anthropic package is required for Kimi. "
                "Install with: pip install anthropic"
            )

        if not config.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for Kimi")

        self.config = config
        self.model = config.anthropic_model or "kimi-for-coding"

        # Kimi uses Anthropic-compatible API (not OpenAI)
        base_url = config.anthropic_base_url or "https://api.kimi.com/coding"
        # Remove /v1 suffix if present (Kimi doesn't use it)
        base_url = base_url.rstrip("/").replace("/v1", "")

        self.client = Anthropic(
            api_key=config.anthropic_api_key,
            base_url=base_url,
        )

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate using Kimi API."""
        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = self.client.messages.create(**kwargs)
        return response.content[0].text if response.content else ""

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Chat completion using Kimi API."""
        # Extract system prompt if present
        system_prompt = None
        chat_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                chat_messages.append(msg)

        kwargs = {
            "model": self.model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = self.client.messages.create(**kwargs)
        return response.content[0].text if response.content else ""


def create_llm_client(config: LLMConfig) -> LLMClient:
    """Factory function to create appropriate LLM client.

    Args:
        config: LLM configuration

    Returns:
        LLMClient instance
    """
    if config.provider == "openai":
        return OpenAIClient(config)
    elif config.provider == "anthropic":
        # Check if using Kimi (has custom base URL with kimi or local address)
        if config.anthropic_base_url and (
            "kimi" in config.anthropic_base_url.lower()
            or "192.168." in config.anthropic_base_url
            or "localhost" in config.anthropic_base_url
            or "127.0." in config.anthropic_base_url
        ):
            return KimiClient(config)
        return AnthropicClient(config)
    elif config.provider == "kimi":
        return KimiClient(config)
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")
