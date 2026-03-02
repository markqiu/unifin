"""Market SDK — unifin.market.*

Usage:
    import unifin

    df = unifin.market.trade_calendar(market="cn", start_date="2024-01-01")
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from unifin.core.router import router
from unifin.core.types import Market

if TYPE_CHECKING:
    import polars as pl


def trade_calendar(
    market: str | Market = Market.CN,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    provider: str | None = None,
) -> pl.DataFrame:
    """Get trading calendar for a market.

    Args:
        market: Market identifier ('cn', 'us', 'hk', ...).
        start_date: Start date.
        end_date: End date.
        provider: Explicit provider name.

    Returns:
        Polars DataFrame: date, is_open, market.
    """
    import polars as pl

    from unifin.core.errors import InvalidDateFormatError, InvalidEnumValueError
    from unifin.models.trade_calendar import TradeCalendarQuery

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
    if isinstance(market, str):
        try:
            market = Market(market)
        except ValueError:
            raise InvalidEnumValueError("market", market, Market)

    q = TradeCalendarQuery(
        market=market,
        start_date=start_date,
        end_date=end_date,
    )
    results = router.query("trade_calendar", q, provider=provider)
    return pl.DataFrame(results) if results else pl.DataFrame()
