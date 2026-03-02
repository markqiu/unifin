"""Equity Search — core data model.

Search for stocks by name, ticker symbol, or other identifiers.
"""

import datetime as dt

from pydantic import BaseModel, Field

from unifin.core.registry import ModelInfo, model_registry


class EquitySearchQuery(BaseModel):
    """Query parameters for equity search."""

    query: str = Field(
        default="",
        description="Search query — name, symbol, or keyword.",
    )
    is_symbol: bool = Field(
        default=False,
        description="Whether to search by ticker symbol only.",
    )
    limit: int | None = Field(
        default=None,
        description="Maximum number of results to return.",
    )


class EquitySearchData(BaseModel):
    """Result schema for equity search."""

    symbol: str | None = Field(default=None, description="Stock ticker symbol.")
    name: str | None = Field(default=None, description="Company name.")
    exchange: str | None = Field(default=None, description="Exchange / market.")
    asset_type: str | None = Field(default=None, description="Asset type (e.g., Stock, ETF).")
    list_date: dt.date | None = Field(default=None, description="IPO / listing date.")
    is_active: bool | None = Field(
        default=None, description="Whether the security is actively trading."
    )


model_registry.register(
    ModelInfo(
        name="equity_search",
        category="equity",
        query_type=EquitySearchQuery,
        result_type=EquitySearchData,
        description="Search for stocks by name, code, or keyword.",
    )
)
