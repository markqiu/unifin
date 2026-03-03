"""Unified LLM client — supports OpenAI and Anthropic APIs.

Provides a single ``LLMClient`` that auto-detects the backend from environment
variables and normalizes both request and response formats.

Backend selection (in priority order):

1. Explicit ``provider`` parameter: ``"openai"`` or ``"anthropic"``
2. ``UNIFIN_LLM_PROVIDER`` env var
3. Auto-detect from ``UNIFIN_LLM_API_KEY`` / ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``
4. Fallback: OpenAI-compatible

Environment variables:

    # Common
    UNIFIN_LLM_PROVIDER     "openai" | "anthropic"  (optional, auto-detected)
    UNIFIN_LLM_MODEL        Model name (default varies by provider)

    # OpenAI / OpenAI-compatible
    UNIFIN_LLM_API_KEY      API key (falls back to OPENAI_API_KEY)
    UNIFIN_LLM_BASE_URL     Base URL (default: https://api.openai.com/v1)

    # Anthropic
    ANTHROPIC_API_KEY        Anthropic API key (falls back to UNIFIN_LLM_API_KEY)
    ANTHROPIC_BASE_URL       Base URL (default: https://api.anthropic.com)

Usage::

    from unifin.nl.llm import llm_client

    # Simple text completion
    text = llm_client.chat("You are helpful.", "What is 1+1?")

    # With tool calling (OpenAI function-calling format in, normalized out)
    response = llm_client.chat_completion(messages, tools=tools)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger("unifin")

# Anthropic API version header
_ANTHROPIC_VERSION = "2023-06-01"

# Default models per provider
_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-20250514",
}


def _detect_provider(api_key: str, base_url: str) -> str:
    """Auto-detect LLM provider from env or key patterns."""
    explicit = os.environ.get("UNIFIN_LLM_PROVIDER", "").lower()
    if explicit in ("openai", "anthropic"):
        return explicit

    # Check if anthropic-specific env var is set
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"

    # Heuristic: Anthropic keys start with "sk-ant-"
    if api_key.startswith("sk-ant-"):
        return "anthropic"

    # Heuristic: base URL contains "anthropic"
    if "anthropic" in base_url.lower():
        return "anthropic"

    return "openai"


class LLMClient:
    """Unified LLM client supporting OpenAI and Anthropic backends.

    Both backends expose the same public interface: ``chat()`` for simple
    text completion and ``chat_completion()`` for tool-calling workflows.
    Responses are normalized to OpenAI format internally.
    """

    def __init__(
        self,
        *,
        provider: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        # Resolve API key
        self._api_key = (
            api_key
            or os.environ.get("UNIFIN_LLM_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        )

        # Detect provider
        raw_base = base_url or os.environ.get("UNIFIN_LLM_BASE_URL") or ""
        self.provider = provider or _detect_provider(self._api_key, raw_base)

        # Resolve base URL (provider-specific defaults)
        if raw_base:
            self._base_url = raw_base
        elif self.provider == "anthropic":
            self._base_url = os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
        else:
            self._base_url = "https://api.openai.com/v1"

        # Resolve model
        self._model = (
            model
            or os.environ.get("UNIFIN_LLM_MODEL")
            or _DEFAULT_MODELS.get(self.provider, "gpt-4o-mini")
        )

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    # ── Public API ──

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.1,
    ) -> str:
        """Simple text completion — returns the assistant's text response."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        response = self.chat_completion(messages, temperature=temperature)
        return response["choices"][0]["message"]["content"]

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = "auto",
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Full chat completion — returns normalized OpenAI-format response.

        Regardless of backend, the returned dict always has the structure::

            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "...",          # may be None when tool_calls present
                        "tool_calls": [...]         # optional
                    }
                }]
            }
        """
        if self.provider == "anthropic":
            return self._anthropic_completion(
                messages, tools=tools, tool_choice=tool_choice, temperature=temperature
            )
        return self._openai_completion(
            messages, tools=tools, tool_choice=tool_choice, temperature=temperature
        )

    # ── OpenAI backend ──

    def _openai_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        import httpx

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
            if tool_choice:
                body["tool_choice"] = tool_choice
        if temperature is not None:
            body["temperature"] = temperature

        url = f"{self._base_url.rstrip('/')}/chat/completions"
        resp = httpx.post(url, json=body, headers=headers, timeout=60.0)
        resp.raise_for_status()
        return resp.json()

    # ── Anthropic backend ──

    def _anthropic_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Call Anthropic Messages API, return OpenAI-normalized response."""
        import httpx

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
        }

        # Convert messages: extract system, adapt tool results
        system_text, anthropic_messages = self._to_anthropic_messages(messages)

        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": anthropic_messages,
        }
        if system_text:
            body["system"] = system_text
        if tools:
            body["tools"] = self._to_anthropic_tools(tools)
            if tool_choice and tool_choice != "auto":
                body["tool_choice"] = {"type": tool_choice}
            else:
                body["tool_choice"] = {"type": "auto"}
        if temperature is not None:
            body["temperature"] = temperature

        url = f"{self._base_url.rstrip('/')}/v1/messages"
        resp = httpx.post(url, json=body, headers=headers, timeout=60.0)
        resp.raise_for_status()

        return self._from_anthropic_response(resp.json())

    # ── Anthropic format converters ──

    @staticmethod
    def _to_anthropic_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Convert OpenAI messages to Anthropic format.

        Returns (system_text, anthropic_messages).
        """
        system_text = ""
        anthropic_msgs: list[dict[str, Any]] = []

        for msg in messages:
            role = msg["role"]

            if role == "system":
                system_text = msg["content"]
                continue

            if role == "tool":
                # Anthropic: tool results are "user" messages with tool_result content
                anthropic_msgs.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.get("tool_call_id", ""),
                                "content": msg.get("content", ""),
                            }
                        ],
                    }
                )
                continue

            if role == "assistant" and "tool_calls" in msg:
                # Convert OpenAI tool_calls to Anthropic tool_use content blocks
                content_blocks: list[dict[str, Any]] = []
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                for tc in msg["tool_calls"]:
                    args = tc["function"]["arguments"]
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "input": args,
                        }
                    )
                anthropic_msgs.append({"role": "assistant", "content": content_blocks})
                continue

            # Regular user/assistant message
            anthropic_msgs.append({"role": role, "content": msg.get("content", "")})

        return system_text, anthropic_msgs

    @staticmethod
    def _to_anthropic_tools(openai_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI function-calling tools to Anthropic tool format."""
        anthropic_tools: list[dict[str, Any]] = []
        for tool in openai_tools:
            if tool.get("type") == "function":
                func = tool["function"]
                anthropic_tools.append(
                    {
                        "name": func["name"],
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {"type": "object"}),
                    }
                )
            else:
                # Already in Anthropic format or unknown — pass through
                anthropic_tools.append(tool)
        return anthropic_tools

    @staticmethod
    def _from_anthropic_response(resp: dict[str, Any]) -> dict[str, Any]:
        """Normalize Anthropic response to OpenAI chat completion format."""
        content_blocks = resp.get("content", [])

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for block in content_blocks:
            if block["type"] == "text":
                text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(block["input"], ensure_ascii=False),
                        },
                    }
                )

        message: dict[str, Any] = {
            "role": "assistant",
            "content": "\n".join(text_parts) if text_parts else None,
        }
        if tool_calls:
            message["tool_calls"] = tool_calls

        return {
            "choices": [{"message": message}],
            "model": resp.get("model", ""),
            "usage": resp.get("usage", {}),
        }


def create_llm_client(**kwargs: Any) -> LLMClient:
    """Factory function — create an LLMClient with env-based defaults."""
    return LLMClient(**kwargs)


# Global singleton (lazy — reads env at first use)
llm_client = LLMClient()
