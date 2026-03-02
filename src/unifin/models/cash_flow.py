"""Cash Flow Statement — core data model.

Standardized cash flow statement.
"""

import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from unifin.core.registry import ModelInfo, model_registry
from unifin.core.symbol import validate_symbol
from unifin.core.types import Period


class CashFlowQuery(BaseModel):
    """Query parameters for cash flow statement."""

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


class CashFlowData(BaseModel):
    """Result schema for cash flow statement data."""

    symbol: Optional[str] = Field(default=None, description="Stock ticker symbol.")
    period_ending: dt.date = Field(description="End date of the reporting period.")
    fiscal_period: Optional[str] = Field(default=None, description="Fiscal period label (e.g., 'Q1', 'FY').")
    fiscal_year: Optional[int] = Field(default=None, description="Fiscal year.")

    # ── Operating Activities ──
    net_income: Optional[float] = Field(default=None, description="Net income (starting point).")
    depreciation_and_amortization: Optional[float] = Field(default=None, description="Depreciation & amortization.")
    stock_based_compensation: Optional[float] = Field(default=None, description="Stock-based compensation.")
    change_in_working_capital: Optional[float] = Field(default=None, description="Change in working capital.")
    net_cash_from_operations: Optional[float] = Field(default=None, description="Net cash from operating activities.")

    # ── Investing Activities ──
    capital_expenditure: Optional[float] = Field(default=None, description="Capital expenditure (CapEx).")
    acquisitions: Optional[float] = Field(default=None, description="Acquisitions.")
    purchase_of_investments: Optional[float] = Field(default=None, description="Purchase of investment securities.")
    sale_of_investments: Optional[float] = Field(default=None, description="Sale / maturity of investments.")
    net_cash_from_investing: Optional[float] = Field(default=None, description="Net cash from investing activities.")

    # ── Financing Activities ──
    issuance_of_debt: Optional[float] = Field(default=None, description="Proceeds from debt issuance.")
    repayment_of_debt: Optional[float] = Field(default=None, description="Repayment of debt.")
    issuance_of_equity: Optional[float] = Field(default=None, description="Proceeds from equity issuance.")
    share_repurchase: Optional[float] = Field(default=None, description="Share buyback / repurchase.")
    dividends_paid: Optional[float] = Field(default=None, description="Dividends paid.")
    net_cash_from_financing: Optional[float] = Field(default=None, description="Net cash from financing activities.")

    # ── Summary ──
    effect_of_exchange_rates: Optional[float] = Field(default=None, description="Effect of exchange rate changes on cash.")
    net_change_in_cash: Optional[float] = Field(default=None, description="Net change in cash and equivalents.")
    cash_at_beginning: Optional[float] = Field(default=None, description="Cash at beginning of period.")
    cash_at_end: Optional[float] = Field(default=None, description="Cash at end of period.")
    free_cash_flow: Optional[float] = Field(default=None, description="Free cash flow (operating - CapEx).")


model_registry.register(
    ModelInfo(
        name="cash_flow",
        category="equity.fundamental",
        query_type=CashFlowQuery,
        result_type=CashFlowData,
        description="Cash flow statement.",
    )
)
