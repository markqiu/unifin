"""LLM-powered code generator — translates DataNeed into working unifin code.

Uses the LLM (OpenAI or Anthropic, auto-detected) to:
1. Understand the user's data need and map it to a model schema.
2. Determine column mappings from provider APIs to unified fields.
3. Generate model + fetcher + test code following project conventions.

Requires a configured LLM API key (UNIFIN_LLM_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY).
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

_CODE_REVIEW_PROMPT = """\
You are a senior Python engineer reviewing code for the unifin financial data platform.

Project conventions:
- All data models use Pydantic BaseModel with Query + Data classes
- Date fields use `import datetime as dt` then `dt.date` (NEVER `from datetime import date`)
- All Data fields except primary key are `Optional[T] = None`
- Fetchers inherit `unifin.core.fetcher.Fetcher` and implement TET
  (transform_query, extract_data, transform_data)
- Fetchers return `list[dict]`, never polars DataFrames
- Symbols use ISO 10383 MIC format (e.g. `000001.XSHE`)
- Errors use structured `UnifinError` hierarchy, never bare `Exception`/`ValueError`
- Tests use pytest (not unittest.TestCase)

Review the following diff and provide:
1. **Summary**: What does this PR do? (1-2 sentences)
2. **Issues** (if any): Bugs, convention violations, security concerns
3. **Suggestions** (if any): Improvements, missing tests, edge cases
4. **Verdict**: One of APPROVE / REQUEST_CHANGES / COMMENT

Format your response as Markdown. Be concise but thorough.
If the code follows all conventions and has no issues, give APPROVE.
If there are minor style nits only, give COMMENT with suggestions.
If there are bugs or convention violations, give REQUEST_CHANGES.
"""

_CODE_FIX_PROMPT = """\
You are a senior Python engineer fixing code for the unifin financial data platform.

Project conventions:
- All data models use Pydantic BaseModel with Query + Data classes
- Date fields use `import datetime as dt` then `dt.date`
  (NEVER `from datetime import date`)
- All Data fields except primary key are `Optional[T] = None`
- Fetchers inherit `unifin.core.fetcher.Fetcher` and implement TET
  (transform_query, extract_data, transform_data)
- Fetchers return `list[dict]`, never polars DataFrames
- Symbols use ISO 10383 MIC format (e.g. `000001.XSHE`)
- Errors use structured `UnifinError` hierarchy, never bare ValueError
- Tests use pytest (not unittest.TestCase)
- Ruff lint: line-length=100, rules E/F/I/N/W/UP

You will receive:
1. A code review with issues and suggestions
2. The current content of files that need fixing

For EACH file that needs changes, output a JSON object with this structure:
```json
{
  "files": [
    {
      "path": "src/unifin/providers/akshare/fund_nav.py",
      "content": "<full corrected file content>"
    }
  ],
  "summary": "Brief description of fixes applied"
}
```

RULES:
- Output ONLY valid JSON, no explanation outside the JSON.
- Include the COMPLETE file content, not just changed lines.
- Fix ALL issues mentioned in the review.
- Also fix any lint issues (line length, import order, etc).
- Do NOT add new features — only fix the reported issues.
- Preserve existing functionality that works correctly.
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

    @property
    def has_llm(self) -> bool:
        """Whether an LLM API key is configured."""
        return self._llm.has_api_key

    def analyze_need(self, user_request: str) -> DataNeed:
        """Use LLM to analyze a user's data request into a DataNeed.

        Raises RuntimeError if no LLM API key is configured.
        """
        if not self._llm.has_api_key:
            raise RuntimeError(
                "LLM API key is required for analyze_need(). "
                "Set UNIFIN_LLM_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY."
            )
        return self._llm_analyze(user_request)

    def generate_column_mapping(self, source: SourceCandidate, need: DataNeed) -> dict[str, str]:
        """Use LLM to generate column mapping from source to unified model.

        Raises RuntimeError if no LLM API key is configured.
        """
        if not self._llm.has_api_key:
            raise RuntimeError(
                "LLM API key is required for generate_column_mapping(). "
                "Set UNIFIN_LLM_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY."
            )
        return self._llm_column_mapping(source, need)

    def review_code(self, diff: str, file_summaries: list[str] | None = None) -> dict[str, str]:
        """Use LLM to review a code diff.

        Returns a dict with keys: summary, issues, suggestions, verdict, review_body.
        Raises RuntimeError if no LLM API key is configured.
        """
        if not self._llm.has_api_key:
            raise RuntimeError(
                "LLM API key is required for review_code(). "
                "Set UNIFIN_LLM_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY."
            )
        return self._llm_review(diff, file_summaries)

    def fix_code(
        self,
        review_body: str,
        file_contents: dict[str, str],
    ) -> dict[str, Any]:
        """Use LLM to fix code based on review feedback.

        Parameters
        ----------
        review_body : str
            The review comment body (Markdown) with issues/suggestions.
        file_contents : dict[str, str]
            Mapping of file path → current file content.

        Returns
        -------
        dict with keys: files (list of {path, content}), summary (str).
        Raises RuntimeError if no LLM API key is configured.
        """
        if not self._llm.has_api_key:
            raise RuntimeError(
                "LLM API key is required for fix_code(). "
                "Set UNIFIN_LLM_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY."
            )
        return self._llm_fix(review_body, file_contents)

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

    def _llm_review(
        self,
        diff: str,
        file_summaries: list[str] | None = None,
    ) -> dict[str, str]:
        """Use LLM to review a code diff."""
        user_msg_parts = []
        if file_summaries:
            files_md = "\n".join(f"- {f}" for f in file_summaries)
            user_msg_parts.append(f"### Changed files\n{files_md}")
        # Truncate diff to ~12k chars to stay within context limits
        truncated = diff[:12000]
        if len(diff) > 12000:
            truncated += "\n\n... (diff truncated)"
        user_msg_parts.append(f"### Diff\n```diff\n{truncated}\n```")

        user_msg = "\n\n".join(user_msg_parts)
        result = self._llm.chat(system=_CODE_REVIEW_PROMPT, user=user_msg)

        # Parse verdict from response
        verdict = "COMMENT"
        result_upper = result.upper()
        if "APPROVE" in result_upper and "REQUEST_CHANGES" not in result_upper:
            verdict = "APPROVE"
        elif "REQUEST_CHANGES" in result_upper:
            verdict = "REQUEST_CHANGES"

        return {
            "review_body": result,
            "verdict": verdict,
        }

    def _llm_fix(
        self,
        review_body: str,
        file_contents: dict[str, str],
    ) -> dict[str, Any]:
        """Use LLM to generate fixed file contents."""
        user_parts = ["### Review feedback\n", review_body, "\n\n### Files to fix\n"]
        for path, content in file_contents.items():
            # Truncate very large files
            truncated = content[:8000]
            if len(content) > 8000:
                truncated += "\n# ... (truncated)"
            user_parts.append(f"#### `{path}`\n```python\n{truncated}\n```\n")

        user_msg = "\n".join(user_parts)
        result = self._llm.chat(system=_CODE_FIX_PROMPT, user=user_msg)
        return self._extract_json(result)
