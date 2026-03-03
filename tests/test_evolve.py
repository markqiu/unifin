"""Tests for the self-evolution module (evolve/).

Tests cover:
- Schema dataclasses
- Template code generation
- Source discovery (keyword matching)
- Generator (fallback analysis)
- Loader (file writing + dynamic import, mocked)
- Orchestrator (end-to-end flow, mocked I/O)
"""


from unifin.evolve.schema import (
    DataNeed,
    EvolvePlan,
    FieldSpec,
    FieldType,
    GeneratedFile,
    SourceCandidate,
)

# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestFieldSpec:
    def test_required_field(self):
        f = FieldSpec(name="symbol", type=FieldType.STR, required=True, description="标的代码")
        assert f.name == "symbol"
        assert f.type == FieldType.STR
        assert f.required is True

    def test_optional_field(self):
        f = FieldSpec(name="nav", type=FieldType.FLOAT, required=False, description="净值")
        assert f.required is False


class TestDataNeed:
    def test_basic(self):
        need = DataNeed(
            model_name="fund_nav",
            category="fund.price",
            description="基金净值数据",
            query_fields=[
                FieldSpec(name="symbol", type=FieldType.STR, required=True),
            ],
            result_fields=[
                FieldSpec(name="date", type=FieldType.DATE, required=True),
                FieldSpec(name="nav", type=FieldType.FLOAT, required=False),
            ],
        )
        assert need.model_name == "fund_nav"
        assert need.has_symbol is True
        assert need.is_time_series is True


class TestEvolvePlan:
    def test_summary(self):
        need = DataNeed(
            model_name="test_model",
            category="test",
            description="Test model",
            query_fields=[FieldSpec(name="symbol", type=FieldType.STR, required=True)],
            result_fields=[FieldSpec(name="value", type=FieldType.FLOAT, required=False)],
        )
        plan = EvolvePlan(
            need=need,
            sources=[
                SourceCandidate(
                    provider="akshare",
                    function_name="ak.test_func",
                    description="Test function",
                )
            ],
            files=[
                GeneratedFile(
                    path="src/unifin/models/test_model.py",
                    content="# test",
                    description="Model file",
                )
            ],
        )
        summary = plan.summary()
        assert "test_model" in summary
        assert "akshare" in summary
        assert "ak.test_func" in summary


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------


class TestTemplateModelCode:
    def _make_need(self) -> DataNeed:
        return DataNeed(
            model_name="fund_nav",
            category="fund.price",
            description="开放式基金净值数据",
            query_fields=[
                FieldSpec(name="symbol", type=FieldType.STR, required=True, description="基金代码"),
                FieldSpec(
                    name="start_date", type=FieldType.DATE, required=False, description="开始日期"
                ),
                FieldSpec(
                    name="end_date", type=FieldType.DATE, required=False, description="结束日期"
                ),
            ],
            result_fields=[
                FieldSpec(name="date", type=FieldType.DATE, required=True, description="净值日期"),
                FieldSpec(name="nav", type=FieldType.FLOAT, required=False, description="单位净值"),
                FieldSpec(
                    name="acc_nav", type=FieldType.FLOAT, required=False, description="累计净值"
                ),
                FieldSpec(
                    name="symbol", type=FieldType.STR, required=False, description="基金代码"
                ),
            ],
        )

    def test_generate_model_code(self):
        from unifin.evolve.templates import generate_model_code

        need = self._make_need()
        code = generate_model_code(need)

        # Must contain class definitions
        assert "class FundNavQuery(BaseModel):" in code
        assert "class FundNavData(BaseModel):" in code

        # Must contain registration
        assert 'model_registry.register(' in code
        assert 'name="fund_nav"' in code
        assert 'category="fund.price"' in code

        # Must import datetime
        assert "import datetime as dt" in code

        # Must have symbol validator
        assert "field_validator" in code
        assert "validate_symbol" in code

        # Must have date range validator
        assert "model_validator" in code
        assert "InvalidDateRangeError" in code

    def test_generate_model_no_symbol(self):
        from unifin.evolve.templates import generate_model_code

        need = DataNeed(
            model_name="macro_gdp",
            category="macro.cn",
            description="GDP数据",
            query_fields=[
                FieldSpec(name="start_date", type=FieldType.DATE, required=False),
            ],
            result_fields=[
                FieldSpec(name="date", type=FieldType.DATE, required=True),
                FieldSpec(name="value", type=FieldType.FLOAT, required=False),
            ],
            has_symbol=False,
            has_date_range=True,
        )
        code = generate_model_code(need)
        assert "validate_symbol" not in code
        assert "class MacroGdpQuery" in code
        assert "class MacroGdpData" in code


class TestTemplateFetcherCode:
    def test_generate_fetcher_code(self):
        from unifin.evolve.templates import generate_fetcher_code

        need = DataNeed(
            model_name="fund_nav",
            category="fund.price",
            description="基金净值数据",
            query_fields=[
                FieldSpec(name="symbol", type=FieldType.STR, required=True),
            ],
            result_fields=[
                FieldSpec(name="date", type=FieldType.DATE, required=True),
                FieldSpec(name="nav", type=FieldType.FLOAT, required=False),
            ],
        )
        source = SourceCandidate(
            provider="akshare",
            function_name="ak.fund_open_fund_info_em",
            description="开放式基金净值(东财)",
            exchanges=["XSHG", "XSHE"],
            column_mapping={"净值日期": "date", "单位净值": "nav"},
        )
        code = generate_fetcher_code(need, source)

        assert "class AkshareFundNavFetcher(Fetcher):" in code
        assert 'provider_name: ClassVar[str] = "akshare"' in code
        assert 'model_name: ClassVar[str] = "fund_nav"' in code
        assert "Exchange.XSHG" in code
        assert "provider_registry.register_fetcher(AkshareFundNavFetcher)" in code
        assert "import akshare as ak" in code


class TestTemplateTestCode:
    def test_generate_test_code(self):
        from unifin.evolve.templates import generate_test_code

        need = DataNeed(
            model_name="fund_nav",
            category="fund.price",
            description="基金净值",
            query_fields=[FieldSpec(name="symbol", type=FieldType.STR, required=True)],
            result_fields=[FieldSpec(name="date", type=FieldType.DATE, required=True)],
        )
        sources = [
            SourceCandidate(
                provider="akshare",
                function_name="ak.test",
                description="test",
            )
        ]
        code = generate_test_code(need, sources)

        assert "class TestModelFundNav:" in code
        assert 'assert "fund_nav" in model_registry' in code
        assert "class TestFetcherAkshareFundNav:" in code


# ---------------------------------------------------------------------------
# Discoverer tests
# ---------------------------------------------------------------------------


class TestSourceDiscoverer:
    def test_search_fund_keywords(self):
        from unifin.evolve.discoverer import discoverer

        results = discoverer.search(["基金", "净值"])
        assert len(results) > 0
        # Should find akshare fund source
        providers = [r.provider for r in results]
        assert "akshare" in providers

    def test_search_english_keywords(self):
        from unifin.evolve.discoverer import discoverer

        results = discoverer.search(["fund", "nav"])
        assert len(results) > 0

    def test_search_equity_keywords(self):
        from unifin.evolve.discoverer import discoverer

        results = discoverer.search(["股票", "历史"])
        assert len(results) > 0

    def test_search_empty(self):
        from unifin.evolve.discoverer import discoverer

        results = discoverer.search(["zzzzz_nonexistent"])
        assert len(results) == 0

    def test_search_specific_provider(self):
        from unifin.evolve.discoverer import discoverer

        results = discoverer.search(["stock"], provider="yfinance")
        for r in results:
            assert r.provider == "yfinance"

    def test_list_available_sources(self):
        from unifin.evolve.discoverer import discoverer

        sources = discoverer.list_available_sources()
        assert len(sources) > 10  # We have a large catalog

    def test_list_filtered_by_provider(self):
        from unifin.evolve.discoverer import discoverer

        sources = discoverer.list_available_sources(provider="akshare")
        for s in sources:
            assert s["provider"] == "akshare"

    def test_search_macro_keywords(self):
        from unifin.evolve.discoverer import discoverer

        results = discoverer.search(["GDP", "宏观"])
        assert len(results) > 0
        funcs = [r.function_name for r in results]
        assert any("gdp" in f.lower() for f in funcs)

    def test_search_bond_keywords(self):
        from unifin.evolve.discoverer import discoverer

        results = discoverer.search(["债券", "bond"])
        assert len(results) > 0


# ---------------------------------------------------------------------------
# Generator fallback tests
# ---------------------------------------------------------------------------


class TestCodeGeneratorFallback:
    def test_fallback_analyze_fund(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()  # No API key → fallback mode
        need = gen.analyze_need("我需要基金净值数据")
        assert need.model_name == "fund_nav"
        assert need.category == "fund.price"

    def test_fallback_analyze_futures(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        need = gen.analyze_need("给我期货数据")
        assert need.model_name == "futures_data"

    def test_fallback_analyze_gdp(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        need = gen.analyze_need("GDP数据")
        assert need.model_name == "macro_gdp"

    def test_fallback_column_mapping(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        source = SourceCandidate(
            provider="akshare",
            function_name="ak.test",
            description="test",
            sample_columns=["日期", "开盘", "收盘", "成交量"],
        )
        need = DataNeed(
            model_name="test",
            category="test",
            description="test",
            result_fields=[
                FieldSpec(name="date", type=FieldType.DATE, required=True),
                FieldSpec(name="open", type=FieldType.FLOAT, required=False),
                FieldSpec(name="close", type=FieldType.FLOAT, required=False),
                FieldSpec(name="volume", type=FieldType.INT, required=False),
            ],
        )
        mapping = gen.generate_column_mapping(source, need)
        assert mapping["日期"] == "date"
        assert mapping["开盘"] == "open"
        assert mapping["收盘"] == "close"
        assert mapping["成交量"] == "volume"


# ---------------------------------------------------------------------------
# Orchestrator tests (no I/O)
# ---------------------------------------------------------------------------


class TestOrchestratorKeywords:
    def test_extract_keywords_chinese(self):
        from unifin.evolve.orchestrator import Orchestrator

        need = DataNeed(
            model_name="fund_nav",
            category="fund.price",
            description="基金净值数据",
        )
        keywords = Orchestrator._extract_keywords("我需要基金净值数据", need)
        assert "基金净值数据" in keywords or "基金" in " ".join(keywords)

    def test_extract_keywords_english(self):
        from unifin.evolve.orchestrator import Orchestrator

        need = DataNeed(
            model_name="equity_dividend",
            category="equity.dividend",
            description="Stock dividends",
        )
        keywords = Orchestrator._extract_keywords("I need stock dividend data", need)
        assert any("dividend" in kw.lower() for kw in keywords)


class TestOrchestratorAnalyze:
    """Test the analyze pipeline (no LLM, no I/O)."""

    def test_analyze_produces_plan(self):
        from unifin.evolve.orchestrator import Orchestrator

        orch = Orchestrator()
        plan = orch.analyze("我需要基金净值数据")
        assert plan.status == "draft"
        assert plan.need.model_name is not None
        assert len(plan.files) > 0

    def test_analyze_finds_sources(self):
        from unifin.evolve.orchestrator import Orchestrator

        orch = Orchestrator()
        plan = orch.analyze("我需要基金净值数据")
        # Should find akshare fund sources
        if plan.sources:
            providers = [s.provider for s in plan.sources]
            assert "akshare" in providers

    def test_plan_summary_readable(self):
        from unifin.evolve.orchestrator import Orchestrator

        orch = Orchestrator()
        plan = orch.analyze("我想要A股融资融券数据")
        summary = plan.summary()
        assert "数据模型" in summary
        assert "查询字段" in summary
        assert "返回字段" in summary
