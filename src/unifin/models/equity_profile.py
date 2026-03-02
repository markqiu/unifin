"""Equity Profile — core data model.

Company profile / basic information.
"""

import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from unifin.core.registry import ModelInfo, model_registry
from unifin.core.symbol import validate_symbol


class EquityProfileQuery(BaseModel):
    """Query parameters for equity profile."""

    symbol: str = Field(
        ...,
        description="Stock symbol in unified format.",
    )

    @field_validator("symbol")
    @classmethod
    def _check_symbol(cls, v: str) -> str:
        return validate_symbol(v)


class EquityProfileData(BaseModel):
    """Result schema for equity profile / company info."""

    symbol: str = Field(description="Stock ticker symbol.")
    name: Optional[str] = Field(default=None, description="Company name.")
    legal_name: Optional[str] = Field(default=None, description="Official legal name.")
    exchange: Optional[str] = Field(default=None, description="Primary exchange.")
    sector: Optional[str] = Field(default=None, description="Industry sector.")
    industry: Optional[str] = Field(default=None, description="Industry category.")
    employees: Optional[int] = Field(default=None, description="Number of employees.")
    description: Optional[str] = Field(default=None, description="Company description / business summary.")
    country: Optional[str] = Field(default=None, description="Country of domicile.")
    city: Optional[str] = Field(default=None, description="Headquarters city.")
    website: Optional[str] = Field(default=None, description="Company website URL.")
    ceo: Optional[str] = Field(default=None, description="Chief Executive Officer.")
    market_cap: Optional[float] = Field(default=None, description="Market capitalization.")
    currency: Optional[str] = Field(default=None, description="Trading currency.")
    list_date: Optional[dt.date] = Field(default=None, description="IPO / listing date.")
    is_active: Optional[bool] = Field(default=None, description="Whether the company is actively trading.")


model_registry.register(
    ModelInfo(
        name="equity_profile",
        category="equity",
        query_type=EquityProfileQuery,
        result_type=EquityProfileData,
        description="Company profile and basic information.",
    )
)
