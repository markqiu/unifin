"""Tests for AI-friendly error messages across the unifin platform.

Verifies that error messages contain structured, actionable information
to help AI callers self-correct.
"""

import pytest
from datetime import date


# ──────────────────────────────────────────────
# 1. Error class structure tests
# ──────────────────────────────────────────────


class TestErrorClasses:
    """Verify error classes have structured attributes."""

    def test_unifin_error_attributes(self):
        from unifin.core.errors import UnifinError

        e = UnifinError(
            "test msg",
            code="TEST",
            received="bad",
            expected=["good1", "good2"],
            hint="try good1",
        )
        assert e.code == "TEST"
        assert e.received == "bad"
        assert e.expected == ["good1", "good2"]
        assert e.hint == "try good1"
        assert "test msg" in str(e)
        assert "bad" in str(e)
        assert "good1" in str(e)

    def test_symbol_error_is_value_error(self):
        """SymbolError must be a ValueError for Pydantic compatibility."""
        from unifin.core.errors import SymbolError

        e = SymbolError("bad symbol", received="???")
        assert isinstance(e, ValueError)

    def test_param_error_is_value_error(self):
        """ParamError must be a ValueError for Pydantic compatibility."""
        from unifin.core.errors import ParamError

        e = ParamError("bad param", code="TEST")
        assert isinstance(e, ValueError)

    def test_model_not_found_suggestions(self):
        from unifin.core.errors import ModelNotFoundError

        e = ModelNotFoundError("equity_hist", ["equity_historical", "equity_search"])
        assert e.code == "MODEL_NOT_FOUND"
        assert "equity_hist" in str(e)
        # Should suggest the similar name
        assert "equity_historical" in str(e)

    def test_fetcher_not_found_hint(self):
        from unifin.core.errors import FetcherNotFoundError

        e = FetcherNotFoundError("balance_sheet", "akshare", ["yfinance", "tushare"])
        assert e.code == "FETCHER_NOT_FOUND"
        assert "akshare" in str(e)
        assert "yfinance" in str(e)
        assert "tushare" in str(e)

    def test_provider_not_found(self):
        from unifin.core.errors import ProviderNotFoundError

        e = ProviderNotFoundError("nonexist", ["yfinance", "eastmoney"])
        assert e.code == "PROVIDER_NOT_FOUND"
        assert "nonexist" in str(e)
        assert "yfinance" in str(e)

    def test_no_provider_error(self):
        from unifin.core.errors import NoProviderError

        e = NoProviderError(
            "equity_historical",
            exchange="XBSE",
            requested_provider="fmp",
            available_providers=["yfinance"],
        )
        assert e.code == "NO_PROVIDER"
        assert "equity_historical" in str(e)
        assert "fmp" in str(e)

    def test_all_providers_failed(self):
        from unifin.core.errors import AllProvidersFailedError

        inner = RuntimeError("network timeout")
        e = AllProvidersFailedError("equity_historical", ["yfinance", "fmp"], inner)
        assert e.code == "ALL_PROVIDERS_FAILED"
        assert "network timeout" in str(e)
        assert e.context["tried_providers"] == ["yfinance", "fmp"]

    def test_invalid_date_range(self):
        from unifin.core.errors import InvalidDateRangeError

        e = InvalidDateRangeError(date(2025, 6, 1), date(2024, 1, 1))
        assert e.code == "INVALID_DATE_RANGE"
        assert "2025-06-01" in str(e)
        assert "2024-01-01" in str(e)
        assert "Swap" in str(e)

    def test_invalid_enum_value(self):
        from unifin.core.errors import InvalidEnumValueError
        from unifin.core.types import Interval

        e = InvalidEnumValueError("interval", "2h", Interval)
        assert e.code == "INVALID_ENUM_VALUE"
        assert "2h" in str(e)
        assert "1d" in str(e)  # valid value should appear

    def test_invalid_date_format(self):
        from unifin.core.errors import InvalidDateFormatError

        e = InvalidDateFormatError("start_date", "not-a-date")
        assert e.code == "INVALID_DATE_FORMAT"
        assert "not-a-date" in str(e)
        assert "YYYY-MM-DD" in str(e)


# ──────────────────────────────────────────────
# 2. Symbol validation error friendliness
# ──────────────────────────────────────────────


class TestSymbolErrorMessages:
    """Verify symbol errors are informative for AI callers."""

    def test_empty_symbol_message(self):
        from unifin.core.errors import SymbolError
        from unifin.core.symbol import validate_symbol

        with pytest.raises(SymbolError) as exc_info:
            validate_symbol("")
        e = exc_info.value
        assert e.code == "INVALID_SYMBOL"
        assert "empty" in str(e).lower()
        assert len(e.expected) >= 4  # has multiple example formats

    def test_garbage_symbol_message(self):
        from unifin.core.errors import SymbolError
        from unifin.core.symbol import validate_symbol

        with pytest.raises(SymbolError) as exc_info:
            validate_symbol("???what???")
        e = exc_info.value
        assert e.received == "???what???"
        assert "Hint" in str(e)

    def test_symbol_error_via_pydantic(self):
        """Pydantic ValidationError should wrap a SymbolError."""
        from pydantic import ValidationError

        from unifin.models.equity_historical import EquityHistoricalQuery

        with pytest.raises(ValidationError) as exc_info:
            EquityHistoricalQuery(symbol="##invalid##")
        # The inner error message should contain guidance
        msg = str(exc_info.value)
        assert "AAPL" in msg or "Invalid symbol" in msg


# ──────────────────────────────────────────────
# 3. Registry / Router error friendliness
# ──────────────────────────────────────────────


class TestRegistryErrors:
    """Verify registry errors are AI-friendly."""

    def test_model_not_found_error(self):
        from unifin.core.errors import ModelNotFoundError
        from unifin.core.registry import model_registry

        with pytest.raises(ModelNotFoundError) as exc_info:
            model_registry.get("nonexistent_model")
        e = exc_info.value
        assert e.code == "MODEL_NOT_FOUND"
        assert "equity_historical" in e.expected  # lists available models

    def test_fetcher_not_found_error(self):
        from unifin.core.errors import FetcherNotFoundError
        from unifin.core.registry import provider_registry

        with pytest.raises(FetcherNotFoundError) as exc_info:
            provider_registry.get_fetcher("equity_historical", "nonexistent_prov")
        e = exc_info.value
        assert e.code == "FETCHER_NOT_FOUND"
        assert "yfinance" in str(e)  # available provider listed

    def test_provider_not_found_error(self):
        from unifin.core.errors import ProviderNotFoundError
        from unifin.core.registry import provider_registry

        with pytest.raises(ProviderNotFoundError) as exc_info:
            provider_registry.get_provider_info("nonexistent_prov")
        e = exc_info.value
        assert e.code == "PROVIDER_NOT_FOUND"
        assert len(e.expected) > 0  # lists available providers


class TestRouterErrors:
    """Verify router-level errors guide AI callers."""

    def test_no_provider_for_model(self):
        """When no provider covers a specific exchange, NoProviderError is raised."""
        from unifin.core.errors import NoProviderError
        from unifin.core.router import SmartRouter
        from unifin.core.types import Exchange

        router = SmartRouter()
        # XBSE (Beijing Stock Exchange) is not supported by any balance_sheet provider
        providers = router._resolve_providers("balance_sheet", Exchange.XBSE, None)
        assert providers == [], "Expected no providers for balance_sheet on XBSE"

        # Verify NoProviderError attributes work correctly
        err = NoProviderError(
            model_name="balance_sheet",
            exchange=Exchange.XBSE,
            requested_provider=None,
            available_providers=["yfinance"],
        )
        assert err.code == "NO_PROVIDER"
        assert "balance_sheet" in str(err)


# ──────────────────────────────────────────────
# 4. SDK coercion error friendliness
# ──────────────────────────────────────────────


class TestSDKCoercionErrors:
    """Verify SDK-layer coercion errors guide AI callers."""

    def test_invalid_interval(self):
        from unifin.core.errors import InvalidEnumValueError

        with pytest.raises(InvalidEnumValueError) as exc_info:
            import unifin

            unifin.equity.historical("AAPL", interval="2h")
        e = exc_info.value
        assert e.code == "INVALID_ENUM_VALUE"
        assert "1d" in str(e)
        assert "2h" in str(e)

    def test_invalid_adjust(self):
        from unifin.core.errors import InvalidEnumValueError

        with pytest.raises(InvalidEnumValueError) as exc_info:
            import unifin

            unifin.equity.historical("AAPL", adjust="split")
        e = exc_info.value
        assert "none" in str(e) or "qfq" in str(e)

    def test_invalid_period(self):
        from unifin.core.errors import InvalidEnumValueError

        with pytest.raises(InvalidEnumValueError) as exc_info:
            import unifin

            unifin.equity.balance_sheet("AAPL", period="monthly")
        e = exc_info.value
        assert "annual" in str(e) or "quarter" in str(e)

    def test_invalid_market(self):
        from unifin.core.errors import InvalidEnumValueError

        with pytest.raises(InvalidEnumValueError) as exc_info:
            import unifin

            unifin.market.trade_calendar(market="mars")
        e = exc_info.value
        assert "cn" in str(e) or "us" in str(e)

    def test_invalid_date_format(self):
        from unifin.core.errors import InvalidDateFormatError

        with pytest.raises(InvalidDateFormatError) as exc_info:
            import unifin

            unifin.equity.historical("AAPL", start_date="yesterday")
        e = exc_info.value
        assert e.code == "INVALID_DATE_FORMAT"
        assert "YYYY-MM-DD" in str(e)
        assert "yesterday" in str(e)

    def test_invalid_date_format_end(self):
        from unifin.core.errors import InvalidDateFormatError

        with pytest.raises(InvalidDateFormatError) as exc_info:
            import unifin

            unifin.equity.historical("AAPL", end_date="2024/12/31")
        e = exc_info.value
        assert "end_date" in str(e)

    def test_index_invalid_date(self):
        from unifin.core.errors import InvalidDateFormatError

        with pytest.raises(InvalidDateFormatError):
            import unifin

            unifin.index.historical("^GSPC", start_date="bad")

    def test_market_invalid_date(self):
        from unifin.core.errors import InvalidDateFormatError

        with pytest.raises(InvalidDateFormatError):
            import unifin

            unifin.market.trade_calendar(start_date="nope")


# ──────────────────────────────────────────────
# 5. Model validation error friendliness
# ──────────────────────────────────────────────


class TestModelValidationErrors:
    """Verify model validators produce AI-friendly messages."""

    def test_equity_historical_date_range(self):
        from pydantic import ValidationError

        from unifin.models.equity_historical import EquityHistoricalQuery

        with pytest.raises(ValidationError) as exc_info:
            EquityHistoricalQuery(
                symbol="AAPL",
                start_date=date(2025, 6, 1),
                end_date=date(2024, 1, 1),
            )
        msg = str(exc_info.value)
        assert "start_date" in msg

    def test_index_historical_date_range(self):
        from pydantic import ValidationError

        from unifin.models.index_historical import IndexHistoricalQuery

        with pytest.raises(ValidationError) as exc_info:
            IndexHistoricalQuery(
                symbol="^GSPC",
                start_date=date(2025, 6, 1),
                end_date=date(2024, 1, 1),
            )
        msg = str(exc_info.value)
        assert "start_date" in msg

    def test_trade_calendar_date_range(self):
        from pydantic import ValidationError

        from unifin.models.trade_calendar import TradeCalendarQuery

        with pytest.raises(ValidationError) as exc_info:
            TradeCalendarQuery(
                start_date=date(2025, 6, 1),
                end_date=date(2024, 1, 1),
            )
        msg = str(exc_info.value)
        assert "start_date" in msg


# ──────────────────────────────────────────────
# 6. Error inheritance chain
# ──────────────────────────────────────────────


class TestErrorInheritance:
    """Verify callers can catch errors at different granularity levels."""

    def test_symbol_error_caught_as_unifin_error(self):
        from unifin.core.errors import SymbolError, UnifinError

        e = SymbolError("test", received="bad")
        assert isinstance(e, UnifinError)
        assert isinstance(e, ValueError)

    def test_provider_errors_caught_as_unifin_error(self):
        from unifin.core.errors import (
            AllProvidersFailedError,
            NoProviderError,
            ProviderError,
            ProviderNotFoundError,
            UnifinError,
        )

        for cls in [ProviderNotFoundError, NoProviderError]:
            if cls == ProviderNotFoundError:
                e = cls("test", [])
            else:
                e = cls("test")
            assert isinstance(e, ProviderError)
            assert isinstance(e, UnifinError)

    def test_param_errors_caught_as_unifin_error(self):
        from unifin.core.errors import (
            InvalidDateFormatError,
            InvalidDateRangeError,
            InvalidEnumValueError,
            ParamError,
            UnifinError,
        )
        from unifin.core.types import Interval

        errors = [
            InvalidDateRangeError(date(2025, 1, 1), date(2024, 1, 1)),
            InvalidEnumValueError("interval", "2h", Interval),
            InvalidDateFormatError("start_date", "bad"),
        ]
        for e in errors:
            assert isinstance(e, ParamError)
            assert isinstance(e, UnifinError)
            assert isinstance(e, ValueError)

    def test_model_fetcher_errors_caught_as_unifin_error(self):
        from unifin.core.errors import (
            FetcherNotFoundError,
            ModelNotFoundError,
            UnifinError,
        )

        e1 = ModelNotFoundError("test", [])
        e2 = FetcherNotFoundError("test", "prov", [])
        assert isinstance(e1, UnifinError)
        assert isinstance(e2, UnifinError)
