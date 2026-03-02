"""ETF SDK — unifin.etf.*

Usage:
    import unifin

    df = unifin.etf.search("沪深300")
    df = unifin.etf.search("S&P 500")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from unifin.core.router import router

if TYPE_CHECKING:
    import polars as pl


def search(
    query: str = "",
    limit: int | None = None,
    provider: str | None = None,
) -> pl.DataFrame:
    """Search for ETFs by name or keyword.

    Args:
        query: Search keyword.
        limit: Maximum results.
        provider: Explicit provider name.

    Returns:
        Polars DataFrame: symbol, name, exchange, fund_type, ...
    """
    import polars as pl

    from unifin.models.etf_search import EtfSearchQuery

    q = EtfSearchQuery(query=query, limit=limit)
    results = router.query("etf_search", q, provider=provider)
    return pl.DataFrame(results) if results else pl.DataFrame()
