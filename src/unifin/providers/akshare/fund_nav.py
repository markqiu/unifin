"""akshare fetcher for fund_nav.

Source: ak.fund_open_fund_info_em
开放式基金历史净值数据(东财)
"""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.registry import provider_registry
from unifin.core.types import Exchange


class AkshareFundNavFetcher(Fetcher):
    """Fetch 开放式基金净值数据 from akshare."""

    provider_name: ClassVar[str] = "akshare"
    model_name: ClassVar[str] = "fund_nav"
    supported_exchanges: ClassVar[list[Exchange]] = [Exchange.XSHG, Exchange.XSHE]

    supported_fields: ClassVar[list[str]] = ['date', 'nav', 'acc_nav', 'daily_return', 'symbol', 'name']
    data_delay: ClassVar[str] = "eod"
    notes: ClassVar[str] = ""

    @staticmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        today = dt.date.today()
        start = getattr(query, "start_date", None)
        start = start or (today - dt.timedelta(days=365))
        end = getattr(query, "end_date", None) or today
        symbol = getattr(query, "symbol", "")

        return {
            "symbol": symbol,
            "start_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
        }

    @staticmethod
    def extract_data(
        params: dict[str, Any],
        credentials: dict[str, str] | None = None,
    ) -> Any:
        try:
            import akshare as ak
        except ImportError:
            raise ImportError("akshare is not installed. pip install 'unifin[akshare]'")

        try:
            df = ak.fund_open_fund_info_em(
                symbol=params["symbol"],
            )
            return df
        except Exception:
            return None

    @staticmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        if raw_data is None or (hasattr(raw_data, 'empty') and raw_data.empty):
            return []

        col_map = {'净值日期': 'date', '单位净值': 'nav', '累计净值': 'acc_nav', '日增长率': 'daily_return'}

        records = raw_data.to_dict(orient="records")
        results = []
        for row in records:
            mapped = {}
            for src_col, dst_col in col_map.items():
                if src_col in row:
                    mapped[dst_col] = row[src_col]
            mapped.setdefault("nav", None)
            mapped.setdefault("acc_nav", None)
            mapped.setdefault("daily_return", None)
            mapped.setdefault("symbol", None)
            mapped.setdefault("name", None)
            results.append(mapped)

        return results


provider_registry.register_fetcher(AkshareFundNavFetcher)
