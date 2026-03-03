"""LLM-powered code generator — translates DataNeed into working unifin code.

Uses the LLM (OpenAI or Anthropic, auto-detected) to:
1. Understand the user's data need and map it to a model schema.
2. Determine column mappings from provider APIs to unified fields.
3. Generate model + fetcher + test code following project conventions.

Falls back to template-based generation when the LLM is unavailable.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from unifin.evolve.schema import (
    DataNeed,
    EvolvePlan,
    FieldSpec,
    FieldType,
    GeneratedFile,
    SourceCandidate,
)
from unifin.evolve.templates import (
    generate_fetcher_code,
    generate_model_code,
    generate_test_code,
)

logger = logging.getLogger("unifin")


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

_ANALYZE_SYSTEM_PROMPT = """\
You are a financial data model architect for the unifin platform.
Given a user's data need (in any language), output a JSON object describing \
the data model schema.

RULES:
- model_name: snake_case, e.g. "fund_nav", "margin_trading"
- category: dot-separated, e.g. "fund.price", "equity.fundamental", \
  "macro.cn", "index.price"
- field types: "str", "int", "float", "bool", "dt.date", "dt.datetime"
- All result (Data) fields except the primary key should be optional (required=false)
- If the data has a symbol, include it as the first query field (required)
- If the data is time-series, include start_date and end_date as optional query fields
- Description should be concise and in the same language as the user's input

Output ONLY valid JSON with this structure:
{
  "model_name": "fund_nav",
  "category": "fund.price",
  "description": "开放式基金净值数据",
  "has_symbol": true,
  "has_date_range": true,
  "is_time_series": true,
  "query_fields": [
    {"name": "symbol", "type": "str", "required": true, "description": "基金代码"},
    {"name": "start_date", "type": "dt.date", "required": false, "description": "开始日期"},
    {"name": "end_date", "type": "dt.date", "required": false, "description": "结束日期"}
  ],
  "result_fields": [
    {"name": "date", "type": "dt.date", "required": true, "description": "净值日期"},
    {"name": "nav", "type": "float", "required": false, "description": "单位净值"},
    {"name": "acc_nav", "type": "float", "required": false, "description": "累计净值"},
    {"name": "daily_return", "type": "float", "required": false, "description": "日收益率"},
    {"name": "symbol", "type": "str", "required": false, "description": "基金代码"}
  ]
}
"""

_COLUMN_MAPPING_PROMPT = """\
You are mapping columns from a data source API to a unified data model.

Source API: {function_name} ({provider})
Source columns: {source_columns}

Target model fields: {target_fields}

Output a JSON object mapping source column names to target field names.
Only include columns that have a clear mapping. Example:
{{"净值日期": "date", "单位净值": "nav", "累计净值": "acc_nav"}}

Output ONLY the JSON object, no explanation.
"""


class CodeGenerator:
    """Generate unifin model + fetcher code, optionally with LLM assistance."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ):
        from unifin.nl.llm import LLMClient

        self._llm = LLMClient(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    # ── Public API ──

    def analyze_need(self, user_request: str) -> DataNeed:
        """Use LLM to analyze a user's data request into a DataNeed."""
        if self._llm.has_api_key:
            try:
                return self._llm_analyze(user_request)
            except Exception as e:
                logger.warning("LLM analysis failed: %s. Falling back to template.", e)

        return self._fallback_analyze(user_request)

    def generate_column_mapping(self, source: SourceCandidate, need: DataNeed) -> dict[str, str]:
        """Use LLM to generate column mapping from source to unified model."""
        if self._llm.has_api_key:
            try:
                return self._llm_column_mapping(source, need)
            except Exception as e:
                logger.warning("LLM column mapping failed: %s. Falling back.", e)

        return self._fallback_column_mapping(source, need)

    def generate_plan(self, need: DataNeed, sources: list[SourceCandidate]) -> EvolvePlan:
        """Generate a complete EvolvePlan with all files to be created."""
        # Deduplicate: only keep one source per provider
        seen_providers: set[str] = set()
        unique_sources: list[SourceCandidate] = []
        for source in sources:
            if source.provider not in seen_providers:
                seen_providers.add(source.provider)
                unique_sources.append(source)
        sources = unique_sources

        # Enrich sources with column mappings
        for source in sources:
            if not source.column_mapping:
                source.column_mapping = self.generate_column_mapping(source, need)

        files: list[GeneratedFile] = []

        # 1. Model file
        model_code = generate_model_code(need)
        files.append(
            GeneratedFile(
                path=f"src/unifin/models/{need.model_name}.py",
                content=model_code,
                description=f"数据模型: {need.model_name}",
            )
        )

        # 2. Fetcher files (one per source)
        for source in sources:
            fetcher_code = generate_fetcher_code(need, source)
            files.append(
                GeneratedFile(
                    path=f"src/unifin/providers/{source.provider}/{need.model_name}.py",
                    content=fetcher_code,
                    description=f"数据源: {source.provider}/{need.model_name}",
                )
            )

        # 3. Test file
        test_code = generate_test_code(need, sources)
        files.append(
            GeneratedFile(
                path=f"tests/test_evolve_{need.model_name}.py",
                content=test_code,
                description=f"测试: {need.model_name}",
            )
        )

        return EvolvePlan(need=need, sources=sources, files=files)

    # ── LLM helpers ──

    def _llm_analyze(self, user_request: str) -> DataNeed:
        result = self._llm.chat(system=_ANALYZE_SYSTEM_PROMPT, user=user_request)
        data = self._extract_json(result)
        return self._json_to_data_need(data)

    def _llm_column_mapping(self, source: SourceCandidate, need: DataNeed) -> dict[str, str]:
        target_fields = [f.name for f in need.result_fields]
        prompt = _COLUMN_MAPPING_PROMPT.format(
            function_name=source.function_name,
            provider=source.provider,
            source_columns=source.sample_columns,
            target_fields=target_fields,
        )
        result = self._llm.chat(system="You are a data mapping assistant.", user=prompt)
        return self._extract_json(result)

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text_lines = text.split("\n")
            if text_lines[0].startswith("```"):
                text_lines = text_lines[1:]
            if text_lines and text_lines[-1].strip() == "```":
                text_lines = text_lines[:-1]
            text = "\n".join(text_lines)
        return json.loads(text)

    @staticmethod
    def _json_to_data_need(data: dict[str, Any]) -> DataNeed:
        query_fields = [
            FieldSpec(
                name=f["name"],
                type=FieldType(f["type"]),
                required=f.get("required", True),
                description=f.get("description", ""),
            )
            for f in data.get("query_fields", [])
        ]
        result_fields = [
            FieldSpec(
                name=f["name"],
                type=FieldType(f["type"]),
                required=f.get("required", False),
                description=f.get("description", ""),
            )
            for f in data.get("result_fields", [])
        ]
        return DataNeed(
            model_name=data["model_name"],
            category=data.get("category", "misc"),
            description=data.get("description", ""),
            query_fields=query_fields,
            result_fields=result_fields,
            has_symbol=data.get("has_symbol", True),
            has_date_range=data.get("has_date_range", True),
            is_time_series=data.get("is_time_series", True),
        )

    # ── Fallback (no LLM) ──

    @staticmethod
    def _fallback_analyze(user_request: str) -> DataNeed:
        """Simple keyword-based analysis when no LLM is available."""
        request_lower = user_request.lower()

        model_name = "custom_data"
        category = "misc"

        keyword_map = [
            (["基金", "净值"], "fund_nav", "fund.price"),
            (["fund", "nav"], "fund_nav", "fund.price"),
            (["基金", "持仓"], "fund_holdings", "fund.holdings"),
            (["fund", "holdings"], "fund_holdings", "fund.holdings"),
            (["融资", "融券"], "margin_trading", "equity.margin"),
            (["margin", "trading"], "margin_trading", "equity.margin"),
            (["基金"], "fund_data", "fund"),
            (["fund"], "fund_data", "fund"),
            (["净值"], "fund_nav", "fund.price"),
            (["期货"], "futures_data", "futures.price"),
            (["futures"], "futures_data", "futures.price"),
            (["债券"], "bond_data", "bond.price"),
            (["bond"], "bond_data", "bond.price"),
            (["汇率"], "forex_data", "forex"),
            (["forex"], "forex_data", "forex"),
            (["宏观"], "macro_data", "macro"),
            (["macro"], "macro_data", "macro"),
            (["GDP"], "macro_gdp", "macro.cn"),
            (["CPI"], "macro_cpi", "macro.cn"),
            (["龙虎榜"], "top_list", "equity.flow"),
            (["分红"], "dividend", "equity.dividend"),
            (["dividend"], "dividend", "equity.dividend"),
        ]

        for keywords, name, cat in keyword_map:
            if all(kw in request_lower or kw.lower() in request_lower for kw in keywords):
                model_name = name
                category = cat
                break

        query_fields = [
            FieldSpec(
                name="symbol",
                type=FieldType.STR,
                required=True,
                description="标的代码",
            ),
            FieldSpec(
                name="start_date",
                type=FieldType.DATE,
                required=False,
                description="开始日期",
            ),
            FieldSpec(
                name="end_date",
                type=FieldType.DATE,
                required=False,
                description="结束日期",
            ),
        ]
        result_fields = [
            FieldSpec(name="date", type=FieldType.DATE, required=True, description="日期"),
            FieldSpec(name="value", type=FieldType.FLOAT, required=False, description="数值"),
            FieldSpec(name="symbol", type=FieldType.STR, required=False, description="标的代码"),
        ]

        return DataNeed(
            model_name=model_name,
            category=category,
            description=user_request[:80],
            query_fields=query_fields,
            result_fields=result_fields,
        )

    @staticmethod
    def _fallback_column_mapping(source: SourceCandidate, need: DataNeed) -> dict[str, str]:
        """Fuzzy name matching for column mapping."""
        mapping: dict[str, str] = {}
        target_names = {f.name for f in need.result_fields}

        common_mappings = {
            "日期": "date",
            "净值日期": "date",
            "date": "date",
            "开盘": "open",
            "open": "open",
            "收盘": "close",
            "close": "close",
            "最高": "high",
            "high": "high",
            "最低": "low",
            "low": "low",
            "成交量": "volume",
            "volume": "volume",
            "成交额": "amount",
            "amount": "amount",
            "单位净值": "nav",
            "累计净值": "acc_nav",
            "日增长率": "daily_return",
            "涨跌幅": "change_pct",
            "换手率": "turnover_rate",
            "振幅": "amplitude",
            "代码": "symbol",
            "名称": "name",
        }

        for src_col in source.sample_columns:
            if src_col in common_mappings:
                target = common_mappings[src_col]
                if target in target_names:
                    mapping[src_col] = target

        return mapping

    @staticmethod
    def _extract_keywords(user_request: str, need: DataNeed) -> list[str]:
        """Extract search keywords from the user request and analyzed need."""
        keywords: list[str] = []

        keywords.extend(need.model_name.split("_"))
        keywords.extend(need.description.split()[:5])

        cn_words = re.findall(r"[\u4e00-\u9fff]+", user_request)
        keywords.extend(cn_words)

        en_words = re.findall(r"[a-zA-Z]{2,}", user_request)
        keywords.extend(en_words)

        generic = {"数据", "需要", "获取", "查询", "想", "我", "data", "get", "want"}
        seen: set[str] = set()
        unique: list[str] = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen and kw_lower not in generic and len(kw) > 1:
                seen.add(kw_lower)
                unique.append(kw)

        return unique
