"""Yahoo Finance data provider."""

from unifin.core.registry import ProviderInfo, provider_registry

provider_registry.register_provider(
    ProviderInfo(
        name="yfinance",
        description=(
            "Yahoo Finance — free global market data"
            " (15-min delayed US quotes, historical from ~1970)"
        ),
        website="https://finance.yahoo.com/",
        credentials_env={},  # No auth required
        markets=[
            "US",
            "CN",
            "HK",
            "JP",
            "GB",
            "DE",
            "FR",
            "NL",
            "CH",
            "IT",
            "SG",
            "AU",
            "KR",
            "TW",
            "IN",
            "CA",
        ],
        data_delay="15min",
        notes="Free tier. US quotes 15-min delayed. Minute-level data limited to last 7 days. "
        "Does not provide amount, vwap, or turnover_rate for equity historical. "
        "Financial statements may have limited coverage for non-US companies.",
    )
)

# Import fetchers to trigger registration
from unifin.providers.yfinance import balance_sheet as _bs  # noqa: F401, E402
from unifin.providers.yfinance import cash_flow as _cf  # noqa: F401, E402
from unifin.providers.yfinance import equity_historical as _  # noqa: F401, E402
from unifin.providers.yfinance import equity_profile as _p  # noqa: F401, E402
from unifin.providers.yfinance import equity_quote as _q  # noqa: F401, E402
from unifin.providers.yfinance import equity_search as _s  # noqa: F401, E402
from unifin.providers.yfinance import etf_search as _es  # noqa: F401, E402
from unifin.providers.yfinance import income_statement as _is  # noqa: F401, E402
from unifin.providers.yfinance import index_historical as _ih  # noqa: F401, E402
from unifin.providers.yfinance import trade_calendar as _tc  # noqa: F401, E402
