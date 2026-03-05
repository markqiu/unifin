"""unifin - Unified intelligent global financial data platform.

Usage:
    import unifin

    # ── Equity ──
    df = unifin.equity.historical("000001.XSHE", start_date="2024-01-01")
    df = unifin.equity.historical("AAPL", start_date="2024-01-01")
    df = unifin.equity.search("Apple")
    df = unifin.equity.profile("AAPL")
    df = unifin.equity.quote("AAPL")
    df = unifin.equity.balance_sheet("AAPL")
    df = unifin.equity.income_statement("AAPL")
    df = unifin.equity.cash_flow("AAPL")

    # ── Index ──
    df = unifin.index.historical("^GSPC", start_date="2024-01-01")

    # ── ETF ──
    df = unifin.etf.search("S&P 500")

    # ── Market ──
    df = unifin.market.trade_calendar(market="cn")
"""

__version__ = "0.1.0"

# ── Register models (must happen before providers) ──
from unifin.models import (
    balance_sheet as _m5,  # noqa: F401, E402
)
from unifin.models import (
    cash_flow as _m7,  # noqa: F401, E402
)
from unifin.models import (
    equity_historical as _m1,  # noqa: F401, E402
)
from unifin.models import (
    equity_profile as _m3,  # noqa: F401, E402
)
from unifin.models import (
    equity_quote as _m4,  # noqa: F401, E402
)
from unifin.models import (
    equity_search as _m2,  # noqa: F401, E402
)
from unifin.models import (
    etf_search as _m9,  # noqa: F401, E402
)
from unifin.models import (
    fund_nav as _m11,  # noqa: F401, E402  # auto-evolved
)
from unifin.models import (
    income_statement as _m6,  # noqa: F401, E402
)
from unifin.models import (
    index_historical as _m8,  # noqa: F401, E402
)
from unifin.models import (
    trade_calendar as _m10,  # noqa: F401, E402
)

# ── Register providers ──
# Each provider import triggers self-registration of its fetchers.
# We catch ImportError so missing optional deps don't break the package.

try:
    from unifin.providers import yfinance as _p_yf  # noqa: F401
except ImportError:
    pass

try:
    from unifin.providers import akshare as _p_ak  # noqa: F401
except ImportError:
    pass

try:
    from unifin.providers import eastmoney as _p_em  # noqa: F401
except ImportError:
    pass

# ── Expose SDK namespaces ──
from unifin.sdk import (  # noqa: F401, E402
    equity,
    etf,
    index,
    market,
)
