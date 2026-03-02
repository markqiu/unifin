"""EastMoney data provider."""

from unifin.core.registry import ProviderInfo, provider_registry

provider_registry.register_provider(
    ProviderInfo(
        name="eastmoney",
        description="East Money (Choice) quantitative data API",
        website="https://quantapi.eastmoney.com/",
        credentials_env={},  # Auth handled by EmQuantAPI client-side license
    )
)

# Import fetchers to trigger registration
from unifin.providers.eastmoney import equity_historical as _  # noqa: F401, E402
