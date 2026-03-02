"""Tests for unifin core + equity_historical end-to-end."""

from __future__ import annotations

from datetime import date

import pytest


# ──────────────────────────────────────────────
# 1. Symbol resolution tests
# ──────────────────────────────────────────────


class TestSymbolResolver:
    """Test ISO 10383 MIC symbol parsing and conversion."""

    def test_parse_unified_a_share(self):
        from unifin.core.symbol import parse_symbol
        from unifin.core.types import Exchange

        code, exchange = parse_symbol("000001.XSHE")
        assert code == "000001"
        assert exchange == Exchange.XSHE

    def test_parse_unified_shanghai(self):
        from unifin.core.symbol import parse_symbol
        from unifin.core.types import Exchange

        code, exchange = parse_symbol("600519.XSHG")
        assert code == "600519"
        assert exchange == Exchange.XSHG

    def test_parse_plain_a_share_shenzhen(self):
        from unifin.core.symbol import parse_symbol
        from unifin.core.types import Exchange

        code, exchange = parse_symbol("000001")
        assert code == "000001"
        assert exchange == Exchange.XSHE

    def test_parse_plain_a_share_shanghai(self):
        from unifin.core.symbol import parse_symbol
        from unifin.core.types import Exchange

        code, exchange = parse_symbol("600519")
        assert code == "600519"
        assert exchange == Exchange.XSHG

    def test_parse_us_ticker(self):
        from unifin.core.symbol import parse_symbol

        code, exchange = parse_symbol("AAPL")
        assert code == "AAPL"
        assert exchange is None  # US tickers are ambiguous without suffix

    def test_parse_us_with_mic(self):
        from unifin.core.symbol import parse_symbol
        from unifin.core.types import Exchange

        code, exchange = parse_symbol("AAPL.XNAS")
        assert code == "AAPL"
        assert exchange == Exchange.XNAS

    def test_parse_yahoo_format(self):
        from unifin.core.symbol import parse_symbol
        from unifin.core.types import Exchange

        code, exchange = parse_symbol("000001.SZ")
        assert code == "000001"
        assert exchange == Exchange.XSHE

    def test_parse_hk(self):
        from unifin.core.symbol import parse_symbol
        from unifin.core.types import Exchange

        code, exchange = parse_symbol("0700.XHKG")
        assert code == "0700"
        assert exchange == Exchange.XHKG

    def test_to_provider_yfinance_a_share(self):
        from unifin.core.symbol import to_provider_symbol

        assert to_provider_symbol("000001.XSHE", "yfinance") == "000001.SZ"
        assert to_provider_symbol("600519.XSHG", "yfinance") == "600519.SS"

    def test_to_provider_yfinance_us(self):
        from unifin.core.symbol import to_provider_symbol

        assert to_provider_symbol("AAPL", "yfinance") == "AAPL"

    def test_to_provider_yfinance_hk(self):
        from unifin.core.symbol import to_provider_symbol

        assert to_provider_symbol("0700.XHKG", "yfinance") == "0700.HK"

    def test_to_provider_eastmoney(self):
        from unifin.core.symbol import to_provider_symbol

        assert to_provider_symbol("600519.XSHG", "eastmoney") == "600519.SH"
        assert to_provider_symbol("000001.XSHE", "eastmoney") == "000001.SZ"

    def test_to_unified(self):
        from unifin.core.symbol import to_unified_symbol

        assert to_unified_symbol("000001.SZ", "yfinance") == "000001.XSHE"
        assert to_unified_symbol("600519.SS", "yfinance") == "600519.XSHG"
        assert to_unified_symbol("AAPL") == "AAPL"
        assert to_unified_symbol("000001.XSHE") == "000001.XSHE"

    def test_roundtrip(self):
        from unifin.core.symbol import to_provider_symbol, to_unified_symbol

        original = "000001.XSHE"
        yf = to_provider_symbol(original, "yfinance")
        assert yf == "000001.SZ"
        back = to_unified_symbol(yf)
        assert back == original


# ──────────────────────────────────────────────
# 2. Registry tests
# ──────────────────────────────────────────────


class TestRegistry:
    """Test model and provider registration."""

    def test_model_registered(self):
        from unifin.core.registry import model_registry

        # equity_historical should be registered on import
        import unifin.models.equity_historical  # noqa: F401

        assert "equity_historical" in model_registry
        info = model_registry.get("equity_historical")
        assert info.category == "equity.price"

    def test_yfinance_provider_registered(self):
        from unifin.core.registry import provider_registry

        try:
            import unifin.providers.yfinance  # noqa: F401
        except ImportError:
            pytest.skip("yfinance not installed")

        assert "yfinance" in provider_registry.list_providers()

    def test_yfinance_fetcher_registered(self):
        from unifin.core.registry import provider_registry
        from unifin.core.types import Exchange

        try:
            import unifin.providers.yfinance  # noqa: F401
        except ImportError:
            pytest.skip("yfinance not installed")

        fetchers = provider_registry.get_providers_for_model("equity_historical")
        assert "yfinance" in fetchers

        # Check exchange coverage
        providers_for_xshe = provider_registry.get_providers_for_exchange(
            "equity_historical", Exchange.XSHE
        )
        assert "yfinance" in providers_for_xshe


# ──────────────────────────────────────────────
# 3. Smart router tests
# ──────────────────────────────────────────────


class TestSmartRouter:
    """Test auto-routing logic."""

    def test_resolve_a_share_providers(self):
        from unifin.core.router import SmartRouter
        from unifin.core.types import Exchange

        try:
            import unifin.providers.yfinance  # noqa: F401
        except ImportError:
            pytest.skip("yfinance not installed")

        router = SmartRouter()
        providers = router._resolve_providers("equity_historical", Exchange.XSHE, None)
        assert len(providers) > 0
        # yfinance should be in the list for XSHE
        assert "yfinance" in providers

    def test_explicit_provider(self):
        from unifin.core.router import SmartRouter

        router = SmartRouter()
        providers = router._resolve_providers("equity_historical", None, "yfinance")
        assert providers == ["yfinance"]


# ──────────────────────────────────────────────
# 4. Model validation tests
# ──────────────────────────────────────────────


class TestEquityHistoricalModel:
    """Test the equity historical data model."""

    def test_query_defaults(self):
        from unifin.core.types import Adjust, Interval
        from unifin.models.equity_historical import EquityHistoricalQuery

        q = EquityHistoricalQuery(symbol="AAPL")
        assert q.interval == Interval.DAILY
        assert q.adjust == Adjust.NONE
        assert q.start_date is None
        assert q.end_date is None

    def test_query_with_dates(self):
        from unifin.models.equity_historical import EquityHistoricalQuery

        q = EquityHistoricalQuery(
            symbol="000001.XSHE",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert q.symbol == "000001.XSHE"
        assert q.start_date == date(2024, 1, 1)

    def test_data_validation(self):
        from unifin.models.equity_historical import EquityHistoricalData

        d = EquityHistoricalData(
            date=date(2024, 1, 2),
            open=10.5,
            high=11.0,
            low=10.2,
            close=10.8,
            volume=1000000,
        )
        assert d.close == 10.8
        assert d.amount is None  # optional


# ──────────────────────────────────────────────
# 5. End-to-end integration test (requires yfinance)
# ──────────────────────────────────────────────


def _yfinance_available() -> bool:
    try:
        import yfinance  # noqa: F401

        return True
    except ImportError:
        return False


class TestEndToEnd:
    """Integration tests that actually fetch data."""

    @pytest.mark.skipif(
        not _yfinance_available(),
        reason="yfinance not installed",
    )
    def test_fetch_us_equity(self):
        """Fetch US equity data via auto-routing (should use yfinance)."""
        import unifin

        df = unifin.equity.historical(
            "AAPL",
            start_date="2024-01-02",
            end_date="2024-01-10",
            use_cache=False,
        )
        assert len(df) > 0
        assert "date" in df.columns
        assert "close" in df.columns
        print(f"\n  Fetched {len(df)} rows for AAPL")
        print(df.head())

    @pytest.mark.skipif(
        not _yfinance_available(),
        reason="yfinance not installed",
    )
    def test_fetch_a_share(self):
        """Fetch A-share data — should auto-route to yfinance (or eastmoney if available)."""
        import unifin

        df = unifin.equity.historical(
            "000001.XSHE",
            start_date="2024-01-02",
            end_date="2024-01-10",
            provider="yfinance",
            use_cache=False,
        )
        assert len(df) > 0
        assert "close" in df.columns
        print(f"\n  Fetched {len(df)} rows for 000001.XSHE")
        print(df.head())

    @pytest.mark.skipif(
        not _yfinance_available(),
        reason="yfinance not installed",
    )
    def test_fetch_hk_equity(self):
        """Fetch HK equity data."""
        import unifin

        df = unifin.equity.historical(
            "0700.XHKG",
            start_date="2024-01-02",
            end_date="2024-01-10",
            provider="yfinance",
            use_cache=False,
        )
        assert len(df) > 0
        print(f"\n  Fetched {len(df)} rows for 0700.XHKG (Tencent)")
        print(df.head())
