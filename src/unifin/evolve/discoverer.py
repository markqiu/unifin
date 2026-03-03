"""Data source discoverer — search known provider APIs for matching data functions.

Currently supports:
- akshare: enumerate available functions from the package
- yfinance: known Ticker attribute/method mappings

Future:
- tushare, fmp, etc.
- Web search for documentation
"""

from __future__ import annotations

import logging
from typing import Any

from unifin.evolve.schema import SourceCandidate

logger = logging.getLogger("unifin")

# ---------------------------------------------------------------------------
# Known data source catalogs
# ---------------------------------------------------------------------------

AKSHARE_CATALOG: list[dict[str, Any]] = [
    # ── Equity ──
    {
        "keywords": ["股票", "A股", "行情", "历史", "stock", "equity", "historical", "price"],
        "function": "ak.stock_zh_a_hist",
        "description": "A股个股历史行情数据(东财)",
        "columns": [
            "日期",
            "开盘",
            "收盘",
            "最高",
            "最低",
            "成交量",
            "成交额",
            "振幅",
            "涨跌幅",
            "涨跌额",
            "换手率",
        ],
        "exchanges": ["XSHG", "XSHE"],
    },
    {
        "keywords": ["港股", "行情", "历史", "hk", "hong kong"],
        "function": "ak.stock_hk_hist",
        "description": "港股个股历史行情数据(东财)",
        "columns": ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"],
        "exchanges": ["XHKG"],
    },
    # ── Fund ──
    {
        "keywords": ["基金", "净值", "fund", "nav", "net asset value", "开放式"],
        "function": "ak.fund_open_fund_info_em",
        "description": "开放式基金历史净值数据(东财)",
        "columns": [
            "净值日期",
            "单位净值",
            "累计净值",
            "日增长率",
            "申购状态",
            "赎回状态",
            "分红送配",
        ],
        "exchanges": ["XSHG", "XSHE"],
    },
    {
        "keywords": ["ETF", "etf", "基金", "场内"],
        "function": "ak.fund_etf_hist_em",
        "description": "场内ETF历史行情数据(东财)",
        "columns": ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"],
        "exchanges": ["XSHG", "XSHE"],
    },
    {
        "keywords": ["基金", "持仓", "fund", "holdings", "重仓"],
        "function": "ak.fund_portfolio_hold_em",
        "description": "基金重仓股数据(东财)",
        "columns": ["序号", "股票代码", "股票名称", "占净值比例", "持股数", "持仓市值", "季度"],
        "exchanges": ["XSHG", "XSHE"],
    },
    # ── Index ──
    {
        "keywords": ["指数", "成分股", "index", "constituent", "权重"],
        "function": "ak.index_stock_cons",
        "description": "指数成分股数据",
        "columns": ["品种代码", "品种名称", "纳入日期"],
        "exchanges": ["XSHG", "XSHE"],
    },
    {
        "keywords": ["指数", "行情", "历史", "index", "historical"],
        "function": "ak.stock_zh_index_daily",
        "description": "中国主要指数历史行情",
        "columns": ["date", "open", "high", "low", "close", "volume"],
        "exchanges": ["XSHG", "XSHE"],
    },
    # ── Macro ──
    {
        "keywords": ["GDP", "gdp", "国内生产总值", "macro", "宏观"],
        "function": "ak.macro_china_gdp",
        "description": "中国GDP数据",
        "columns": ["季度", "国内生产总值-绝对值", "国内生产总值-同比增长", "第一产业-绝对值"],
        "exchanges": [],
    },
    {
        "keywords": ["CPI", "cpi", "物价", "消费者价格", "通胀"],
        "function": "ak.macro_china_cpi",
        "description": "中国CPI数据",
        "columns": ["月份", "全国-当月", "全国-同比增长", "全国-环比增长"],
        "exchanges": [],
    },
    {
        "keywords": ["利率", "shibor", "银行间", "拆借", "interest rate"],
        "function": "ak.rate_interbank",
        "description": "银行间拆借利率 (Shibor等)",
        "columns": ["报告日", "利率类型", "1天", "7天", "14天", "1月", "3月"],
        "exchanges": [],
    },
    # ── Company info ──
    {
        "keywords": ["财务", "利润", "income", "profit", "收入", "利润表"],
        "function": "ak.stock_financial_report_sina",
        "description": "上市公司财务报表(新浪)",
        "columns": ["报告期", "净利润", "营业收入", "基本每股收益"],
        "exchanges": ["XSHG", "XSHE"],
    },
    {
        "keywords": ["分红", "dividend", "股息", "送股", "转增"],
        "function": "ak.stock_history_dividend_detail",
        "description": "个股历史分红数据(东财)",
        "columns": ["报告期", "分红方案", "股权登记日", "除权除息日"],
        "exchanges": ["XSHG", "XSHE"],
    },
    {
        "keywords": ["龙虎榜", "大宗", "异动", "hot", "dragon", "tiger"],
        "function": "ak.stock_lhb_detail_daily_sina",
        "description": "龙虎榜每日详情(新浪)",
        "columns": ["序号", "代码", "名称", "收盘价", "涨跌幅", "龙虎榜净买额"],
        "exchanges": ["XSHG", "XSHE"],
    },
    {
        "keywords": ["融资融券", "margin", "两融", "融资", "融券"],
        "function": "ak.stock_margin_detail_szse",
        "description": "融资融券明细数据",
        "columns": ["交易日期", "股票代码", "融资余额", "融券余量", "融资买入额"],
        "exchanges": ["XSHG", "XSHE"],
    },
    # ── News / Sentiment ──
    {
        "keywords": ["新闻", "公告", "news", "announcement", "资讯"],
        "function": "ak.stock_notice_report",
        "description": "上市公司公告数据",
        "columns": ["代码", "名称", "公告标题", "公告类型", "公告日期"],
        "exchanges": ["XSHG", "XSHE"],
    },
    # ── Futures ──
    {
        "keywords": ["期货", "futures", "商品", "commodity"],
        "function": "ak.futures_zh_daily_sina",
        "description": "国内期货日线数据(新浪)",
        "columns": ["date", "open", "high", "low", "close", "volume", "hold"],
        "exchanges": [],
    },
    # ── Forex ──
    {
        "keywords": ["汇率", "外汇", "forex", "currency", "exchange rate"],
        "function": "ak.currency_boc_sina",
        "description": "人民币汇率数据(中国银行)",
        "columns": ["日期", "现汇买入价", "现钞买入价", "现汇卖出价", "现钞卖出价"],
        "exchanges": [],
    },
    # ── Bond ──
    {
        "keywords": ["债券", "国债", "bond", "treasury", "收益率曲线"],
        "function": "ak.bond_china_yield",
        "description": "中国国债收益率曲线",
        "columns": ["日期", "中债国债到期收益率:1年", "中债国债到期收益率:10年"],
        "exchanges": [],
    },
]

YFINANCE_CATALOG: list[dict[str, Any]] = [
    {
        "keywords": ["历史", "行情", "price", "historical", "ohlcv"],
        "function": "history",
        "description": "Historical OHLCV data (global)",
        "columns": ["Open", "High", "Low", "Close", "Volume"],
        "exchanges": ["XNYS", "XNAS", "XHKG", "XLON", "XSHG", "XSHE"],
    },
    {
        "keywords": ["财务", "资产负债", "balance", "sheet"],
        "function": "balance_sheet",
        "description": "Balance sheet (global)",
        "columns": ["Total Assets", "Total Liabilities", "Stockholders Equity"],
        "exchanges": ["XNYS", "XNAS", "XHKG", "XLON"],
    },
    {
        "keywords": ["利润", "income", "profit", "收入"],
        "function": "income_stmt",
        "description": "Income statement (global)",
        "columns": ["Total Revenue", "Net Income", "Operating Income"],
        "exchanges": ["XNYS", "XNAS", "XHKG", "XLON"],
    },
    {
        "keywords": ["现金流", "cash", "flow"],
        "function": "cashflow",
        "description": "Cash flow statement (global)",
        "columns": ["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow"],
        "exchanges": ["XNYS", "XNAS", "XHKG", "XLON"],
    },
    {
        "keywords": ["分红", "股息", "dividend"],
        "function": "dividends",
        "description": "Historical dividends (global)",
        "columns": ["Date", "Dividends"],
        "exchanges": ["XNYS", "XNAS", "XHKG", "XLON"],
    },
    {
        "keywords": ["公司", "信息", "profile", "company", "info"],
        "function": "info",
        "description": "Company profile / info (global)",
        "columns": ["shortName", "sector", "industry", "marketCap"],
        "exchanges": ["XNYS", "XNAS", "XHKG", "XLON"],
    },
]


# ---------------------------------------------------------------------------
# Discoverer
# ---------------------------------------------------------------------------


class SourceDiscoverer:
    """Search known provider APIs for data sources matching a user's need."""

    def search(self, keywords: list[str], provider: str | None = None) -> list[SourceCandidate]:
        """Search all (or a specific) provider for matching data sources."""
        candidates: list[SourceCandidate] = []

        if provider is None or provider == "akshare":
            candidates.extend(self._search_catalog(keywords, "akshare", AKSHARE_CATALOG))

        if provider is None or provider == "yfinance":
            candidates.extend(self._search_catalog(keywords, "yfinance", YFINANCE_CATALOG))

        candidates.sort(key=lambda c: self._score(c, keywords), reverse=True)

        if candidates:
            top_score = self._score(candidates[0], keywords)
            threshold = max(1, top_score // 2)
            candidates = [c for c in candidates if self._score(c, keywords) >= threshold]

        return candidates

    def list_available_sources(self, provider: str | None = None) -> list[dict[str, str]]:
        """List all known data sources in the catalog."""
        result: list[dict[str, str]] = []
        catalogs = []
        if provider is None or provider == "akshare":
            catalogs.append(("akshare", AKSHARE_CATALOG))
        if provider is None or provider == "yfinance":
            catalogs.append(("yfinance", YFINANCE_CATALOG))

        for prov_name, catalog in catalogs:
            for entry in catalog:
                result.append(
                    {
                        "provider": prov_name,
                        "function": entry["function"],
                        "description": entry["description"],
                        "keywords": ", ".join(entry["keywords"]),
                    }
                )
        return result

    # ── internal ──

    def _search_catalog(
        self,
        keywords: list[str],
        provider: str,
        catalog: list[dict[str, Any]],
    ) -> list[SourceCandidate]:
        """Search a provider catalog for keyword matches."""
        results: list[SourceCandidate] = []
        keywords_lower = [k.lower() for k in keywords]

        for entry in catalog:
            entry_keywords = [k.lower() for k in entry.get("keywords", [])]
            desc_lower = entry.get("description", "").lower()

            matched = False
            for kw in keywords_lower:
                if any(kw in ek for ek in entry_keywords) or kw in desc_lower:
                    matched = True
                    break

            if matched:
                results.append(
                    SourceCandidate(
                        provider=provider,
                        function_name=entry["function"],
                        description=entry["description"],
                        sample_columns=entry.get("columns", []),
                        exchanges=entry.get("exchanges", []),
                    )
                )

        return results

    def _score(self, candidate: SourceCandidate, keywords: list[str]) -> int:
        """Score a candidate by keyword match count."""
        score = 0
        text = (candidate.function_name + " " + candidate.description).lower()
        for kw in keywords:
            if kw.lower() in text:
                score += 1
        return score


# Global singleton
discoverer = SourceDiscoverer()
