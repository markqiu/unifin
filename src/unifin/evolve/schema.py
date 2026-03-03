"""Data structures for the self-evolution pipeline."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Stage enum — tracks the Issue-driven workflow progress
# ---------------------------------------------------------------------------


class Stage(str, Enum):
    """Stages in the Issue-driven self-evolution workflow."""

    ANALYZING = "analyzing"  # Parsing issue → DataNeed
    DISCOVERED = "discovered"  # Found data sources
    AWAITING_APPROVAL = "awaiting_approval"  # Posted findings, waiting for user
    GENERATING = "generating"  # Generating code
    TESTING = "testing"  # Running generated tests
    PR_CREATED = "pr_created"  # PR has been created
    COMPLETED = "completed"  # All done, issue closed
    FAILED = "failed"  # Something went wrong


# ---------------------------------------------------------------------------
# Field / Source / Need definitions
# ---------------------------------------------------------------------------


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
    column_mapping: dict[str, str] = field(default_factory=dict)
    exchanges: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class DataNeed:
    """Fully analyzed data need, ready for code generation."""

    model_name: str  # e.g. "fund_nav"
    category: str  # e.g. "fund.price"
    description: str  # e.g. "Open-end fund NAV data"
    query_fields: list[FieldSpec] = field(default_factory=list)
    result_fields: list[FieldSpec] = field(default_factory=list)
    has_symbol: bool = True
    has_date_range: bool = True
    is_time_series: bool = True


@dataclass
class GeneratedFile:
    """A file to be written to disk."""

    path: str  # Relative to project root
    content: str  # Full file content
    description: str  # Human-readable description


@dataclass
class EvolvePlan:
    """Complete plan for adding a new data capability."""

    need: DataNeed
    sources: list[SourceCandidate]
    files: list[GeneratedFile] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: dt.datetime.now().isoformat())
    stage: Stage = Stage.ANALYZING
    issue_number: int | None = None  # GitHub Issue number
    branch_name: str | None = None  # Git branch for the PR
    error: str | None = None  # Error message if failed

    @property
    def model_name(self) -> str:
        return self.need.model_name

    def summary(self) -> str:
        """Human-readable plan summary in Markdown."""
        lines = [
            f"## 📊 数据模型: `{self.need.model_name}`",
            f"- **分类**: `{self.need.category}`",
            f"- **描述**: {self.need.description}",
            f"- **阶段**: {self.stage.value}",
            "",
            "### 查询字段 (Query)",
            "| 字段 | 类型 | 必填 | 说明 |",
            "|------|------|------|------|",
        ]
        for f in self.need.query_fields:
            req = "✅" if f.required else "❌"
            lines.append(f"| `{f.name}` | `{f.type.value}` | {req} | {f.description} |")

        lines.append("")
        lines.append("### 返回字段 (Data)")
        lines.append("| 字段 | 类型 | 必填 | 说明 |")
        lines.append("|------|------|------|------|")
        for f in self.need.result_fields:
            req = "✅" if f.required else "❌"
            lines.append(f"| `{f.name}` | `{f.type.value}` | {req} | {f.description} |")

        lines.append("")
        lines.append("### 数据源")
        if self.sources:
            for s in self.sources:
                lines.append(f"- **{s.provider}**: `{s.function_name}`")
                lines.append(f"  > {s.description}")
                if s.exchanges:
                    lines.append(f"  > 交易所: {', '.join(s.exchanges)}")
        else:
            lines.append("- ⚠️ 未找到匹配的数据源")

        if self.files:
            lines.append("")
            lines.append("### 将要生成的文件")
            for f in self.files:
                lines.append(f"- `{f.path}` — {f.description}")

        return "\n".join(lines)
