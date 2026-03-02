"""EastMoney fetcher for equity_historical."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Adjust, Exchange


class EastMoneyEquityHistoricalFetcher(Fetcher):
    """Fetch equity historical data from East Money (Choice) API."""

    provider_name: ClassVar[str] = "eastmoney"
    model_name: ClassVar[str] = "equity_historical"
    supported_exchanges: ClassVar[list[Exchange]] = [
        Exchange.XSHG,
        Exchange.XSHE,
        Exchange.XHKG,
    ]
    requires_credentials: ClassVar[list[str]] = []

    @staticmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        """Convert unified query to EastMoney API parameters."""
        today = date.today()
        start = getattr(query, "start_date", None) or date(today.year - 1, today.month, today.day)
        end = getattr(query, "end_date", None) or today
        adjust = getattr(query, "adjust", Adjust.NONE)

        # Map adjustment type to EM flag: 1=不复权, 2=后复权, 3=前复权
        adjust_flag = {
            Adjust.NONE: "1",
            Adjust.BACKWARD: "2",
            Adjust.FORWARD: "3",
        }.get(adjust, "1")

        return {
            "symbol": getattr(query, "symbol", ""),
            "start_date": start.strftime("%Y%m%d")
            if isinstance(start, date)
            else str(start).replace("-", ""),
            "end_date": end.strftime("%Y%m%d")
            if isinstance(end, date)
            else str(end).replace("-", ""),
            "adjust_flag": adjust_flag,
            "indicators": "OPEN,CLOSE,HIGH,LOW,VOLUME,AMOUNT",
        }

    @staticmethod
    def extract_data(params: dict[str, Any], credentials: dict[str, str] | None = None) -> Any:
        """Call EastMoney EmQuantAPI."""
        try:
            from EmQuantAPI import c as em
        except ImportError:
            raise ImportError(
                "EmQuantAPI is not installed. "
                "Install it from https://quantapi.eastmoney.com/ "
                "or use a different provider (e.g., provider='yfinance')."
            )

        # Login
        login_result = em.start()
        if hasattr(login_result, "ErrorCode") and login_result.ErrorCode != 0:
            raise RuntimeError(f"EastMoney login failed: {login_result.ErrorMsg}")

        try:
            data = em.csd(
                params["symbol"],
                params["indicators"],
                params["start_date"],
                params["end_date"],
                f"AdjustFlag={params['adjust_flag']},Ispandas=1",
            )

            if hasattr(data, "ErrorCode") and data.ErrorCode != 0:
                raise RuntimeError(f"EastMoney API error: {data.ErrorMsg}")

            # Parse EM response into list of dicts
            result = []
            if data.Data and hasattr(data.Data, "items"):
                for code, indicators in data.Data.items():
                    if indicators and len(indicators) > 0:
                        for i, dt in enumerate(data.Dates):
                            row = {
                                "date": dt,
                                "open": indicators[0][i]
                                if len(indicators) > 0 and len(indicators[0]) > i
                                else None,
                                "close": indicators[1][i]
                                if len(indicators) > 1 and len(indicators[1]) > i
                                else None,
                                "high": indicators[2][i]
                                if len(indicators) > 2 and len(indicators[2]) > i
                                else None,
                                "low": indicators[3][i]
                                if len(indicators) > 3 and len(indicators[3]) > i
                                else None,
                                "volume": indicators[4][i]
                                if len(indicators) > 4 and len(indicators[4]) > i
                                else None,
                                "amount": indicators[5][i]
                                if len(indicators) > 5 and len(indicators[5]) > i
                                else None,
                            }
                            result.append(row)
            return result
        finally:
            em.stop()

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        """Transform EastMoney raw data to unified format."""
        if not raw_data:
            return []

        results = []
        for row in raw_data:
            dt = row.get("date")
            if isinstance(dt, str):
                try:
                    dt = datetime.strptime(dt, "%Y-%m-%d").date()
                except ValueError:
                    try:
                        dt = datetime.strptime(dt, "%Y%m%d").date()
                    except ValueError:
                        pass

            results.append(
                {
                    "date": dt,
                    "open": _to_float(row.get("open")),
                    "high": _to_float(row.get("high")),
                    "low": _to_float(row.get("low")),
                    "close": _to_float(row.get("close")),
                    "volume": _to_int(row.get("volume")),
                    "amount": _to_float(row.get("amount")),
                }
            )

        return results


def _to_float(v: Any) -> float | None:
    """Safely convert to float."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f  # NaN check
    except (ValueError, TypeError):
        return None


def _to_int(v: Any) -> int | None:
    """Safely convert to int."""
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


# Register
provider_registry.register_fetcher(EastMoneyEquityHistoricalFetcher)
