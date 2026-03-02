"""Balance Sheet — core data model.

Standardized balance sheet / statement of financial position.
"""

import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from unifin.core.registry import ModelInfo, model_registry
from unifin.core.symbol import validate_symbol
from unifin.core.types import Period


class BalanceSheetQuery(BaseModel):
    """Query parameters for balance sheet."""

    symbol: str = Field(
        ...,
        description="Stock symbol in unified format.",
    )

    @field_validator("symbol")
    @classmethod
    def _check_symbol(cls, v: str) -> str:
        return validate_symbol(v)
    period: Period = Field(
        default=Period.ANNUAL,
        description="Reporting period.",
    )
    limit: Optional[int] = Field(
        default=5,
        description="Number of periods to return.",
    )


class BalanceSheetData(BaseModel):
    """Result schema for balance sheet data."""

    symbol: Optional[str] = Field(default=None, description="Stock ticker symbol.")
    period_ending: dt.date = Field(description="End date of the reporting period.")
    fiscal_period: Optional[str] = Field(default=None, description="Fiscal period label (e.g., 'Q1', 'FY').")
    fiscal_year: Optional[int] = Field(default=None, description="Fiscal year.")

    # ── Current Assets ──
    cash_and_equivalents: Optional[float] = Field(default=None, description="Cash and cash equivalents.")
    accounts_receivable: Optional[float] = Field(default=None, description="Accounts receivable.")
    inventory: Optional[float] = Field(default=None, description="Inventory.")
    prepaid_expenses: Optional[float] = Field(default=None, description="Prepaid expenses.")
    other_current_assets: Optional[float] = Field(default=None, description="Other current assets.")
    total_current_assets: Optional[float] = Field(default=None, description="Total current assets.")

    # ── Non-current Assets ──
    property_plant_equipment: Optional[float] = Field(default=None, description="Property, plant & equipment (net).")
    intangible_assets: Optional[float] = Field(default=None, description="Intangible assets.")
    goodwill: Optional[float] = Field(default=None, description="Goodwill.")
    other_non_current_assets: Optional[float] = Field(default=None, description="Other non-current assets.")
    total_non_current_assets: Optional[float] = Field(default=None, description="Total non-current assets.")
    total_assets: Optional[float] = Field(default=None, description="Total assets.")

    # ── Current Liabilities ──
    accounts_payable: Optional[float] = Field(default=None, description="Accounts payable.")
    short_term_debt: Optional[float] = Field(default=None, description="Short-term debt / borrowings.")
    other_current_liabilities: Optional[float] = Field(default=None, description="Other current liabilities.")
    total_current_liabilities: Optional[float] = Field(default=None, description="Total current liabilities.")

    # ── Non-current Liabilities ──
    long_term_debt: Optional[float] = Field(default=None, description="Long-term debt / borrowings.")
    other_non_current_liabilities: Optional[float] = Field(default=None, description="Other non-current liabilities.")
    total_non_current_liabilities: Optional[float] = Field(default=None, description="Total non-current liabilities.")
    total_liabilities: Optional[float] = Field(default=None, description="Total liabilities.")

    # ── Equity ──
    minority_interest: Optional[float] = Field(default=None, description="Minority / non-controlling interest.")
    retained_earnings: Optional[float] = Field(default=None, description="Retained earnings.")
    total_shareholders_equity: Optional[float] = Field(default=None, description="Total shareholders' equity.")
    total_liabilities_and_equity: Optional[float] = Field(default=None, description="Total liabilities and shareholders' equity.")
    net_debt: Optional[float] = Field(default=None, description="Net debt (total debt - cash).")


model_registry.register(
    ModelInfo(
        name="balance_sheet",
        category="equity.fundamental",
        query_type=BalanceSheetQuery,
        result_type=BalanceSheetData,
        description="Balance sheet / statement of financial position.",
    )
)
