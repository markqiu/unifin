"""Equity Search — core data model.

Search for stocks by name, ticker symbol, or other identifiers.
"""

import datetime as dt
from typing import Optional

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
    limit: Optional[int] = Field(
        default=None,
        description="Maximum number of results to return.",
    )


class EquitySearchData(BaseModel):
    """Result schema for equity search."""

    symbol: Optional[str] = Field(default=None, description="Stock ticker symbol.")
    name: Optional[str] = Field(default=None, description="Company name.")
    exchange: Optional[str] = Field(default=None, description="Exchange / market.")
    asset_type: Optional[str] = Field(default=None, description="Asset type (e.g., Stock, ETF).")
    list_date: Optional[dt.date] = Field(default=None, description="IPO / listing date.")
    is_active: Optional[bool] = Field(default=None, description="Whether the security is actively trading.")


model_registry.register(
    ModelInfo(
        name="equity_search",
        category="equity",
        query_type=EquitySearchQuery,
        result_type=EquitySearchData,
        description="Search for stocks by name, code, or keyword.",
    )
)
