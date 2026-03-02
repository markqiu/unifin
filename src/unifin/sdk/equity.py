"""Equity SDK — unifin.equity.*

Usage:
    import unifin

    df = unifin.equity.historical("000001.XSHE", start_date="2024-01-01")
    df = unifin.equity.historical("AAPL", start_date="2024-01-01")
    df = unifin.equity.historical("AAPL", provider="yfinance")
    df = unifin.equity.search("Apple")
    df = unifin.equity.profile("AAPL")
    df = unifin.equity.quote("AAPL")
    df = unifin.equity.balance_sheet("AAPL")
    df = unifin.equity.income_statement("AAPL")
    df = unifin.equity.cash_flow("AAPL")
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from unifin.core.router import router
from unifin.core.types import Adjust, Interval, Period

if TYPE_CHECKING:
    import polars as pl


def historical(
    symbol: str,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    interval: str | Interval = Interval.DAILY,
    adjust: str | Adjust = Adjust.NONE,
    provider: str | None = None,
    use_cache: bool = True,
) -> pl.DataFrame:
    """Get historical price data for an equity.

    Args:
        symbol: Stock symbol (e.g., '000001.XSHE', 'AAPL', '0700.XHKG').
        start_date: Start date (inclusive). Defaults to 1 year ago.
        end_date: End date (inclusive). Defaults to today.
        interval: Bar interval ('1m', '5m', '15m', '30m', '1h', '1d', '1w', '1M').
        adjust: Price adjustment ('none', 'qfq' forward, 'hfq' backward).
        provider: Explicit provider name. Auto-selected if None.
        use_cache: If True, check local DuckDB cache first.

    Returns:
        Polars DataFrame with columns: date, open, high, low, close, volume, amount, ...
    """
    import polars as pl

    from unifin.core.errors import InvalidDateFormatError, InvalidEnumValueError
    from unifin.models.equity_historical import EquityHistoricalQuery

    # Coerce string dates
    if isinstance(start_date, str):
        try:
            start_date = date.fromisoformat(start_date)
        except ValueError:
            raise InvalidDateFormatError("start_date", start_date)
    if isinstance(end_date, str):
        try:
            end_date = date.fromisoformat(end_date)
        except ValueError:
            raise InvalidDateFormatError("end_date", end_date)

    # Coerce string enums
    if isinstance(interval, str):
        try:
            interval = Interval(interval)
        except ValueError:
            raise InvalidEnumValueError("interval", interval, Interval)
    if isinstance(adjust, str):
        try:
            adjust = Adjust(adjust)
        except ValueError:
            raise InvalidEnumValueError("adjust", adjust, Adjust)

    query = EquityHistoricalQuery(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        adjust=adjust,
    )

    # Check local cache first
    if use_cache:
        from unifin.core.store import store
        from unifin.core.symbol import to_unified_symbol

        unified_sym = to_unified_symbol(symbol)
        cached = store.load(
            "equity_historical",
            symbol=unified_sym,
            start_date=str(start_date) if start_date else None,
            end_date=str(end_date) if end_date else None,
        )
        if cached:
            return pl.DataFrame(cached)

    # Route to provider
    results = router.query("equity_historical", query, provider=provider)

    if not results:
        return pl.DataFrame()

    # Save to cache
    if use_cache:
        from unifin.core.store import store

        try:
            store.save("equity_historical", results, symbol=symbol)
        except Exception:
            pass  # Cache failures are non-fatal

    return pl.DataFrame(results)


def search(
    query: str = "",
    is_symbol: bool = False,
    limit: int | None = None,
    provider: str | None = None,
) -> pl.DataFrame:
    """Search for equities by name or symbol.

    Args:
        query: Search keyword — company name, ticker, etc.
        is_symbol: If True, search by ticker symbol only.
        limit: Maximum results.
        provider: Explicit provider name.

    Returns:
        Polars DataFrame: symbol, name, exchange, asset_type, ...
    """
    import polars as pl

    from unifin.models.equity_search import EquitySearchQuery

    q = EquitySearchQuery(query=query, is_symbol=is_symbol, limit=limit)
    results = router.query("equity_search", q, provider=provider)
    return pl.DataFrame(results) if results else pl.DataFrame()


def profile(
    symbol: str,
    provider: str | None = None,
) -> pl.DataFrame:
    """Get company profile / basic information.

    Args:
        symbol: Stock symbol.
        provider: Explicit provider name.

    Returns:
        Polars DataFrame with company info.
    """
    import polars as pl

    from unifin.models.equity_profile import EquityProfileQuery

    q = EquityProfileQuery(symbol=symbol)
    results = router.query("equity_profile", q, provider=provider)
    return pl.DataFrame(results) if results else pl.DataFrame()


def quote(
    symbol: str,
    provider: str | None = None,
) -> pl.DataFrame:
    """Get real-time / delayed equity quote.

    Args:
        symbol: Stock symbol.
        provider: Explicit provider name.

    Returns:
        Polars DataFrame with quote data.
    """
    import polars as pl

    from unifin.models.equity_quote import EquityQuoteQuery

    q = EquityQuoteQuery(symbol=symbol)
    results = router.query("equity_quote", q, provider=provider)
    return pl.DataFrame(results) if results else pl.DataFrame()


def balance_sheet(
    symbol: str,
    period: str | Period = Period.ANNUAL,
    limit: int | None = 5,
    provider: str | None = None,
) -> pl.DataFrame:
    """Get balance sheet / statement of financial position.

    Args:
        symbol: Stock symbol.
        period: 'annual' or 'quarter'.
        limit: Number of periods.
        provider: Explicit provider name.

    Returns:
        Polars DataFrame with balance sheet data.
    """
    import polars as pl

    from unifin.core.errors import InvalidEnumValueError
    from unifin.models.balance_sheet import BalanceSheetQuery

    if isinstance(period, str):
        try:
            period = Period(period)
        except ValueError:
            raise InvalidEnumValueError("period", period, Period)

    q = BalanceSheetQuery(symbol=symbol, period=period, limit=limit)
    results = router.query("balance_sheet", q, provider=provider)
    return pl.DataFrame(results) if results else pl.DataFrame()


def income_statement(
    symbol: str,
    period: str | Period = Period.ANNUAL,
    limit: int | None = 5,
    provider: str | None = None,
) -> pl.DataFrame:
    """Get income statement / profit & loss.

    Args:
        symbol: Stock symbol.
        period: 'annual' or 'quarter'.
        limit: Number of periods.
        provider: Explicit provider name.

    Returns:
        Polars DataFrame with income statement data.
    """
    import polars as pl

    from unifin.core.errors import InvalidEnumValueError
    from unifin.models.income_statement import IncomeStatementQuery

    if isinstance(period, str):
        try:
            period = Period(period)
        except ValueError:
            raise InvalidEnumValueError("period", period, Period)

    q = IncomeStatementQuery(symbol=symbol, period=period, limit=limit)
    results = router.query("income_statement", q, provider=provider)
    return pl.DataFrame(results) if results else pl.DataFrame()


def cash_flow(
    symbol: str,
    period: str | Period = Period.ANNUAL,
    limit: int | None = 5,
    provider: str | None = None,
) -> pl.DataFrame:
    """Get cash flow statement.

    Args:
        symbol: Stock symbol.
        period: 'annual' or 'quarter'.
        limit: Number of periods.
        provider: Explicit provider name.

    Returns:
        Polars DataFrame with cash flow data.
    """
    import polars as pl

    from unifin.core.errors import InvalidEnumValueError
    from unifin.models.cash_flow import CashFlowQuery

    if isinstance(period, str):
        try:
            period = Period(period)
        except ValueError:
            raise InvalidEnumValueError("period", period, Period)

    q = CashFlowQuery(symbol=symbol, period=period, limit=limit)
    results = router.query("cash_flow", q, provider=provider)
    return pl.DataFrame(results) if results else pl.DataFrame()
