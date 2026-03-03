"""Natural language query engine — translate user questions into data queries.

Architecture:

1. ``generate_tools()`` reads the model registry and produces OpenAI-
   compatible function-calling schemas (zero-config for new models).
2. The user's natural-language question is sent to any OpenAI-compatible or
   Anthropic LLM together with the tool definitions.
3. The LLM returns a ``tool_calls`` response; we execute each call against
   the ``SmartRouter`` and return the results.

Supported LLM backends:
- OpenAI API  (``OPENAI_API_KEY``)
- Any OpenAI-compatible endpoint (``UNIFIN_LLM_BASE_URL`` + ``UNIFIN_LLM_API_KEY``)
- Anthropic Claude API (``ANTHROPIC_API_KEY``)

Backend is auto-detected or set via ``UNIFIN_LLM_PROVIDER``.

Usage::

    from unifin.nl.engine import NLEngine

    engine = NLEngine()            # reads env vars for LLM config
    df = engine.ask("苹果公司最近一年的股价走势")
    print(df)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from unifin.nl.llm import LLMClient

logger = logging.getLogger("unifin")


class NLEngine:
    """Translate natural language → unifin SDK queries via LLM tool-calling.

    The engine auto-discovers all registered models and presents them as
    callable tools to the LLM.  When a new model is registered, it is
    automatically available for NL queries — no code changes needed.
    """

    SYSTEM_PROMPT = (
        "You are a financial data assistant powered by the unifin platform. "
        "You have access to a set of data-query tools. Use them to answer "
        "the user's question. Each tool maps to a unifin data model.\n\n"
        "IMPORTANT RULES:\n"
        "- For Chinese A-share stocks, use MIC symbol format: 6-digit code + "
        "'.XSHE' (Shenzhen) or '.XSHG' (Shanghai). Example: 平安银行 → 000001.XSHE\n"
        "- For US stocks, use plain ticker: AAPL, MSFT, GOOGL\n"
        "- For Hong Kong stocks: 0700.XHKG\n"
        "- Dates must be ISO format: YYYY-MM-DD\n"
        "- Always call the most appropriate tool. If the user asks for "
        "historical prices, use query_equity_historical. For company info, "
        "use query_equity_profile. For financial statements, use the "
        "corresponding balance_sheet / income_statement / cash_flow tool.\n"
        "- If the user's question is ambiguous, make reasonable assumptions "
        "and proceed with the query.\n"
        "- After receiving tool results, provide a concise summary in the "
        "same language the user used."
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ):
        self._llm = LLMClient(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        self._tools: list[dict] | None = None  # lazy

    @property
    def tools(self) -> list[dict[str, Any]]:
        """Lazily generate tool definitions from the registry."""
        if self._tools is None:
            from unifin.nl.tools import generate_tools

            self._tools = generate_tools()
        return self._tools

    # ── public API ──

    def ask(
        self,
        question: str,
        *,
        provider: str | None = None,
        max_rounds: int = 3,
    ) -> dict[str, Any]:
        """Ask a natural-language question and return structured results.

        Args:
            question: Free-form user question (any language).
            provider: Force a specific data provider.
            max_rounds: Max LLM ↔ tool call rounds.

        Returns:
            Dict with keys:
            - ``answer``: LLM's textual summary
            - ``data``: list[dict] raw query results (last tool call)
            - ``tool_calls``: list of tool calls made
        """

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        all_tool_calls: list[dict[str, Any]] = []
        last_data: list[dict[str, Any]] = []

        for _round in range(max_rounds):
            response = self._chat_completion(messages)
            choice = response["choices"][0]
            message = choice["message"]

            # If the LLM wants to call tools
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                # LLM is done — return final answer
                return {
                    "answer": message.get("content", ""),
                    "data": last_data,
                    "tool_calls": all_tool_calls,
                }

            # Append assistant message (with tool_calls) to history
            messages.append(message)

            # Execute each tool call
            for tc in tool_calls:
                func = tc["function"]
                tool_name = func["name"]
                try:
                    args = json.loads(func["arguments"])
                except json.JSONDecodeError:
                    args = {}

                logger.info("NL tool call: %s(%s)", tool_name, args)
                all_tool_calls.append({"name": tool_name, "arguments": args})

                # Execute via router
                result = self._execute_tool(tool_name, args, provider=provider)
                last_data = result

                # Feed results back to LLM
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": self._truncate_result(result),
                    }
                )

        # Max rounds exhausted — return whatever we have
        return {
            "answer": "（达到最大查询轮次）",
            "data": last_data,
            "tool_calls": all_tool_calls,
        }

    # ── internals ──

    def _chat_completion(self, messages: list[dict]) -> dict[str, Any]:
        """Call the LLM via the unified LLMClient."""
        return self._llm.chat_completion(messages, tools=self.tools, tool_choice="auto")

    def _execute_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        provider: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a tool call via the SmartRouter."""
        from unifin.core.registry import model_registry
        from unifin.core.router import router
        from unifin.nl.tools import tool_name_to_model

        model_name = tool_name_to_model(tool_name)
        info = model_registry.get(model_name)

        # Build the query object from args
        query = info.query_type.model_validate(args)
        return router.query(model_name, query, provider=provider)

    @staticmethod
    def _truncate_result(data: list[dict], max_rows: int = 50) -> str:
        """Serialize results for LLM context, truncating if too large."""
        if not data:
            return "No data returned."

        total = len(data)
        truncated = data[:max_rows]
        text = json.dumps(truncated, ensure_ascii=False, default=str)

        if total > max_rows:
            text += f"\n... ({total - max_rows} more rows truncated)"

        return text
