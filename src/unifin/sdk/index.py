"""Index SDK — unifin.index.*

Usage:
    import unifin

    df = unifin.index.historical("000001.XSHG", start_date="2024-01-01")
    df = unifin.index.historical("^GSPC", start_date="2024-01-01")
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from unifin.core.router import router
from unifin.core.types import Interval

if TYPE_CHECKING:
    import polars as pl


def historical(
    symbol: str,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    interval: str | Interval = Interval.DAILY,
    provider: str | None = None,
) -> "pl.DataFrame":
    """Get historical price data for a market index.

    Args:
        symbol: Index symbol (e.g., '000001.XSHG', '^GSPC', '^HSI').
        start_date: Start date (inclusive). Defaults to 1 year ago.
        end_date: End date (inclusive). Defaults to today.
        interval: Bar interval.
        provider: Explicit provider name.

    Returns:
        Polars DataFrame: date, open, high, low, close, volume, ...
    """
    import polars as pl

    from unifin.core.errors import InvalidDateFormatError, InvalidEnumValueError
    from unifin.models.index_historical import IndexHistoricalQuery

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
    if isinstance(interval, str):
        try:
            interval = Interval(interval)
        except ValueError:
            raise InvalidEnumValueError("interval", interval, Interval)

    q = IndexHistoricalQuery(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
    )
    results = router.query("index_historical", q, provider=provider)
    return pl.DataFrame(results) if results else pl.DataFrame()
