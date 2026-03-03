"""Tests for the unified LLM client — OpenAI / Anthropic dual-backend."""

from __future__ import annotations

import json

from unifin.nl.llm import LLMClient, _detect_provider

# ──────────────────────────────────────────────
# 1. Provider detection
# ──────────────────────────────────────────────


class TestProviderDetection:
    def test_default_is_openai(self, monkeypatch):
        monkeypatch.delenv("UNIFIN_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert _detect_provider("sk-abc123", "") == "openai"

    def test_explicit_env_var(self, monkeypatch):
        monkeypatch.setenv("UNIFIN_LLM_PROVIDER", "anthropic")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert _detect_provider("", "") == "anthropic"

    def test_explicit_env_var_openai(self, monkeypatch):
        monkeypatch.setenv("UNIFIN_LLM_PROVIDER", "openai")
        assert _detect_provider("sk-ant-xxx", "") == "openai"

    def test_anthropic_api_key_env(self, monkeypatch):
        monkeypatch.delenv("UNIFIN_LLM_PROVIDER", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxx")
        assert _detect_provider("", "") == "anthropic"

    def test_anthropic_key_prefix(self, monkeypatch):
        monkeypatch.delenv("UNIFIN_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert _detect_provider("sk-ant-api03-xxx", "") == "anthropic"

    def test_anthropic_base_url(self, monkeypatch):
        monkeypatch.delenv("UNIFIN_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert _detect_provider("xxx", "https://api.anthropic.com") == "anthropic"


# ──────────────────────────────────────────────
# 2. Client initialization
# ──────────────────────────────────────────────


class TestLLMClientInit:
    def test_openai_defaults(self, monkeypatch):
        monkeypatch.delenv("UNIFIN_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("UNIFIN_LLM_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("UNIFIN_LLM_BASE_URL", raising=False)
        monkeypatch.delenv("UNIFIN_LLM_MODEL", raising=False)

        client = LLMClient(api_key="sk-test")
        assert client.provider == "openai"
        assert client._base_url == "https://api.openai.com/v1"
        assert client._model == "gpt-4o-mini"

    def test_anthropic_from_provider_param(self, monkeypatch):
        monkeypatch.delenv("UNIFIN_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("UNIFIN_LLM_MODEL", raising=False)

        client = LLMClient(provider="anthropic", api_key="sk-ant-test")
        assert client.provider == "anthropic"
        assert client._base_url == "https://api.anthropic.com"
        assert "claude" in client._model

    def test_custom_base_url(self, monkeypatch):
        monkeypatch.delenv("UNIFIN_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("UNIFIN_LLM_MODEL", raising=False)

        client = LLMClient(
            provider="openai",
            api_key="test",
            base_url="https://my-proxy.com/v1",
        )
        assert client._base_url == "https://my-proxy.com/v1"

    def test_has_api_key(self, monkeypatch):
        monkeypatch.delenv("UNIFIN_LLM_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        client = LLMClient(api_key="sk-test")
        assert client.has_api_key is True

        client2 = LLMClient(api_key="")
        assert client2.has_api_key is False


# ──────────────────────────────────────────────
# 3. Anthropic format converters
# ──────────────────────────────────────────────


class TestAnthropicConverters:
    def test_to_anthropic_messages_extracts_system(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        system, msgs = LLMClient._to_anthropic_messages(messages)
        assert system == "You are helpful."
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hello"

    def test_to_anthropic_messages_tool_result(self):
        messages = [
            {"role": "user", "content": "Get data"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "query_equity_historical",
                            "arguments": '{"symbol": "AAPL"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": '[{"date": "2024-01-01"}]',
            },
        ]
        system, msgs = LLMClient._to_anthropic_messages(messages)
        assert system == ""
        assert len(msgs) == 3

        # Assistant message → tool_use blocks
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"][0]["type"] == "tool_use"
        assert msgs[1]["content"][0]["name"] == "query_equity_historical"

        # Tool result → user with tool_result content
        assert msgs[2]["role"] == "user"
        assert msgs[2]["content"][0]["type"] == "tool_result"
        assert msgs[2]["content"][0]["tool_use_id"] == "call_1"

    def test_to_anthropic_tools(self):
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "query_equity_historical",
                    "description": "Get equity history",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                        },
                        "required": ["symbol"],
                    },
                },
            }
        ]
        result = LLMClient._to_anthropic_tools(openai_tools)
        assert len(result) == 1
        assert result[0]["name"] == "query_equity_historical"
        assert result[0]["description"] == "Get equity history"
        assert "properties" in result[0]["input_schema"]

    def test_from_anthropic_response_text_only(self):
        anthropic_resp = {
            "content": [{"type": "text", "text": "The answer is 42."}],
            "model": "claude-sonnet-4-20250514",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        result = LLMClient._from_anthropic_response(anthropic_resp)
        assert result["choices"][0]["message"]["content"] == "The answer is 42."
        assert "tool_calls" not in result["choices"][0]["message"]

    def test_from_anthropic_response_tool_use(self):
        anthropic_resp = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "query_equity_historical",
                    "input": {"symbol": "AAPL"},
                }
            ],
            "model": "claude-sonnet-4-20250514",
        }
        result = LLMClient._from_anthropic_response(anthropic_resp)
        msg = result["choices"][0]["message"]
        assert msg["content"] is None
        assert len(msg["tool_calls"]) == 1
        tc = msg["tool_calls"][0]
        assert tc["function"]["name"] == "query_equity_historical"
        assert json.loads(tc["function"]["arguments"]) == {"symbol": "AAPL"}

    def test_from_anthropic_response_mixed(self):
        anthropic_resp = {
            "content": [
                {"type": "text", "text": "Let me look that up."},
                {
                    "type": "tool_use",
                    "id": "toolu_456",
                    "name": "query_equity_search",
                    "input": {"query": "Apple"},
                },
            ],
            "model": "claude-sonnet-4-20250514",
        }
        result = LLMClient._from_anthropic_response(anthropic_resp)
        msg = result["choices"][0]["message"]
        assert msg["content"] == "Let me look that up."
        assert len(msg["tool_calls"]) == 1


# ──────────────────────────────────────────────
# 4. Existing engine/generator still work
# ──────────────────────────────────────────────


class TestEngineIntegration:
    def test_engine_creates_with_provider(self):
        from unifin.nl.engine import NLEngine

        engine = NLEngine(provider="anthropic", api_key="sk-ant-test")
        assert engine._llm.provider == "anthropic"

    def test_engine_creates_openai(self):
        from unifin.nl.engine import NLEngine

        engine = NLEngine(provider="openai", api_key="sk-test")
        assert engine._llm.provider == "openai"


class TestGeneratorIntegration:
    def test_generator_creates_with_provider(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator(provider="anthropic", api_key="sk-ant-test")
        assert gen._llm.provider == "anthropic"

    def test_generator_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("UNIFIN_LLM_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        assert gen._llm.has_api_key is False
        assert gen.has_llm is False

        # Must raise RuntimeError without API key
        import pytest

        with pytest.raises(RuntimeError, match="LLM API key is required"):
            gen.analyze_need("获取基金净值数据")
