"""Income Statement — core data model.

Standardized income statement / profit & loss statement.
"""

import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from unifin.core.registry import ModelInfo, model_registry
from unifin.core.symbol import validate_symbol
from unifin.core.types import Period


class IncomeStatementQuery(BaseModel):
    """Query parameters for income statement."""

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


class IncomeStatementData(BaseModel):
    """Result schema for income statement data."""

    symbol: Optional[str] = Field(default=None, description="Stock ticker symbol.")
    period_ending: dt.date = Field(description="End date of the reporting period.")
    fiscal_period: Optional[str] = Field(default=None, description="Fiscal period label (e.g., 'Q1', 'FY').")
    fiscal_year: Optional[int] = Field(default=None, description="Fiscal year.")

    # ── Revenue ──
    total_revenue: Optional[float] = Field(default=None, description="Total revenue / operating income.")
    cost_of_revenue: Optional[float] = Field(default=None, description="Cost of goods sold / operating cost.")
    gross_profit: Optional[float] = Field(default=None, description="Gross profit.")

    # ── Operating Expenses ──
    research_and_development: Optional[float] = Field(default=None, description="R&D expense.")
    selling_general_admin: Optional[float] = Field(default=None, description="SG&A expense.")
    total_operating_expenses: Optional[float] = Field(default=None, description="Total operating expenses.")
    operating_income: Optional[float] = Field(default=None, description="Operating income / profit.")

    # ── Non-Operating ──
    interest_income: Optional[float] = Field(default=None, description="Interest income.")
    interest_expense: Optional[float] = Field(default=None, description="Interest expense.")
    other_income: Optional[float] = Field(default=None, description="Other non-operating income/expense.")

    # ── Earnings ──
    income_before_tax: Optional[float] = Field(default=None, description="Income before income tax.")
    income_tax: Optional[float] = Field(default=None, description="Income tax expense.")
    net_income: Optional[float] = Field(default=None, description="Net income / net profit.")
    net_income_continuing: Optional[float] = Field(default=None, description="Net income from continuing operations.")
    total_comprehensive_income: Optional[float] = Field(default=None, description="Total comprehensive income.")

    # ── Per Share ──
    basic_eps: Optional[float] = Field(default=None, description="Basic earnings per share.")
    diluted_eps: Optional[float] = Field(default=None, description="Diluted earnings per share.")

    # ── Margins ──
    gross_profit_margin: Optional[float] = Field(default=None, description="Gross profit margin (ratio).")
    net_income_margin: Optional[float] = Field(default=None, description="Net income margin (ratio).")
    ebitda: Optional[float] = Field(default=None, description="EBITDA.")
    depreciation_and_amortization: Optional[float] = Field(default=None, description="Depreciation & amortization.")


model_registry.register(
    ModelInfo(
        name="income_statement",
        category="equity.fundamental",
        query_type=IncomeStatementQuery,
        result_type=IncomeStatementData,
        description="Income statement / profit & loss.",
    )
)
