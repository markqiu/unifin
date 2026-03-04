"""Equity Historical Price — core data model.

Covers all timeframes (daily, weekly, monthly, minute-level) via the `interval` parameter.
This is the single most fundamental model in the platform.
"""

import datetime as dt

from pydantic import BaseModel, Field, field_validator, model_validator

from unifin.core.registry import ModelInfo, model_registry
from unifin.core.symbol import validate_symbol
from unifin.core.types import Adjust, Interval


class EquityHistoricalQuery(BaseModel):
    """Query parameters for equity historical price data."""

    symbol: str = Field(
        ...,
        description="Stock symbol in unified format (e.g., '000001.XSHE', 'AAPL').",
    )

    @field_validator("symbol")
    @classmethod
    def _check_symbol(cls, v: str) -> str:
        return validate_symbol(v)

    start_date: dt.date | None = Field(
        default=None,
        description="Start date (inclusive). Defaults to 1 year ago.",
    )
    end_date: dt.date | None = Field(
        default=None,
        description="End date (inclusive). Defaults to today.",
    )
    interval: Interval = Field(
        default=Interval.DAILY,
        description="Bar interval / frequency.",
    )
    adjust: Adjust = Field(
        default=Adjust.NONE,
        description="Price adjustment type.",
    )

    @model_validator(mode="after")
    def _validate_dates(self) -> "EquityHistoricalQuery":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            from unifin.core.errors import InvalidDateRangeError

            raise InvalidDateRangeError(self.start_date, self.end_date)
        return self


class EquityHistoricalData(BaseModel):
    """Result schema for equity historical price data."""

    date: dt.date | dt.datetime = Field(description="Bar timestamp.")
    open: float | None = Field(default=None, description="Opening price.")
    high: float | None = Field(default=None, description="Highest price.")
    low: float | None = Field(default=None, description="Lowest price.")
    close: float | None = Field(default=None, description="Closing price.")
    volume: int | None = Field(default=None, description="Trading volume (shares).")
    amount: float | None = Field(default=None, description="Trading amount (local currency).")
    vwap: float | None = Field(default=None, description="Volume-weighted average price.")
    turnover_rate: float | None = Field(default=None, description="Turnover rate (ratio, 0-1).")
    symbol: str | None = Field(default=None, description="Stock symbol in unified MIC format.")


# ── Register the model ──
model_registry.register(
    ModelInfo(
        name="equity_historical",
        category="equity.price",
        query_type=EquityHistoricalQuery,
        result_type=EquityHistoricalData,
        description=(
            "Historical OHLCV price data for equities, supporting daily to minute-level intervals."
        ),
    )
)
