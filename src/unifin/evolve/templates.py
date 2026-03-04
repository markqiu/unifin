"""Code templates for auto-generating model, fetcher, and test files.

These templates follow the exact conventions documented in AGENTS.md:
- Models: Query + Data + model_registry.register()
- Fetchers: Fetcher subclass + provider_registry.register_fetcher()
- Tests: pytest style, no unittest.TestCase
"""

from __future__ import annotations

from unifin.evolve.schema import DataNeed, FieldSpec, FieldType, SourceCandidate

# ---------------------------------------------------------------------------
# Type mapping helpers
# ---------------------------------------------------------------------------

_TYPE_TO_PYDANTIC: dict[FieldType, str] = {
    FieldType.STR: "str",
    FieldType.INT: "int",
    FieldType.FLOAT: "float",
    FieldType.BOOL: "bool",
    FieldType.DATE: "dt.date",
    FieldType.DATETIME: "dt.datetime",
}


def _field_type_str(f: FieldSpec) -> str:
    """Return the type annotation string for a field."""
    base = _TYPE_TO_PYDANTIC[f.type]
    if not f.required:
        return f"{base} | None"
    return base


def _field_default(f: FieldSpec) -> str:
    """Return the default value for a Field()."""
    if f.required:
        return "..."
    if f.default is not None:
        return f.default
    return "None"


def _needs_dt_import(fields: list[FieldSpec]) -> bool:
    """Check if any field requires datetime import."""
    return any(f.type in (FieldType.DATE, FieldType.DATETIME) for f in fields)


def _to_class_name(snake_name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in snake_name.split("_"))


# ---------------------------------------------------------------------------
# Model template
# ---------------------------------------------------------------------------


def generate_model_code(need: DataNeed) -> str:
    """Generate a complete model file following unifin conventions."""
    lines: list[str] = []

    lines.append(f'"""{need.description} — data model."""')
    lines.append("")

    if _needs_dt_import(need.query_fields + need.result_fields):
        lines.append("import datetime as dt")
        lines.append("")

    lines.append("from pydantic import BaseModel, Field")
    validators_needed = []
    if need.has_symbol:
        validators_needed.append("field_validator")
    if need.has_date_range:
        validators_needed.append("model_validator")
    if validators_needed:
        lines[-1] = f"from pydantic import BaseModel, Field, {', '.join(validators_needed)}"

    lines.append("")
    lines.append("from unifin.core.registry import ModelInfo, model_registry")
    if need.has_symbol:
        lines.append("from unifin.core.symbol import validate_symbol")
    lines.append("")
    lines.append("")

    # ── Query class ──
    query_name = _to_class_name(need.model_name) + "Query"
    lines.append(f"class {query_name}(BaseModel):")
    lines.append(f'    """Query parameters for {need.description.lower()}."""')
    lines.append("")

    for f in need.query_fields:
        type_str = _field_type_str(f)
        default = _field_default(f)
        lines.append(f"    {f.name}: {type_str} = Field(")
        lines.append(f"        default={default},")
        lines.append(f'        description="{f.description}",')
        lines.append("    )")

    if need.has_symbol:
        lines.append("")
        lines.append('    @field_validator("symbol")')
        lines.append("    @classmethod")
        lines.append("    def _check_symbol(cls, v: str) -> str:")
        lines.append("        return validate_symbol(v)")

    if need.has_date_range:
        lines.append("")
        lines.append('    @model_validator(mode="after")')
        lines.append(f'    def _validate_dates(self) -> "{query_name}":')
        lines.append("        if (self.start_date and self.end_date")
        lines.append("                and self.start_date > self.end_date):")
        lines.append("            from unifin.core.errors import InvalidDateRangeError")
        lines.append("")
        lines.append("            raise InvalidDateRangeError(self.start_date, self.end_date)")
        lines.append("        return self")

    lines.append("")
    lines.append("")

    # ── Data class ──
    data_name = _to_class_name(need.model_name) + "Data"
    lines.append(f"class {data_name}(BaseModel):")
    lines.append(f'    """Result schema for {need.description.lower()}."""')
    lines.append("")

    for f in need.result_fields:
        type_str = _field_type_str(f)
        default = _field_default(f)
        lines.append(f"    {f.name}: {type_str} = Field(")
        lines.append(f"        default={default},")
        lines.append(f'        description="{f.description}",')
        lines.append("    )")

    lines.append("")
    lines.append("")

    # ── Registration ──
    lines.append("# ── Register the model ──")
    lines.append("model_registry.register(")
    lines.append("    ModelInfo(")
    lines.append(f'        name="{need.model_name}",')
    lines.append(f'        category="{need.category}",')
    lines.append(f"        query_type={query_name},")
    lines.append(f"        result_type={data_name},")
    lines.append(f'        description="{need.description}",')
    lines.append("    )")
    lines.append(")")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fetcher template
# ---------------------------------------------------------------------------


def generate_fetcher_code(need: DataNeed, source: SourceCandidate) -> str:
    """Generate a complete fetcher file following unifin conventions."""
    lines: list[str] = []

    lines.append(f'"""{source.provider} fetcher for {need.model_name}.')
    lines.append("")
    lines.append(f"Source: {source.function_name}")
    lines.append(f"{source.description}")
    lines.append('"""')
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")
    if _needs_dt_import(need.query_fields + need.result_fields):
        lines.append("import datetime as dt")
    lines.append("from typing import Any, ClassVar")
    lines.append("")
    lines.append("from pydantic import BaseModel")
    lines.append("")
    lines.append("from unifin.core.fetcher import Fetcher")
    lines.append("from unifin.core.registry import provider_registry")
    lines.append("from unifin.core.types import Exchange")
    lines.append("")
    lines.append("")

    class_name = _to_class_name(source.provider) + _to_class_name(need.model_name) + "Fetcher"
    lines.append(f"class {class_name}(Fetcher):")
    lines.append(f'    """Fetch {need.description.lower()} from {source.provider}."""')
    lines.append("")
    lines.append(f'    provider_name: ClassVar[str] = "{source.provider}"')
    lines.append(f'    model_name: ClassVar[str] = "{need.model_name}"')

    exchanges_str = ", ".join(f"Exchange.{e}" for e in source.exchanges)
    lines.append(f"    supported_exchanges: ClassVar[list[Exchange]] = [{exchanges_str}]")
    lines.append("")

    result_field_names = [f.name for f in need.result_fields]
    lines.append(f"    supported_fields: ClassVar[list[str]] = {result_field_names}")
    lines.append('    data_delay: ClassVar[str] = "eod"')
    lines.append(f'    notes: ClassVar[str] = "{source.notes}"')
    lines.append("")

    # transform_query
    lines.append("    @staticmethod")
    lines.append("    def transform_query(query: BaseModel) -> dict[str, Any]:")
    if need.has_date_range:
        lines.append("        today = dt.date.today()")
        lines.append('        start = getattr(query, "start_date", None)')
        lines.append("        start = start or (today - dt.timedelta(days=365))")
        lines.append('        end = getattr(query, "end_date", None) or today')
        lines.append('        symbol = getattr(query, "symbol", "")')
        lines.append("")
        lines.append("        return {")
        lines.append('            "symbol": symbol,')
        lines.append('            "start_date": start.strftime("%Y%m%d"),')
        lines.append('            "end_date": end.strftime("%Y%m%d"),')
        lines.append("        }")
    else:
        lines.append('        symbol = getattr(query, "symbol", "")')
        lines.append('        return {"symbol": symbol}')
    lines.append("")

    # extract_data
    lines.append("    @staticmethod")
    lines.append("    def extract_data(")
    lines.append("        params: dict[str, Any],")
    lines.append("        credentials: dict[str, str] | None = None,")
    lines.append("    ) -> Any:")

    if source.provider == "akshare":
        lines.append("        try:")
        lines.append("            import akshare as ak")
        lines.append("        except ImportError:")
        lines.append(
            "            raise ImportError("
            "\"akshare is not installed. pip install 'unifin[akshare]'\""
            ")"
        )
        lines.append("")
        func_name = source.function_name.replace("ak.", "")
        lines.append("        try:")
        lines.append(f"            df = ak.{func_name}(")
        lines.append('                symbol=params["symbol"],')
        lines.append("            )")
        lines.append("            return df")
        lines.append("        except Exception:")
        lines.append("            return None")
    elif source.provider == "yfinance":
        lines.append("        try:")
        lines.append("            import yfinance as yf")
        lines.append("        except ImportError:")
        lines.append(
            "            raise ImportError("
            "\"yfinance is not installed. pip install 'unifin[yfinance]'\""
            ")"
        )
        lines.append("")
        lines.append('        ticker = yf.Ticker(params["symbol"])')
        lines.append("        try:")
        lines.append(f"            data = ticker.{source.function_name}")
        lines.append("            return data")
        lines.append("        except Exception:")
        lines.append("            return None")
    else:
        lines.append("        # TODO: Implement data extraction for this provider")
        lines.append("        raise NotImplementedError")
    lines.append("")

    # transform_data
    lines.append("    @staticmethod")
    lines.append("    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:")
    lines.append("        if raw_data is None or (hasattr(raw_data, 'empty') and raw_data.empty):")
    lines.append("            return []")
    lines.append("")
    lines.append(f"        col_map = {repr(source.column_mapping)}")
    lines.append("")
    lines.append('        records = raw_data.to_dict(orient="records")')
    lines.append("        results = []")
    lines.append("        for row in records:")
    lines.append("            mapped = {}")
    lines.append("            for src_col, dst_col in col_map.items():")
    lines.append("                if src_col in row:")
    lines.append("                    mapped[dst_col] = row[src_col]")
    for f in need.result_fields:
        if not f.required:
            lines.append(f'            mapped.setdefault("{f.name}", None)')
    lines.append("            results.append(mapped)")
    lines.append("")
    lines.append("        return results")
    lines.append("")
    lines.append("")
    lines.append(f"provider_registry.register_fetcher({class_name})")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Test template
# ---------------------------------------------------------------------------


def generate_test_code(need: DataNeed, sources: list[SourceCandidate]) -> str:
    """Generate a test file for the new model and fetchers."""
    lines: list[str] = []

    lines.append(f'"""Tests for {need.model_name} model and fetchers."""')
    lines.append("")
    lines.append("from unifin.core.registry import model_registry, provider_registry")
    lines.append("")
    lines.append("")

    lines.append(f"class TestModel{_to_class_name(need.model_name)}:")
    lines.append(f'    """Tests for {need.model_name} model registration."""')
    lines.append("")
    lines.append("    def test_model_registered(self):")
    lines.append(f'        assert "{need.model_name}" in model_registry')
    lines.append("")
    lines.append("    def test_model_info(self):")
    lines.append(f'        info = model_registry.get("{need.model_name}")')
    lines.append(f'        assert info.name == "{need.model_name}"')
    lines.append(f'        assert info.category == "{need.category}"')
    lines.append("")
    lines.append("    def test_query_fields(self):")
    lines.append(f'        info = model_registry.get("{need.model_name}")')
    lines.append("        fields = info.query_type.model_fields")
    for f in need.query_fields:
        lines.append(f'        assert "{f.name}" in fields')
    lines.append("")
    lines.append("    def test_result_fields(self):")
    lines.append(f'        info = model_registry.get("{need.model_name}")')
    lines.append("        fields = info.result_type.model_fields")
    for f in need.result_fields:
        lines.append(f'        assert "{f.name}" in fields')
    lines.append("")

    for source in sources:
        cls = f"TestFetcher{_to_class_name(source.provider)}{_to_class_name(need.model_name)}"
        lines.append("")
        lines.append(f"class {cls}:")
        lines.append(f'    """Tests for {source.provider} fetcher of {need.model_name}."""')
        lines.append("")
        lines.append("    def test_fetcher_registered(self):")
        get_f = f'provider_registry.get_fetcher("{need.model_name}", "{source.provider}")'
        lines.append(f"        fetcher = {get_f}")
        lines.append("        assert fetcher is not None")
        lines.append(f'        assert fetcher.model_name == "{need.model_name}"')
        lines.append(f'        assert fetcher.provider_name == "{source.provider}"')
        lines.append("")
        lines.append("    def test_supported_exchanges(self):")
        lines.append(f"        fetcher = {get_f}")
        lines.append("        assert len(fetcher.supported_exchanges) > 0")
        lines.append("")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SDK function template
# ---------------------------------------------------------------------------


def generate_sdk_function(need: DataNeed) -> str:
    """Generate a SDK function to add to the appropriate namespace."""
    func_name = need.model_name.split("_", 1)[-1] if "_" in need.model_name else need.model_name

    lines: list[str] = []
    lines.append(f"def {func_name}(")

    for f in need.query_fields:
        if f.required:
            lines.append(f"    {f.name}: str,")
        else:
            type_hint = (
                f"{_TYPE_TO_PYDANTIC[f.type]} | None" if f.type != FieldType.STR else "str | None"
            )
            lines.append(f"    {f.name}: {type_hint} = None,")

    lines.append("    *,")
    lines.append("    provider: str | None = None,")
    lines.append(") -> pl.DataFrame:")
    lines.append(f'    """{need.description}."""')
    lines.append(f'    return _query("{need.model_name}", locals(), provider=provider)')
    lines.append("")

    return "\n".join(lines)
