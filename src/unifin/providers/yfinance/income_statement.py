"""YFinance fetcher for income_statement."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange


class YFinanceIncomeStatementFetcher(Fetcher):
    """Fetch income statement data from Yahoo Finance."""

    provider_name: ClassVar[str] = "yfinance"
    model_name: ClassVar[str] = "income_statement"
    supported_exchanges: ClassVar[list[Exchange]] = [
        Exchange.XNYS,
        Exchange.XNAS,
        Exchange.XASE,
        Exchange.ARCX,
        Exchange.XSHG,
        Exchange.XSHE,
        Exchange.XHKG,
        Exchange.XJPX,
        Exchange.XLON,
        Exchange.XPAR,
        Exchange.XAMS,
        Exchange.XETR,
        Exchange.XSWX,
        Exchange.XMIL,
        Exchange.XSES,
        Exchange.XASX,
        Exchange.XKRX,
        Exchange.XTAI,
        Exchange.XBOM,
        Exchange.XNSE,
        Exchange.XTSE,
    ]

    # Coverage metadata
    supported_fields: ClassVar[list[str]] = [
        "period_ending",
        "fiscal_period",
        "fiscal_year",
        "total_revenue",
        "cost_of_revenue",
        "gross_profit",
        "research_and_development",
        "selling_general_admin",
        "total_operating_expenses",
        "operating_income",
        "interest_income",
        "interest_expense",
        "other_income",
        "income_before_tax",
        "income_tax",
        "net_income",
        "basic_eps",
        "diluted_eps",
        "gross_profit_margin",
        "net_income_margin",
        "ebitda",
        "depreciation_and_amortization",
    ]
    data_start_date: ClassVar[str] = "2000-01-01"
    data_delay: ClassVar[str] = "eod"
    notes: ClassVar[str] = (
        "Typically provides 4 annual or 4-5 quarterly periods. "
        "Margins are computed from raw revenue/profit data. "
        "net_income_continuing and total_comprehensive_income may be None for some companies."
    )

    @staticmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        period = getattr(query, "period", "annual")
        limit = getattr(query, "limit", 5)
        return {
            "symbol": getattr(query, "symbol", ""),
            "period": period,
            "limit": limit or 5,
        }

    @staticmethod
    def extract_data(params: dict[str, Any], credentials: dict[str, str] | None = None) -> Any:
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("yfinance is not installed. pip install 'unifin[yfinance]'")

        ticker = yf.Ticker(params["symbol"])
        if params["period"] == "quarter":
            df = ticker.quarterly_income_stmt
        else:
            df = ticker.income_stmt

        if df is None or df.empty:
            return None
        return df

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        if raw_data is None:
            return []

        import pandas as pd

        df = raw_data
        if not isinstance(df, pd.DataFrame):
            return []

        limit = getattr(query, "limit", 5) or 5
        period_type = getattr(query, "period", "annual")

        results = []
        for col_date in list(df.columns)[:limit]:
            col = df[col_date]
            dt_val = col_date.date() if isinstance(col_date, pd.Timestamp) else col_date

            total_rev = _g(col, "Total Revenue")
            cost_rev = _g(col, "Cost Of Revenue")
            gross = _g(col, "Gross Profit")
            net = _g(col, "Net Income")

            # Compute margins if possible
            gross_margin = None
            net_margin = None
            if total_rev and total_rev != 0:
                if gross is not None:
                    gross_margin = gross / total_rev
                if net is not None:
                    net_margin = net / total_rev

            results.append(
                {
                    "period_ending": dt_val,
                    "fiscal_period": "FY" if period_type == "annual" else "Q",
                    "fiscal_year": dt_val.year if hasattr(dt_val, "year") else None,
                    "total_revenue": total_rev,
                    "cost_of_revenue": cost_rev,
                    "gross_profit": gross,
                    "research_and_development": _g(col, "Research And Development"),
                    "selling_general_admin": _g(col, "Selling General And Administration"),
                    "total_operating_expenses": _g(col, "Total Expenses", "Operating Expense"),
                    "operating_income": _g(col, "Operating Income"),
                    "interest_income": _g(col, "Interest Income"),
                    "interest_expense": _g(col, "Interest Expense"),
                    "other_income": _g(
                        col, "Other Income Expense", "Other Non Operating Income Expenses"
                    ),
                    "income_before_tax": _g(col, "Pretax Income"),
                    "income_tax": _g(col, "Tax Provision"),
                    "net_income": net,
                    "net_income_continuing": _g(col, "Net Income Continuous Operations"),
                    "total_comprehensive_income": _g(
                        col, "Net Income Including Noncontrolling Interests"
                    ),
                    "basic_eps": _g(col, "Basic EPS"),
                    "diluted_eps": _g(col, "Diluted EPS"),
                    "gross_profit_margin": gross_margin,
                    "net_income_margin": net_margin,
                    "ebitda": _g(col, "EBITDA"),
                    "depreciation_and_amortization": _g(col, "Reconciled Depreciation"),
                }
            )

        return results


def _g(col: Any, *keys: str) -> float | None:
    """Get first matching value from a pandas Series by multiple possible keys."""
    for key in keys:
        try:
            v = col.get(key)
            if v is not None:
                f = float(v)
                if f == f:  # NaN check
                    return f
        except (KeyError, ValueError, TypeError):
            continue
    return None


provider_registry.register_fetcher(YFinanceIncomeStatementFetcher)
