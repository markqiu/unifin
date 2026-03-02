"""Tests for yfinance etf_search/trade_calendar and akshare provider fetchers.

Covers:
  - Fetcher registration (yfinance: etf_search, trade_calendar)
  - Fetcher registration (akshare: equity_historical, equity_search, equity_quote,
    etf_search, trade_calendar)
  - Provider metadata (akshare)
  - transform_query, transform_data (unit tests with mock data — no network)
"""

from __future__ import annotations

from datetime import date

import pytest

# ──────────────────────────────────────────────────
# 0. Helpers
# ──────────────────────────────────────────────────


def _akshare_available() -> bool:
    try:
        import akshare  # noqa: F401

        return True
    except ImportError:
        return False


def _yfinance_available() -> bool:
    try:
        import yfinance  # noqa: F401

        return True
    except ImportError:
        return False


# ──────────────────────────────────────────────────
# 1. Provider & fetcher registration
# ──────────────────────────────────────────────────


class TestAKShareProviderRegistration:
    """AKShare provider should be registered with correct metadata."""

    def test_provider_registered(self):
        from unifin.core.registry import provider_registry

        assert "akshare" in provider_registry.list_providers()

    def test_provider_markets(self):
        from unifin.core.registry import provider_registry

        info = provider_registry.get_provider_info("akshare")
        assert "CN" in info.markets
        assert "HK" in info.markets

    def test_provider_no_credentials(self):
        from unifin.core.registry import provider_registry

        info = provider_registry.get_provider_info("akshare")
        assert info.credentials_env == {}

    def test_provider_delay(self):
        from unifin.core.registry import provider_registry

        info = provider_registry.get_provider_info("akshare")
        assert info.data_delay == "15min"


class TestYFinanceNewFetcherRegistration:
    """yfinance etf_search and trade_calendar fetchers should be registered."""

    def test_etf_search_registered(self):
        from unifin.core.registry import provider_registry

        providers = list(provider_registry.get_providers_for_model("etf_search").keys())
        assert "yfinance" in providers

    def test_trade_calendar_registered(self):
        from unifin.core.registry import provider_registry

        providers = list(provider_registry.get_providers_for_model("trade_calendar").keys())
        assert "yfinance" in providers

    def test_etf_search_supported_fields(self):
        from unifin.core.registry import provider_registry

        fetcher = provider_registry.get_fetcher("etf_search", "yfinance")
        assert "symbol" in fetcher.supported_fields
        assert "name" in fetcher.supported_fields

    def test_trade_calendar_supported_fields(self):
        from unifin.core.registry import provider_registry

        fetcher = provider_registry.get_fetcher("trade_calendar", "yfinance")
        assert "date" in fetcher.supported_fields
        assert "is_open" in fetcher.supported_fields
        assert "market" in fetcher.supported_fields


class TestAKShareFetcherRegistration:
    """All 5 akshare fetchers should be registered."""

    @pytest.mark.parametrize(
        "model_name",
        [
            "equity_historical",
            "equity_search",
            "equity_quote",
            "etf_search",
            "trade_calendar",
        ],
    )
    def test_akshare_registered(self, model_name: str):
        from unifin.core.registry import provider_registry

        providers = list(provider_registry.get_providers_for_model(model_name).keys())
        assert "akshare" in providers, f"akshare not registered for '{model_name}'"

    @pytest.mark.parametrize(
        "model_name",
        [
            "equity_historical",
            "equity_search",
            "equity_quote",
            "etf_search",
            "trade_calendar",
        ],
    )
    def test_akshare_supported_fields(self, model_name: str):
        from unifin.core.registry import provider_registry

        fetcher = provider_registry.get_fetcher(model_name, "akshare")
        assert len(fetcher.supported_fields) > 0

    def test_akshare_equity_historical_exchanges(self):
        from unifin.core.registry import provider_registry
        from unifin.core.types import Exchange

        fetcher = provider_registry.get_fetcher("equity_historical", "akshare")
        assert Exchange.XSHG in fetcher.supported_exchanges
        assert Exchange.XSHE in fetcher.supported_exchanges
        assert Exchange.XHKG in fetcher.supported_exchanges

    def test_akshare_equity_search_exchanges(self):
        from unifin.core.registry import provider_registry
        from unifin.core.types import Exchange

        fetcher = provider_registry.get_fetcher("equity_search", "akshare")
        assert Exchange.XSHG in fetcher.supported_exchanges
        assert Exchange.XSHE in fetcher.supported_exchanges


# ──────────────────────────────────────────────────
# 2. YFinance etf_search — transform_query / transform_data
# ──────────────────────────────────────────────────


class TestYFinanceEtfSearchTransform:
    def test_transform_query_basic(self):
        from unifin.models.etf_search import EtfSearchQuery
        from unifin.providers.yfinance.etf_search import YFinanceEtfSearchFetcher

        q = EtfSearchQuery(query="S&P 500")
        params = YFinanceEtfSearchFetcher.transform_query(q)
        assert params["query"] == "S&P 500"
        assert params["limit"] == 25

    def test_transform_query_with_limit(self):
        from unifin.models.etf_search import EtfSearchQuery
        from unifin.providers.yfinance.etf_search import YFinanceEtfSearchFetcher

        q = EtfSearchQuery(query="bond", limit=10)
        params = YFinanceEtfSearchFetcher.transform_query(q)
        assert params["limit"] == 10

    def test_transform_data_empty(self):
        from unifin.models.etf_search import EtfSearchQuery
        from unifin.providers.yfinance.etf_search import YFinanceEtfSearchFetcher

        q = EtfSearchQuery(query="x")
        result = YFinanceEtfSearchFetcher.transform_data([], q)
        assert result == []

    def test_transform_data_with_quotes(self):
        from unifin.models.etf_search import EtfSearchQuery
        from unifin.providers.yfinance.etf_search import YFinanceEtfSearchFetcher

        mock_data = [
            {
                "symbol": "SPY",
                "shortname": "SPDR S&P 500 ETF Trust",
                "exchange": "PCX",
                "quoteType": "ETF",
            },
            {
                "symbol": "VOO",
                "longName": "Vanguard S&P 500 ETF",
                "exchange": "PCX",
                "quoteType": "ETF",
            },
        ]
        q = EtfSearchQuery(query="S&P")
        result = YFinanceEtfSearchFetcher.transform_data(mock_data, q)
        assert len(result) == 2
        assert result[0]["symbol"] == "SPY"
        assert result[0]["name"] == "SPDR S&P 500 ETF Trust"
        assert result[1]["symbol"] == "VOO"
        assert result[1]["name"] == "Vanguard S&P 500 ETF"
        assert result[0]["fund_type"] == "ETF"


# ──────────────────────────────────────────────────
# 3. YFinance trade_calendar — transform_query / transform_data
# ──────────────────────────────────────────────────


class TestYFinanceTradeCalendarTransform:
    def test_transform_query_cn(self):
        from unifin.models.trade_calendar import TradeCalendarQuery
        from unifin.providers.yfinance.trade_calendar import YFinanceTradeCalendarFetcher

        q = TradeCalendarQuery(
            market="cn",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        params = YFinanceTradeCalendarFetcher.transform_query(q)
        assert params["symbol"] == "000001.SS"  # CN proxy
        assert params["market"] == "cn"
        assert params["start"] == "2024-01-01"

    def test_transform_query_us(self):
        from unifin.models.trade_calendar import TradeCalendarQuery
        from unifin.providers.yfinance.trade_calendar import YFinanceTradeCalendarFetcher

        q = TradeCalendarQuery(market="us")
        params = YFinanceTradeCalendarFetcher.transform_query(q)
        assert params["symbol"] == "SPY"
        assert params["market"] == "us"

    def test_transform_data_with_dates(self):
        from unifin.models.trade_calendar import TradeCalendarQuery
        from unifin.providers.yfinance.trade_calendar import YFinanceTradeCalendarFetcher

        raw = {
            "dates": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
            "market": "us",
        }
        q = TradeCalendarQuery(market="us")
        result = YFinanceTradeCalendarFetcher.transform_data(raw, q)
        assert len(result) == 3
        assert result[0]["date"] == date(2024, 1, 2)
        assert result[0]["is_open"] is True
        assert result[0]["market"] == "us"

    def test_transform_data_empty(self):
        from unifin.models.trade_calendar import TradeCalendarQuery
        from unifin.providers.yfinance.trade_calendar import YFinanceTradeCalendarFetcher

        raw = {"dates": [], "market": "cn"}
        q = TradeCalendarQuery(market="cn")
        result = YFinanceTradeCalendarFetcher.transform_data(raw, q)
        assert result == []


# ──────────────────────────────────────────────────
# 4. AKShare equity_historical — transform_query / transform_data
# ──────────────────────────────────────────────────


class TestAKShareEquityHistoricalTransform:
    def test_transform_query_defaults(self):
        from unifin.models.equity_historical import EquityHistoricalQuery
        from unifin.providers.akshare.equity_historical import AKShareEquityHistoricalFetcher

        q = EquityHistoricalQuery(
            symbol="000001.XSHE",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
        )
        params = AKShareEquityHistoricalFetcher.transform_query(q)
        assert params["start_date"] == "20240101"
        assert params["end_date"] == "20240331"
        assert params["period"] == "daily"
        assert params["adjust"] == ""

    def test_transform_query_weekly_qfq(self):
        from unifin.core.types import Adjust, Interval
        from unifin.models.equity_historical import EquityHistoricalQuery
        from unifin.providers.akshare.equity_historical import AKShareEquityHistoricalFetcher

        q = EquityHistoricalQuery(
            symbol="600519.XSHG",
            interval=Interval.WEEKLY,
            adjust=Adjust.FORWARD,
        )
        params = AKShareEquityHistoricalFetcher.transform_query(q)
        assert params["period"] == "weekly"
        assert params["adjust"] == "qfq"

    def test_transform_data_from_df(self):
        import pandas as pd

        from unifin.models.equity_historical import EquityHistoricalQuery
        from unifin.providers.akshare.equity_historical import AKShareEquityHistoricalFetcher

        mock_df = pd.DataFrame(
            {
                "日期": ["2024-01-02", "2024-01-03"],
                "开盘": [10.5, 10.8],
                "收盘": [10.8, 11.0],
                "最高": [11.0, 11.2],
                "最低": [10.3, 10.7],
                "成交量": [100000, 120000],
                "成交额": [1080000.0, 1320000.0],
            }
        )
        q = EquityHistoricalQuery(symbol="000001.XSHE")
        result = AKShareEquityHistoricalFetcher.transform_data(mock_df, q)
        assert len(result) == 2
        assert result[0]["open"] == 10.5
        assert result[0]["close"] == 10.8
        assert result[0]["volume"] == 100000
        assert result[1]["high"] == 11.2

    def test_transform_data_empty(self):
        from unifin.models.equity_historical import EquityHistoricalQuery
        from unifin.providers.akshare.equity_historical import AKShareEquityHistoricalFetcher

        q = EquityHistoricalQuery(symbol="000001.XSHE")
        result = AKShareEquityHistoricalFetcher.transform_data(None, q)
        assert result == []


# ──────────────────────────────────────────────────
# 5. AKShare equity_search — transform_query / transform_data
# ──────────────────────────────────────────────────


class TestAKShareEquitySearchTransform:
    def test_transform_query(self):
        from unifin.models.equity_search import EquitySearchQuery
        from unifin.providers.akshare.equity_search import AKShareEquitySearchFetcher

        q = EquitySearchQuery(query="平安")
        params = AKShareEquitySearchFetcher.transform_query(q)
        assert params["query"] == "平安"
        assert params["limit"] == 100

    def test_transform_data_filters_by_name(self):
        from unifin.models.equity_search import EquitySearchQuery
        from unifin.providers.akshare.equity_search import AKShareEquitySearchFetcher

        mock_data = [
            {"code": "000001", "name": "平安银行"},
            {"code": "601318", "name": "中国平安"},
            {"code": "600519", "name": "贵州茅台"},
        ]
        q = EquitySearchQuery(query="平安")
        result = AKShareEquitySearchFetcher.transform_data(mock_data, q)
        assert len(result) == 2
        assert result[0]["name"] == "平安银行"
        assert result[0]["symbol"] == "000001.XSHE"
        assert result[1]["name"] == "中国平安"
        assert result[1]["symbol"] == "601318.XSHG"

    def test_transform_data_filters_by_code(self):
        from unifin.models.equity_search import EquitySearchQuery
        from unifin.providers.akshare.equity_search import AKShareEquitySearchFetcher

        mock_data = [
            {"code": "000001", "name": "平安银行"},
            {"code": "000002", "name": "万科A"},
        ]
        q = EquitySearchQuery(query="000001")
        result = AKShareEquitySearchFetcher.transform_data(mock_data, q)
        assert len(result) == 1
        assert result[0]["symbol"] == "000001.XSHE"

    def test_transform_data_empty_query_returns_all(self):
        from unifin.models.equity_search import EquitySearchQuery
        from unifin.providers.akshare.equity_search import AKShareEquitySearchFetcher

        mock_data = [
            {"code": "000001", "name": "平安银行"},
            {"code": "000002", "name": "万科A"},
        ]
        q = EquitySearchQuery(query="")
        result = AKShareEquitySearchFetcher.transform_data(mock_data, q)
        assert len(result) == 2

    def test_infer_exchange(self):
        from unifin.providers.akshare.equity_search import _infer_exchange

        assert _infer_exchange("600519") == "XSHG"
        assert _infer_exchange("000001") == "XSHE"
        assert _infer_exchange("300059") == "XSHE"
        assert _infer_exchange("830799") == "XBSE"


# ──────────────────────────────────────────────────
# 6. AKShare equity_quote — transform_query / transform_data
# ──────────────────────────────────────────────────


class TestAKShareEquityQuoteTransform:
    def test_transform_query(self):
        from unifin.models.equity_quote import EquityQuoteQuery
        from unifin.providers.akshare.equity_quote import AKShareEquityQuoteFetcher

        q = EquityQuoteQuery(symbol="000001.XSHE")
        params = AKShareEquityQuoteFetcher.transform_query(q)
        assert params["symbol"] == "000001.XSHE"

    def test_transform_data_with_records(self):
        from unifin.models.equity_quote import EquityQuoteQuery
        from unifin.providers.akshare.equity_quote import AKShareEquityQuoteFetcher

        mock_data = [
            {
                "代码": "000001",
                "名称": "平安银行",
                "最新价": 12.5,
                "今开": 12.3,
                "最高": 12.8,
                "最低": 12.1,
                "昨收": 12.2,
                "成交量": 500000,
                "成交额": 6250000.0,
                "涨跌额": 0.3,
                "涨跌幅": 2.46,
                "换手率": 0.5,
                "流通市值": 240000000000.0,
            }
        ]
        q = EquityQuoteQuery(symbol="000001.XSHE")
        result = AKShareEquityQuoteFetcher.transform_data(mock_data, q)
        assert len(result) == 1
        row = result[0]
        assert row["symbol"] == "000001"
        assert row["name"] == "平安银行"
        assert row["last_price"] == 12.5
        assert row["change"] == 0.3
        assert row["change_percent"] == 2.46
        assert row["volume"] == 500000

    def test_transform_data_empty(self):
        from unifin.models.equity_quote import EquityQuoteQuery
        from unifin.providers.akshare.equity_quote import AKShareEquityQuoteFetcher

        q = EquityQuoteQuery(symbol="000001.XSHE")
        result = AKShareEquityQuoteFetcher.transform_data([], q)
        assert result == []


# ──────────────────────────────────────────────────
# 7. AKShare etf_search — transform_query / transform_data
# ──────────────────────────────────────────────────


class TestAKShareEtfSearchTransform:
    def test_transform_query(self):
        from unifin.models.etf_search import EtfSearchQuery
        from unifin.providers.akshare.etf_search import AKShareEtfSearchFetcher

        q = EtfSearchQuery(query="沪深300")
        params = AKShareEtfSearchFetcher.transform_query(q)
        assert params["query"] == "沪深300"
        assert params["limit"] == 100

    def test_transform_data_from_fund_name_em(self):
        import pandas as pd

        from unifin.models.etf_search import EtfSearchQuery
        from unifin.providers.akshare.etf_search import AKShareEtfSearchFetcher

        mock_df = pd.DataFrame(
            {
                "基金代码": ["510300", "510500", "000001"],
                "基金简称": ["华泰柏瑞沪深300ETF", "南方中证500ETF", "华夏成长混合"],
                "基金类型": ["股票型-ETF", "股票型-ETF", "混合型"],
            }
        )
        raw = {"source": "fund_name_em", "data": mock_df}
        q = EtfSearchQuery(query="")
        result = AKShareEtfSearchFetcher.transform_data(raw, q)
        # Should only include ETF types, not 混合型
        assert len(result) == 2
        assert result[0]["symbol"] == "510300"
        assert result[0]["name"] == "华泰柏瑞沪深300ETF"

    def test_transform_data_with_filter(self):
        import pandas as pd

        from unifin.models.etf_search import EtfSearchQuery
        from unifin.providers.akshare.etf_search import AKShareEtfSearchFetcher

        mock_df = pd.DataFrame(
            {
                "基金代码": ["510300", "510500"],
                "基金简称": ["华泰柏瑞沪深300ETF", "南方中证500ETF"],
                "基金类型": ["股票型-ETF", "股票型-ETF"],
            }
        )
        raw = {"source": "fund_name_em", "data": mock_df}
        q = EtfSearchQuery(query="300")
        result = AKShareEtfSearchFetcher.transform_data(raw, q)
        assert len(result) == 1
        assert result[0]["symbol"] == "510300"

    def test_transform_data_empty_source(self):
        from unifin.models.etf_search import EtfSearchQuery
        from unifin.providers.akshare.etf_search import AKShareEtfSearchFetcher

        raw = {"source": "none", "data": None}
        q = EtfSearchQuery(query="x")
        result = AKShareEtfSearchFetcher.transform_data(raw, q)
        assert result == []


# ──────────────────────────────────────────────────
# 8. AKShare trade_calendar — transform_query / transform_data
# ──────────────────────────────────────────────────


class TestAKShareTradeCalendarTransform:
    def test_transform_query_cn(self):
        from unifin.models.trade_calendar import TradeCalendarQuery
        from unifin.providers.akshare.trade_calendar import AKShareTradeCalendarFetcher

        q = TradeCalendarQuery(
            market="cn",
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 30),
        )
        params = AKShareTradeCalendarFetcher.transform_query(q)
        assert params["market"] == "cn"
        assert params["start_date"] == date(2024, 6, 1)
        assert params["end_date"] == date(2024, 6, 30)

    def test_transform_data_with_dates(self):
        from unifin.models.trade_calendar import TradeCalendarQuery
        from unifin.providers.akshare.trade_calendar import AKShareTradeCalendarFetcher

        raw = {
            "dates": [date(2024, 6, 3), date(2024, 6, 4), date(2024, 6, 5)],
            "market": "cn",
        }
        q = TradeCalendarQuery(market="cn")
        result = AKShareTradeCalendarFetcher.transform_data(raw, q)
        assert len(result) == 3
        assert result[0]["date"] == date(2024, 6, 3)
        assert result[0]["is_open"] is True
        assert result[0]["market"] == "cn"

    def test_transform_data_empty(self):
        from unifin.models.trade_calendar import TradeCalendarQuery
        from unifin.providers.akshare.trade_calendar import AKShareTradeCalendarFetcher

        raw = {"dates": [], "market": "cn"}
        q = TradeCalendarQuery(market="cn")
        result = AKShareTradeCalendarFetcher.transform_data(raw, q)
        assert result == []

    def test_extract_data_non_cn_returns_empty(self):
        """Non-CN markets should return empty (akshare only covers CN)."""
        from unifin.providers.akshare.trade_calendar import AKShareTradeCalendarFetcher

        params = {"market": "us", "start_date": date(2024, 1, 1), "end_date": date(2024, 1, 31)}
        result = AKShareTradeCalendarFetcher.extract_data(params)
        assert result["dates"] == []


# ──────────────────────────────────────────────────
# 9. SmartRouter coverage for new providers
# ──────────────────────────────────────────────────


class TestSmartRouterNewProviders:
    """Router should find akshare + yfinance for CN models."""

    def test_etf_search_has_two_providers(self):
        from unifin.core.registry import provider_registry

        providers = list(provider_registry.get_providers_for_model("etf_search").keys())
        assert "yfinance" in providers
        assert "akshare" in providers

    def test_trade_calendar_has_two_providers(self):
        from unifin.core.registry import provider_registry

        providers = list(provider_registry.get_providers_for_model("trade_calendar").keys())
        assert "yfinance" in providers
        assert "akshare" in providers

    def test_equity_historical_includes_akshare(self):
        from unifin.core.registry import provider_registry

        providers = list(provider_registry.get_providers_for_model("equity_historical").keys())
        assert "akshare" in providers
        assert "yfinance" in providers

    def test_router_resolve_cn_equity_historical(self):
        from unifin.core.router import SmartRouter
        from unifin.core.types import Exchange

        router = SmartRouter()
        providers = router._resolve_providers("equity_historical", Exchange.XSHE, None)
        # Both yfinance and akshare support XSHE
        assert "yfinance" in providers
        assert "akshare" in providers

    def test_router_resolve_etf_search_xshg(self):
        from unifin.core.router import SmartRouter
        from unifin.core.types import Exchange

        router = SmartRouter()
        providers = router._resolve_providers("etf_search", Exchange.XSHG, None)
        assert "yfinance" in providers
        assert "akshare" in providers


# ──────────────────────────────────────────────────
# 10. Symbol format for akshare
# ──────────────────────────────────────────────────


class TestAKShareSymbolFormat:
    """akshare expects plain codes (no suffix)."""

    def test_to_provider_akshare_shenzhen(self):
        from unifin.core.symbol import to_provider_symbol

        result = to_provider_symbol("000001.XSHE", "akshare")
        assert result == "000001"

    def test_to_provider_akshare_shanghai(self):
        from unifin.core.symbol import to_provider_symbol

        result = to_provider_symbol("600519.XSHG", "akshare")
        assert result == "600519"

    def test_to_provider_akshare_plain(self):
        from unifin.core.symbol import to_provider_symbol

        # Plain US ticker should pass through
        result = to_provider_symbol("AAPL", "akshare")
        assert result == "AAPL"
