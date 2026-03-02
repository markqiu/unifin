"""Index Historical — core data model.

Historical OHLCV price data for market indices.
"""

import datetime as dt
from typing import Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from unifin.core.registry import ModelInfo, model_registry
from unifin.core.symbol import validate_symbol
from unifin.core.types import Interval


class IndexHistoricalQuery(BaseModel):
    """Query parameters for index historical price data."""

    symbol: str = Field(
        ...,
        description="Index symbol (e.g., '000001.XSHG' for SSE Composite, '^GSPC' for S&P 500).",
    )

    @field_validator("symbol")
    @classmethod
    def _check_symbol(cls, v: str) -> str:
        return validate_symbol(v)
    start_date: Optional[dt.date] = Field(
        default=None,
        description="Start date (inclusive). Defaults to 1 year ago.",
    )
    end_date: Optional[dt.date] = Field(
        default=None,
        description="End date (inclusive). Defaults to today.",
    )
    interval: Interval = Field(
        default=Interval.DAILY,
        description="Bar interval / frequency.",
    )

    @model_validator(mode="after")
    def _validate_dates(self) -> "IndexHistoricalQuery":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            from unifin.core.errors import InvalidDateRangeError

            raise InvalidDateRangeError(self.start_date, self.end_date)
        return self


class IndexHistoricalData(BaseModel):
    """Result schema for index historical price data."""

    date: Union[dt.date, dt.datetime] = Field(description="Bar timestamp.")
    open: Optional[float] = Field(default=None, description="Opening price.")
    high: Optional[float] = Field(default=None, description="Highest price.")
    low: Optional[float] = Field(default=None, description="Lowest price.")
    close: Optional[float] = Field(default=None, description="Closing price.")
    volume: Optional[int] = Field(default=None, description="Trading volume.")
    amount: Optional[float] = Field(default=None, description="Turnover amount (currency).")
    change: Optional[float] = Field(default=None, description="Price change from previous close.")
    change_percent: Optional[float] = Field(default=None, description="Price change percentage.")
    symbol: Optional[str] = Field(default=None, description="Index symbol.")


model_registry.register(
    ModelInfo(
        name="index_historical",
        category="index",
        query_type=IndexHistoricalQuery,
        result_type=IndexHistoricalData,
        description="Historical OHLCV price data for market indices.",
    )
)
