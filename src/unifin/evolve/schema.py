"""Data structures for the self-evolution pipeline."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum


class FieldType(str, Enum):
    """Supported field types for auto-generated models."""

    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    DATE = "dt.date"
    DATETIME = "dt.datetime"


@dataclass
class FieldSpec:
    """Specification of a single field in a data model."""

    name: str
    type: FieldType
    required: bool = True
    description: str = ""
    default: str | None = None  # Python literal as string, e.g. "None"


@dataclass
class SourceCandidate:
    """A potential data source found by the Discoverer."""

    provider: str  # e.g. "akshare"
    function_name: str  # e.g. "ak.fund_open_fund_daily_em"
    description: str  # Human-readable description
    sample_columns: list[str] = field(default_factory=list)
    column_mapping: dict[str, str] = field(default_factory=dict)  # provider → unified
    exchanges: list[str] = field(default_factory=list)  # e.g. ["XSHG", "XSHE"]
    notes: str = ""


@dataclass
class DataNeed:
    """Fully analyzed data need, ready for code generation."""

    model_name: str  # e.g. "fund_nav"
    category: str  # e.g. "fund.price"
    description: str  # e.g. "Open-end fund NAV data"
    query_fields: list[FieldSpec] = field(default_factory=list)
    result_fields: list[FieldSpec] = field(default_factory=list)
    has_symbol: bool = True  # Whether the query has a symbol field
    has_date_range: bool = True  # Whether the query has start_date/end_date
    is_time_series: bool = True  # Whether results are time-ordered


@dataclass
class GeneratedFile:
    """A file to be written to disk."""

    path: str  # Relative to project root, e.g. "src/unifin/models/fund_nav.py"
    content: str  # Full file content
    description: str  # Human-readable description


@dataclass
class EvolvePlan:
    """Complete plan for adding a new data capability."""

    need: DataNeed
    sources: list[SourceCandidate]
    files: list[GeneratedFile] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: dt.datetime.now().isoformat())
    status: str = "draft"  # draft → confirmed → executed → failed

    @property
    def model_name(self) -> str:
        return self.need.model_name

    def summary(self) -> str:
        """Human-readable plan summary."""
        lines = [
            f"## 数据模型: {self.need.model_name}",
            f"- 分类: {self.need.category}",
            f"- 描述: {self.need.description}",
            "",
            "### 查询字段",
        ]
        for f in self.need.query_fields:
            req = "必填" if f.required else "可选"
            lines.append(f"- `{f.name}`: {f.type.value} ({req}) — {f.description}")

        lines.append("")
        lines.append("### 返回字段")
        for f in self.need.result_fields:
            req = "必填" if f.required else "可选"
            lines.append(f"- `{f.name}`: {f.type.value} ({req}) — {f.description}")

        lines.append("")
        lines.append("### 数据源")
        for s in self.sources:
            lines.append(f"- **{s.provider}**: `{s.function_name}`")
            lines.append(f"  {s.description}")

        lines.append("")
        lines.append("### 生成文件")
        for f in self.files:
            lines.append(f"- `{f.path}` — {f.description}")

        return "\n".join(lines)
