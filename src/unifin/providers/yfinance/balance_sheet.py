"""YFinance fetcher for balance_sheet."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange


class YFinanceBalanceSheetFetcher(Fetcher):
    """Fetch balance sheet data from Yahoo Finance."""

    provider_name: ClassVar[str] = "yfinance"
    model_name: ClassVar[str] = "balance_sheet"
    supported_exchanges: ClassVar[list[Exchange]] = [
        Exchange.XNYS, Exchange.XNAS, Exchange.XASE, Exchange.ARCX,
        Exchange.XSHG, Exchange.XSHE,
        Exchange.XHKG,
        Exchange.XJPX, Exchange.XLON, Exchange.XPAR, Exchange.XAMS,
        Exchange.XETR, Exchange.XSWX, Exchange.XMIL,
        Exchange.XSES, Exchange.XASX, Exchange.XKRX, Exchange.XTAI,
        Exchange.XBOM, Exchange.XNSE, Exchange.XTSE,
    ]

    # Coverage metadata
    supported_fields: ClassVar[list[str]] = [
        "period_ending", "fiscal_period", "fiscal_year",
        "cash_and_equivalents", "accounts_receivable", "inventory",
        "total_current_assets", "property_plant_equipment", "intangible_assets",
        "goodwill", "total_non_current_assets", "total_assets",
        "accounts_payable", "short_term_debt", "total_current_liabilities",
        "long_term_debt", "total_non_current_liabilities", "total_liabilities",
        "minority_interest", "retained_earnings", "total_shareholders_equity",
        "total_liabilities_and_equity", "net_debt",
    ]
    data_start_date: ClassVar[str] = "2000-01-01"
    data_delay: ClassVar[str] = "eod"
    notes: ClassVar[str] = (
        "Typically provides 4 annual or 4-5 quarterly periods. "
        "Line item names may vary by company. Non-US coverage may be limited."
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
            df = ticker.quarterly_balance_sheet
        else:
            df = ticker.balance_sheet

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
        # yfinance balance_sheet: columns are dates, rows are line items
        for col_date in list(df.columns)[:limit]:
            col = df[col_date]
            dt_val = col_date.date() if isinstance(col_date, pd.Timestamp) else col_date

            results.append({
                "period_ending": dt_val,
                "fiscal_period": "FY" if period_type == "annual" else "Q",
                "fiscal_year": dt_val.year if hasattr(dt_val, "year") else None,
                "cash_and_equivalents": _g(col, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"),
                "accounts_receivable": _g(col, "Accounts Receivable", "Receivables"),
                "inventory": _g(col, "Inventory"),
                "prepaid_expenses": _g(col, "Prepaid Assets"),
                "other_current_assets": _g(col, "Other Current Assets"),
                "total_current_assets": _g(col, "Current Assets"),
                "property_plant_equipment": _g(col, "Net PPE", "Gross PPE"),
                "intangible_assets": _g(col, "Other Intangible Assets"),
                "goodwill": _g(col, "Goodwill"),
                "other_non_current_assets": _g(col, "Other Non Current Assets"),
                "total_non_current_assets": _g(col, "Total Non Current Assets"),
                "total_assets": _g(col, "Total Assets"),
                "accounts_payable": _g(col, "Accounts Payable", "Payables"),
                "short_term_debt": _g(col, "Current Debt", "Current Debt And Capital Lease Obligation"),
                "other_current_liabilities": _g(col, "Other Current Liabilities"),
                "total_current_liabilities": _g(col, "Current Liabilities"),
                "long_term_debt": _g(col, "Long Term Debt", "Long Term Debt And Capital Lease Obligation"),
                "other_non_current_liabilities": _g(col, "Other Non Current Liabilities"),
                "total_non_current_liabilities": _g(col, "Total Non Current Liabilities And Minority Interest"),
                "total_liabilities": _g(col, "Total Liabilities Net Minority Interest"),
                "minority_interest": _g(col, "Minority Interest"),
                "retained_earnings": _g(col, "Retained Earnings"),
                "total_shareholders_equity": _g(col, "Stockholders Equity", "Total Equity Gross Minority Interest"),
                "total_liabilities_and_equity": _g(col, "Total Assets"),  # A = L + E
                "net_debt": _g(col, "Net Debt"),
            })

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


provider_registry.register_fetcher(YFinanceBalanceSheetFetcher)
