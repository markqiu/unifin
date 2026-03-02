"""Equity Quote — core data model.

Real-time or delayed price quote for equities.
"""

import datetime as dt
from typing import Optional, Union

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
    name: Optional[str] = Field(default=None, description="Company name.")
    exchange: Optional[str] = Field(default=None, description="Exchange venue.")
    asset_type: Optional[str] = Field(default=None, description="Asset type.")
    last_price: Optional[float] = Field(default=None, description="Last trade price.")
    open: Optional[float] = Field(default=None, description="Open price of the day.")
    high: Optional[float] = Field(default=None, description="High price of the day.")
    low: Optional[float] = Field(default=None, description="Low price of the day.")
    close: Optional[float] = Field(default=None, description="Close price (or latest for intraday).")
    prev_close: Optional[float] = Field(default=None, description="Previous close price.")
    volume: Optional[int] = Field(default=None, description="Trading volume.")
    amount: Optional[float] = Field(default=None, description="Turnover amount (currency).")
    change: Optional[float] = Field(default=None, description="Change from previous close.")
    change_percent: Optional[float] = Field(default=None, description="Change percentage (normalized 0-1).")
    bid: Optional[float] = Field(default=None, description="Best bid price.")
    bid_size: Optional[int] = Field(default=None, description="Bid size in lots.")
    ask: Optional[float] = Field(default=None, description="Best ask price.")
    ask_size: Optional[int] = Field(default=None, description="Ask size in lots.")
    year_high: Optional[float] = Field(default=None, description="52-week high.")
    year_low: Optional[float] = Field(default=None, description="52-week low.")
    market_cap: Optional[float] = Field(default=None, description="Market capitalization.")
    timestamp: Optional[Union[dt.date, dt.datetime]] = Field(default=None, description="Quote timestamp.")


model_registry.register(
    ModelInfo(
        name="equity_quote",
        category="equity.price",
        query_type=EquityQuoteQuery,
        result_type=EquityQuoteData,
        description="Real-time or delayed equity price quote.",
    )
)
