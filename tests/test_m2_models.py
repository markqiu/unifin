"""Tests for all M2 models — models, registry, and yfinance integration."""

import pytest
from datetime import date


# ──────────────────────────────────────────────
# 1. Model registration tests
# ──────────────────────────────────────────────

class TestModelRegistration:
    """Verify all 10 models are registered."""

    def test_all_models_registered(self):
        from unifin.core.registry import model_registry

        expected = [
            "equity_historical", "equity_search", "equity_profile",
            "equity_quote", "balance_sheet", "income_statement",
            "cash_flow", "index_historical", "etf_search", "trade_calendar",
        ]
        registered = model_registry.list_models()
        for name in expected:
            assert name in registered, f"Model '{name}' not registered"

    def test_model_category_mapping(self):
        from unifin.core.registry import model_registry

        assert model_registry.get("equity_historical").category == "equity.price"
        assert model_registry.get("equity_search").category == "equity"
        assert model_registry.get("equity_profile").category == "equity"
        assert model_registry.get("equity_quote").category == "equity.price"
        assert model_registry.get("balance_sheet").category == "equity.fundamental"
        assert model_registry.get("income_statement").category == "equity.fundamental"
        assert model_registry.get("cash_flow").category == "equity.fundamental"
        assert model_registry.get("index_historical").category == "index"
        assert model_registry.get("etf_search").category == "etf"
        assert model_registry.get("trade_calendar").category == "market"


# ──────────────────────────────────────────────
# 2. Fetcher registration tests
# ──────────────────────────────────────────────

class TestFetcherRegistration:
    """Verify yfinance fetchers are registered for supported models."""

    def test_yfinance_fetchers(self):
        from unifin.core.registry import provider_registry

        yf_models = [
            "equity_historical", "equity_search", "equity_profile",
            "equity_quote", "balance_sheet", "income_statement",
            "cash_flow", "index_historical", "etf_search", "trade_calendar",
        ]
        for model_name in yf_models:
            providers = list(provider_registry.get_providers_for_model(model_name).keys())
            assert "yfinance" in providers, f"yfinance not registered for '{model_name}'"

    def test_akshare_fetchers(self):
        from unifin.core.registry import provider_registry

        ak_models = [
            "equity_historical", "equity_search", "equity_quote",
            "etf_search", "trade_calendar",
        ]
        for model_name in ak_models:
            providers = list(provider_registry.get_providers_for_model(model_name).keys())
            assert "akshare" in providers, f"akshare not registered for '{model_name}'"


# ──────────────────────────────────────────────
# 3. Pydantic model validation tests
# ──────────────────────────────────────────────

class TestEquitySearchModel:
    def test_query_defaults(self):
        from unifin.models.equity_search import EquitySearchQuery

        q = EquitySearchQuery()
        assert q.query == ""
        assert q.is_symbol is False
        assert q.limit is None

    def test_data_fields(self):
        from unifin.models.equity_search import EquitySearchData

        d = EquitySearchData(symbol="AAPL", name="Apple Inc.")
        assert d.symbol == "AAPL"
        assert d.name == "Apple Inc."
        assert d.exchange is None


class TestEquityProfileModel:
    def test_query_required_symbol(self):
        from unifin.models.equity_profile import EquityProfileQuery

        q = EquityProfileQuery(symbol="AAPL")
        assert q.symbol == "AAPL"

    def test_data_fields(self):
        from unifin.models.equity_profile import EquityProfileData

        d = EquityProfileData(
            symbol="AAPL", name="Apple Inc.", sector="Technology",
            market_cap=3_000_000_000_000.0,
        )
        assert d.market_cap == 3_000_000_000_000.0
        assert d.ceo is None


class TestEquityQuoteModel:
    def test_data_fields(self):
        from unifin.models.equity_quote import EquityQuoteData

        d = EquityQuoteData(
            symbol="AAPL", last_price=185.5, volume=50000000,
            change=2.3, change_percent=0.0125,
        )
        assert d.last_price == 185.5
        assert d.change_percent == 0.0125


class TestBalanceSheetModel:
    def test_query_defaults(self):
        from unifin.models.balance_sheet import BalanceSheetQuery

        q = BalanceSheetQuery(symbol="AAPL")
        assert q.period == "annual"
        assert q.limit == 5

    def test_data_fields(self):
        from unifin.models.balance_sheet import BalanceSheetData

        d = BalanceSheetData(
            period_ending=date(2024, 9, 30),
            total_assets=352_583_000_000.0,
            total_liabilities=308_030_000_000.0,
        )
        assert d.period_ending == date(2024, 9, 30)
        assert d.total_assets == 352_583_000_000.0
        assert d.cash_and_equivalents is None


class TestIncomeStatementModel:
    def test_data_fields(self):
        from unifin.models.income_statement import IncomeStatementData

        d = IncomeStatementData(
            period_ending=date(2024, 9, 30),
            total_revenue=391_035_000_000.0,
            net_income=93_736_000_000.0,
            basic_eps=6.08,
        )
        assert d.total_revenue == 391_035_000_000.0
        assert d.basic_eps == 6.08


class TestCashFlowModel:
    def test_data_fields(self):
        from unifin.models.cash_flow import CashFlowData

        d = CashFlowData(
            period_ending=date(2024, 9, 30),
            net_cash_from_operations=118_254_000_000.0,
            capital_expenditure=-9_959_000_000.0,
            free_cash_flow=108_295_000_000.0,
        )
        assert d.free_cash_flow == 108_295_000_000.0


class TestIndexHistoricalModel:
    def test_query_defaults(self):
        from unifin.models.index_historical import IndexHistoricalQuery

        q = IndexHistoricalQuery(symbol="^GSPC")
        assert q.start_date is None
        assert q.end_date is None

    def test_data_fields(self):
        from unifin.models.index_historical import IndexHistoricalData

        d = IndexHistoricalData(
            date=date(2024, 1, 2),
            open=4742.0, high=4793.0, low=4740.0, close=4770.0,
            volume=3_200_000_000,
        )
        assert d.close == 4770.0


class TestEtfSearchModel:
    def test_data_fields(self):
        from unifin.models.etf_search import EtfSearchData

        d = EtfSearchData(symbol="510300", name="华泰柏瑞沪深300ETF")
        assert d.symbol == "510300"


class TestTradeCalendarModel:
    def test_query_defaults(self):
        from unifin.models.trade_calendar import TradeCalendarQuery

        q = TradeCalendarQuery()
        assert q.market == "cn"

    def test_data_fields(self):
        from unifin.models.trade_calendar import TradeCalendarData

        d = TradeCalendarData(date=date(2024, 1, 2), is_open=True, market="cn")
        assert d.is_open is True


# ──────────────────────────────────────────────
# 4. SDK function existence tests
# ──────────────────────────────────────────────

class TestSDKNamespaces:
    def test_equity_functions(self):
        import unifin

        assert callable(unifin.equity.historical)
        assert callable(unifin.equity.search)
        assert callable(unifin.equity.profile)
        assert callable(unifin.equity.quote)
        assert callable(unifin.equity.balance_sheet)
        assert callable(unifin.equity.income_statement)
        assert callable(unifin.equity.cash_flow)

    def test_index_functions(self):
        import unifin

        assert callable(unifin.index.historical)

    def test_etf_functions(self):
        import unifin

        assert callable(unifin.etf.search)

    def test_market_functions(self):
        import unifin

        assert callable(unifin.market.trade_calendar)


# ──────────────────────────────────────────────
# 5. End-to-end integration tests (yfinance)
# ──────────────────────────────────────────────

def _yfinance_available() -> bool:
    try:
        import yfinance  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _yfinance_available(), reason="yfinance not installed")
class TestEndToEndYFinance:
    """Integration tests that fetch real data via yfinance."""

    def test_equity_search(self):
        import unifin

        df = unifin.equity.search("Apple")
        assert len(df) > 0
        assert "symbol" in df.columns
        assert "name" in df.columns
        print(f"\n  equity.search('Apple') → {len(df)} results")
        print(df.head(3))

    def test_equity_profile(self):
        import unifin

        df = unifin.equity.profile("AAPL")
        assert len(df) == 1
        assert "symbol" in df.columns
        assert "sector" in df.columns
        row = df.to_dicts()[0]
        assert row["symbol"] == "AAPL"
        print(f"\n  equity.profile('AAPL'): sector={row.get('sector')}, mktcap={row.get('market_cap')}")

    def test_equity_quote(self):
        import unifin

        df = unifin.equity.quote("AAPL")
        assert len(df) == 1
        row = df.to_dicts()[0]
        assert row["symbol"] == "AAPL"
        assert row.get("last_price") is not None or row.get("close") is not None
        print(f"\n  equity.quote('AAPL'): price={row.get('last_price')}")

    def test_balance_sheet(self):
        import unifin

        df = unifin.equity.balance_sheet("AAPL")
        assert len(df) > 0
        assert "period_ending" in df.columns
        assert "total_assets" in df.columns
        print(f"\n  equity.balance_sheet('AAPL') → {len(df)} periods")
        print(df.select("period_ending", "total_assets", "total_liabilities").head())

    def test_income_statement(self):
        import unifin

        df = unifin.equity.income_statement("AAPL")
        assert len(df) > 0
        assert "total_revenue" in df.columns
        assert "net_income" in df.columns
        print(f"\n  equity.income_statement('AAPL') → {len(df)} periods")
        print(df.select("period_ending", "total_revenue", "net_income").head())

    def test_cash_flow(self):
        import unifin

        df = unifin.equity.cash_flow("AAPL")
        assert len(df) > 0
        assert "net_cash_from_operations" in df.columns
        print(f"\n  equity.cash_flow('AAPL') → {len(df)} periods")
        print(df.select("period_ending", "net_cash_from_operations", "free_cash_flow").head())

    def test_index_historical(self):
        import unifin

        df = unifin.index.historical("^GSPC", start_date="2024-01-02", end_date="2024-01-10")
        assert len(df) > 0
        assert "close" in df.columns
        print(f"\n  index.historical('^GSPC') → {len(df)} rows")
        print(df.head())

    def test_quarterly_balance_sheet(self):
        import unifin

        df = unifin.equity.balance_sheet("AAPL", period="quarter", limit=2)
        assert len(df) > 0
        assert len(df) <= 2
        print(f"\n  quarterly balance_sheet → {len(df)} periods")


# ──────────────────────────────────────────────
# 7. Strict typing & validation tests
# ──────────────────────────────────────────────


class TestStrictTyping:
    """Verify strict type checking for Query models."""

    def test_period_enum_rejects_invalid(self):
        """period='monthly' should be rejected."""
        from pydantic import ValidationError
        from unifin.models.balance_sheet import BalanceSheetQuery

        with pytest.raises(ValidationError):
            BalanceSheetQuery(symbol="AAPL", period="monthly")

    def test_period_enum_accepts_valid(self):
        from unifin.models.balance_sheet import BalanceSheetQuery
        from unifin.core.types import Period

        q = BalanceSheetQuery(symbol="AAPL", period="quarter")
        assert q.period == Period.QUARTER

        q2 = BalanceSheetQuery(symbol="AAPL", period=Period.ANNUAL)
        assert q2.period == Period.ANNUAL

    def test_market_enum_rejects_invalid(self):
        from pydantic import ValidationError
        from unifin.models.trade_calendar import TradeCalendarQuery

        with pytest.raises(ValidationError):
            TradeCalendarQuery(market="mars")

    def test_market_enum_accepts_valid(self):
        from unifin.models.trade_calendar import TradeCalendarQuery
        from unifin.core.types import Market

        q = TradeCalendarQuery(market="us")
        assert q.market == Market.US

    def test_date_range_validation(self):
        """start_date > end_date should raise."""
        from pydantic import ValidationError
        from unifin.models.equity_historical import EquityHistoricalQuery

        with pytest.raises(ValidationError, match="start_date"):
            EquityHistoricalQuery(
                symbol="AAPL",
                start_date=date(2024, 12, 31),
                end_date=date(2024, 1, 1),
            )

    def test_date_range_valid(self):
        from unifin.models.equity_historical import EquityHistoricalQuery

        q = EquityHistoricalQuery(
            symbol="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert q.start_date < q.end_date

    def test_index_date_range_validation(self):
        from pydantic import ValidationError
        from unifin.models.index_historical import IndexHistoricalQuery

        with pytest.raises(ValidationError, match="start_date"):
            IndexHistoricalQuery(
                symbol="^GSPC",
                start_date=date(2025, 1, 1),
                end_date=date(2024, 1, 1),
            )

    def test_interval_enum_rejects_invalid(self):
        from pydantic import ValidationError
        from unifin.models.equity_historical import EquityHistoricalQuery

        with pytest.raises(ValidationError):
            EquityHistoricalQuery(symbol="AAPL", interval="2h")


class TestOutputValidation:
    """Verify router validates output against result Pydantic model."""

    @pytest.mark.skipif(
        not _yfinance_available(),
        reason="yfinance not installed",
    )
    def test_symbol_injected_in_results(self):
        """Router should inject unified symbol into result rows."""
        import unifin

        df = unifin.equity.historical("AAPL", start_date="2024-06-01", end_date="2024-06-05")
        assert len(df) > 0
        assert "symbol" in df.columns
        # Every row should have the unified symbol
        symbols = df["symbol"].to_list()
        assert all(s == "AAPL" for s in symbols)

    @pytest.mark.skipif(
        not _yfinance_available(),
        reason="yfinance not installed",
    )
    def test_a_share_symbol_unified_in_results(self):
        """A-share results should have MIC-format symbols."""
        import unifin

        df = unifin.equity.historical("000001.XSHE", start_date="2024-06-01", end_date="2024-06-05")
        if len(df) > 0:
            symbols = df["symbol"].to_list()
            assert all(s == "000001.XSHE" for s in symbols)


class TestProviderMetadata:
    """Verify enhanced provider and fetcher metadata."""

    def test_yfinance_provider_has_markets(self):
        from unifin.core.registry import provider_registry

        info = provider_registry.get_provider_info("yfinance")
        assert len(info.markets) > 0
        assert "US" in info.markets
        assert "CN" in info.markets

    def test_yfinance_provider_has_delay(self):
        from unifin.core.registry import provider_registry

        info = provider_registry.get_provider_info("yfinance")
        assert info.data_delay == "15min"

    def test_fetcher_has_coverage_metadata(self):
        from unifin.core.registry import provider_registry

        fetcher_cls = provider_registry.get_fetcher("equity_historical", "yfinance")
        assert len(fetcher_cls.supported_fields) > 0
        assert "close" in fetcher_cls.supported_fields
        assert fetcher_cls.data_start_date == "1970-01-01"
        assert fetcher_cls.data_delay == "15min"

    def test_all_yfinance_fetchers_have_supported_fields(self):
        """Every yfinance fetcher should declare supported_fields."""
        from unifin.core.registry import provider_registry

        models_with_yfinance = [
            "equity_historical", "equity_search", "equity_profile",
            "equity_quote", "balance_sheet", "income_statement",
            "cash_flow", "index_historical", "etf_search", "trade_calendar",
        ]
        for model_name in models_with_yfinance:
            fetcher_cls = provider_registry.get_fetcher(model_name, "yfinance")
            assert len(fetcher_cls.supported_fields) > 0, (
                f"yfinance/{model_name} missing supported_fields"
            )


class TestSymbolValidation:
    """Verify symbol format validation at the Query layer."""

    def test_valid_us_ticker(self):
        from unifin.models.equity_historical import EquityHistoricalQuery

        q = EquityHistoricalQuery(symbol="AAPL")
        assert q.symbol == "AAPL"

    def test_valid_mic_format(self):
        from unifin.models.equity_historical import EquityHistoricalQuery

        q = EquityHistoricalQuery(symbol="000001.XSHE")
        assert q.symbol == "000001.XSHE"

    def test_valid_hk(self):
        from unifin.models.equity_profile import EquityProfileQuery

        q = EquityProfileQuery(symbol="0700.XHKG")
        assert q.symbol == "0700.XHKG"

    def test_valid_index_caret(self):
        from unifin.models.index_historical import IndexHistoricalQuery

        q = IndexHistoricalQuery(symbol="^GSPC")
        assert q.symbol == "^GSPC"

    def test_valid_plain_a_share(self):
        from unifin.models.equity_historical import EquityHistoricalQuery

        q = EquityHistoricalQuery(symbol="600519")
        assert q.symbol == "600519"

    def test_valid_brk_b(self):
        from unifin.models.equity_quote import EquityQuoteQuery

        q = EquityQuoteQuery(symbol="BRK.B")
        assert q.symbol == "BRK.B"

    def test_reject_empty(self):
        from pydantic import ValidationError
        from unifin.models.equity_historical import EquityHistoricalQuery

        with pytest.raises(ValidationError, match="symbol"):
            EquityHistoricalQuery(symbol="")

    def test_reject_garbage(self):
        from pydantic import ValidationError
        from unifin.models.equity_historical import EquityHistoricalQuery

        with pytest.raises(ValidationError, match="Invalid symbol"):
            EquityHistoricalQuery(symbol="???")

    def test_reject_spaces(self):
        from pydantic import ValidationError
        from unifin.models.balance_sheet import BalanceSheetQuery

        with pytest.raises(ValidationError, match="Invalid symbol"):
            BalanceSheetQuery(symbol="apple inc")

    def test_reject_too_long_ticker(self):
        from pydantic import ValidationError
        from unifin.models.equity_profile import EquityProfileQuery

        with pytest.raises(ValidationError, match="Invalid symbol"):
            EquityProfileQuery(symbol="TOOLONGTICKER")

    def test_whitespace_stripped(self):
        from unifin.models.equity_historical import EquityHistoricalQuery

        q = EquityHistoricalQuery(symbol="  AAPL  ")
        assert q.symbol == "AAPL"

    def test_all_query_models_validate_symbol(self):
        """Every Query model with a required symbol should reject garbage."""
        from pydantic import ValidationError

        from unifin.models.equity_historical import EquityHistoricalQuery
        from unifin.models.equity_profile import EquityProfileQuery
        from unifin.models.equity_quote import EquityQuoteQuery
        from unifin.models.balance_sheet import BalanceSheetQuery
        from unifin.models.income_statement import IncomeStatementQuery
        from unifin.models.cash_flow import CashFlowQuery
        from unifin.models.index_historical import IndexHistoricalQuery

        models = [
            EquityHistoricalQuery,
            EquityProfileQuery,
            EquityQuoteQuery,
            BalanceSheetQuery,
            IncomeStatementQuery,
            CashFlowQuery,
            IndexHistoricalQuery,
        ]
        for model_cls in models:
            with pytest.raises(ValidationError):
                model_cls(symbol="!!invalid!!")
