"""ETF Search — core data model.

Search for exchange-traded funds by name or code.
"""

import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field

from unifin.core.registry import ModelInfo, model_registry


class EtfSearchQuery(BaseModel):
    """Query parameters for ETF search."""

    query: str = Field(
        default="",
        description="Search query — name, symbol, or keyword.",
    )
    limit: Optional[int] = Field(
        default=None,
        description="Maximum number of results to return.",
    )


class EtfSearchData(BaseModel):
    """Result schema for ETF search."""

    symbol: str = Field(description="ETF ticker symbol.")
    name: Optional[str] = Field(default=None, description="ETF name.")
    exchange: Optional[str] = Field(default=None, description="Exchange / market.")
    fund_family: Optional[str] = Field(default=None, description="Fund family / management company.")
    fund_type: Optional[str] = Field(default=None, description="Fund category / type.")
    list_date: Optional[dt.date] = Field(default=None, description="Listing date.")
    expense_ratio: Optional[float] = Field(default=None, description="Annual expense ratio.")
    total_assets: Optional[float] = Field(default=None, description="Total net assets.")


model_registry.register(
    ModelInfo(
        name="etf_search",
        category="etf",
        query_type=EtfSearchQuery,
        result_type=EtfSearchData,
        description="Search for ETFs by name, code, or keyword.",
    )
)
