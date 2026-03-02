"""Trade Calendar — core data model.

Query trading calendar / trading days for a given market.
"""

import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from unifin.core.registry import ModelInfo, model_registry
from unifin.core.types import Market


class TradeCalendarQuery(BaseModel):
    """Query parameters for trade calendar."""

    market: Market = Field(
        default=Market.CN,
        description="Market identifier.",
    )
    start_date: Optional[dt.date] = Field(
        default=None,
        description="Start date (inclusive).",
    )
    end_date: Optional[dt.date] = Field(
        default=None,
        description="End date (inclusive).",
    )

    @model_validator(mode="after")
    def _validate_dates(self) -> "TradeCalendarQuery":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            from unifin.core.errors import InvalidDateRangeError

            raise InvalidDateRangeError(self.start_date, self.end_date)
        return self


class TradeCalendarData(BaseModel):
    """Result schema for trade calendar — one row per trading day."""

    date: dt.date = Field(description="Trading date.")
    is_open: bool = Field(default=True, description="Whether the market is open on this day.")
    market: Optional[str] = Field(default=None, description="Market identifier.")


model_registry.register(
    ModelInfo(
        name="trade_calendar",
        category="market",
        query_type=TradeCalendarQuery,
        result_type=TradeCalendarData,
        description="Trading calendar — list of trading days for a market.",
    )
)
