"""YFinance fetcher for cash_flow."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange


class YFinanceCashFlowFetcher(Fetcher):
    """Fetch cash flow statement from Yahoo Finance."""

    provider_name: ClassVar[str] = "yfinance"
    model_name: ClassVar[str] = "cash_flow"
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
        "net_income", "depreciation_and_amortization",
        "stock_based_compensation", "change_in_working_capital",
        "net_cash_from_operations", "capital_expenditure",
        "net_cash_from_investing",
        "issuance_of_debt", "repayment_of_debt",
        "share_repurchase", "dividends_paid",
        "net_cash_from_financing",
        "net_change_in_cash", "cash_at_beginning", "cash_at_end",
        "free_cash_flow",
    ]
    data_start_date: ClassVar[str] = "2000-01-01"
    data_delay: ClassVar[str] = "eod"
    notes: ClassVar[str] = (
        "Typically provides 4 annual or 4-5 quarterly periods. "
        "free_cash_flow is computed as operating_cf + capex. "
        "acquisitions, purchase/sale_of_investments, issuance_of_equity may be None."
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
            df = ticker.quarterly_cashflow
        else:
            df = ticker.cashflow

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

            op_cf = _g(col, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
            capex = _g(col, "Capital Expenditure")
            fcf = None
            if op_cf is not None and capex is not None:
                fcf = op_cf + capex  # CapEx is typically negative

            results.append({
                "period_ending": dt_val,
                "fiscal_period": "FY" if period_type == "annual" else "Q",
                "fiscal_year": dt_val.year if hasattr(dt_val, "year") else None,
                "net_income": _g(col, "Net Income", "Net Income From Continuing Operations"),
                "depreciation_and_amortization": _g(col, "Depreciation And Amortization", "Depreciation Amortization Depletion"),
                "stock_based_compensation": _g(col, "Stock Based Compensation"),
                "change_in_working_capital": _g(col, "Change In Working Capital", "Changes In Account Receivables"),
                "net_cash_from_operations": op_cf,
                "capital_expenditure": capex,
                "acquisitions": _g(col, "Acquisitions And Disposals"),
                "purchase_of_investments": _g(col, "Purchase Of Investment", "Purchase Of Business"),
                "sale_of_investments": _g(col, "Sale Of Investment"),
                "net_cash_from_investing": _g(col, "Investing Cash Flow", "Cash Flow From Continuing Investing Activities"),
                "issuance_of_debt": _g(col, "Issuance Of Debt", "Long Term Debt Issuance"),
                "repayment_of_debt": _g(col, "Repayment Of Debt", "Long Term Debt Payments"),
                "issuance_of_equity": _g(col, "Issuance Of Capital Stock"),
                "share_repurchase": _g(col, "Repurchase Of Capital Stock"),
                "dividends_paid": _g(col, "Common Stock Dividend Paid", "Cash Dividends Paid"),
                "net_cash_from_financing": _g(col, "Financing Cash Flow", "Cash Flow From Continuing Financing Activities"),
                "effect_of_exchange_rates": _g(col, "Effect Of Exchange Rate Changes"),
                "net_change_in_cash": _g(col, "Changes In Cash"),
                "cash_at_beginning": _g(col, "Beginning Cash Position"),
                "cash_at_end": _g(col, "End Cash Position"),
                "free_cash_flow": fcf,
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


provider_registry.register_fetcher(YFinanceCashFlowFetcher)
