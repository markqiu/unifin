"""Equity Quote — core data model.

Real-time or delayed price quote for equities.
"""

import datetime as dt

from pydantic import BaseModel, Field, field_validator

from unifin.core.registry import ModelInfo, model_registry
from unifin.core.symbol import validate_symbol


class EquityQuoteQuery(BaseModel):
    """Query parameters for equity quote."""

    symbol: str = Field(
        ...,
        description="Stock symbol in unified format (supports comma-separated for multi-symbol).",
    )

    @field_validator("symbol")
    @classmethod
    def _check_symbol(cls, v: str) -> str:
        return validate_symbol(v)


class EquityQuoteData(BaseModel):
    """Result schema for equity quote."""

    symbol: str = Field(description="Stock ticker symbol.")
    name: str | None = Field(default=None, description="Company name.")
    exchange: str | None = Field(default=None, description="Exchange venue.")
    asset_type: str | None = Field(default=None, description="Asset type.")
    last_price: float | None = Field(default=None, description="Last trade price.")
    open: float | None = Field(default=None, description="Open price of the day.")
    high: float | None = Field(default=None, description="High price of the day.")
    low: float | None = Field(default=None, description="Low price of the day.")
    close: float | None = Field(default=None, description="Close price (or latest for intraday).")
    prev_close: float | None = Field(default=None, description="Previous close price.")
    volume: int | None = Field(default=None, description="Trading volume.")
    amount: float | None = Field(default=None, description="Turnover amount (currency).")
    change: float | None = Field(default=None, description="Change from previous close.")
    change_percent: float | None = Field(
        default=None, description="Change percentage (normalized 0-1)."
    )
    bid: float | None = Field(default=None, description="Best bid price.")
    bid_size: int | None = Field(default=None, description="Bid size in lots.")
    ask: float | None = Field(default=None, description="Best ask price.")
    ask_size: int | None = Field(default=None, description="Ask size in lots.")
    year_high: float | None = Field(default=None, description="52-week high.")
    year_low: float | None = Field(default=None, description="52-week low.")
    market_cap: float | None = Field(default=None, description="Market capitalization.")
    timestamp: dt.date | dt.datetime | None = Field(default=None, description="Quote timestamp.")


model_registry.register(
    ModelInfo(
        name="equity_quote",
        category="equity.price",
        query_type=EquityQuoteQuery,
        result_type=EquityQuoteData,
        description="Real-time or delayed equity price quote.",
    )
)
