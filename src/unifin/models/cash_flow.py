"""Cash Flow Statement — core data model.

Standardized cash flow statement.
"""

import datetime as dt

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
    limit: int | None = Field(
        default=5,
        description="Number of periods to return.",
    )


class CashFlowData(BaseModel):
    """Result schema for cash flow statement data."""

    symbol: str | None = Field(default=None, description="Stock ticker symbol.")
    period_ending: dt.date = Field(description="End date of the reporting period.")
    fiscal_period: str | None = Field(
        default=None, description="Fiscal period label (e.g., 'Q1', 'FY')."
    )
    fiscal_year: int | None = Field(default=None, description="Fiscal year.")

    # ── Operating Activities ──
    net_income: float | None = Field(default=None, description="Net income (starting point).")
    depreciation_and_amortization: float | None = Field(
        default=None, description="Depreciation & amortization."
    )
    stock_based_compensation: float | None = Field(
        default=None, description="Stock-based compensation."
    )
    change_in_working_capital: float | None = Field(
        default=None, description="Change in working capital."
    )
    net_cash_from_operations: float | None = Field(
        default=None, description="Net cash from operating activities."
    )

    # ── Investing Activities ──
    capital_expenditure: float | None = Field(
        default=None, description="Capital expenditure (CapEx)."
    )
    acquisitions: float | None = Field(default=None, description="Acquisitions.")
    purchase_of_investments: float | None = Field(
        default=None, description="Purchase of investment securities."
    )
    sale_of_investments: float | None = Field(
        default=None, description="Sale / maturity of investments."
    )
    net_cash_from_investing: float | None = Field(
        default=None, description="Net cash from investing activities."
    )

    # ── Financing Activities ──
    issuance_of_debt: float | None = Field(default=None, description="Proceeds from debt issuance.")
    repayment_of_debt: float | None = Field(default=None, description="Repayment of debt.")
    issuance_of_equity: float | None = Field(
        default=None, description="Proceeds from equity issuance."
    )
    share_repurchase: float | None = Field(default=None, description="Share buyback / repurchase.")
    dividends_paid: float | None = Field(default=None, description="Dividends paid.")
    net_cash_from_financing: float | None = Field(
        default=None, description="Net cash from financing activities."
    )

    # ── Summary ──
    effect_of_exchange_rates: float | None = Field(
        default=None, description="Effect of exchange rate changes on cash."
    )
    net_change_in_cash: float | None = Field(
        default=None, description="Net change in cash and equivalents."
    )
    cash_at_beginning: float | None = Field(
        default=None, description="Cash at beginning of period."
    )
    cash_at_end: float | None = Field(default=None, description="Cash at end of period.")
    free_cash_flow: float | None = Field(
        default=None, description="Free cash flow (operating - CapEx)."
    )


model_registry.register(
    ModelInfo(
        name="cash_flow",
        category="equity.fundamental",
        query_type=CashFlowQuery,
        result_type=CashFlowData,
        description="Cash flow statement.",
    )
)
