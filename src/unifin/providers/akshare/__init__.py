"""AKShare data provider — free, open-source Chinese market data.

AKShare aggregates data from Sina, EastMoney, TongHuaShun, and others.
No authentication required.
"""

from unifin.core.registry import ProviderInfo, provider_registry

provider_registry.register_provider(
    ProviderInfo(
        name="akshare",
        description=(
            "AKShare — open-source Chinese financial data aggregator"
            " (EastMoney, Sina, XueQiu, etc.)"
        ),
        website="https://akshare.akfamily.xyz/",
        credentials_env={},  # No auth required
        markets=["CN", "HK"],
        data_delay="15min",
        notes="Free and open-source. Covers A-shares and HK stocks. "
        "Data sourced from EastMoney, Sina, XueQiu and others. "
        "No API key required. Rate limits may apply during peak hours.",
    )
)

# Import fetchers to trigger registration
from unifin.providers.akshare import equity_historical as _eh  # noqa: F401, E402
from unifin.providers.akshare import equity_quote as _eq  # noqa: F401, E402
from unifin.providers.akshare import equity_search as _es  # noqa: F401, E402
from unifin.providers.akshare import etf_search as _etf  # noqa: F401, E402
from unifin.providers.akshare import trade_calendar as _tc  # noqa: F401, E402
from unifin.providers.akshare import fund_nav  # noqa: F401  # auto-evolved
