"""Model and Provider registries — the central nervous system of unifin."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel

from unifin.core.fetcher import Fetcher
from unifin.core.types import Exchange

logger = logging.getLogger("unifin")


# ──────────────────────────────────────────────
# Model Registry
# ──────────────────────────────────────────────


@dataclass
class ModelInfo:
    """Metadata about a registered data model."""

    name: str  # e.g. "equity_historical"
    category: str  # e.g. "equity.price"
    query_type: type[BaseModel]  # Pydantic model for query params
    result_type: type[BaseModel]  # Pydantic model for result data
    description: str = ""
    version: str = "1.0"


class ModelRegistry:
    """Central registry of all data models.

    All models must be registered here. Providers cannot define ad-hoc models.
    """

    def __init__(self) -> None:
        self._models: dict[str, ModelInfo] = {}

    def register(self, info: ModelInfo) -> None:
        """Register a data model."""
        if info.name in self._models:
            logger.warning("Model '%s' already registered, overwriting.", info.name)
        self._models[info.name] = info
        logger.debug("Registered model: %s (%s)", info.name, info.category)

    def get(self, name: str) -> ModelInfo:
        """Get model info by name."""
        if name not in self._models:
            from unifin.core.errors import ModelNotFoundError

            raise ModelNotFoundError(name, sorted(self._models.keys()))
        return self._models[name]

    def list_models(self) -> list[str]:
        """List all registered model names."""
        return sorted(self._models.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._models


# ──────────────────────────────────────────────
# Provider Registry
# ──────────────────────────────────────────────


@dataclass
class ProviderInfo:
    """Metadata about a registered data provider."""

    name: str
    description: str = ""
    website: str = ""
    credentials_env: dict[str, str] = field(default_factory=dict)
    # model_name → list of supported exchanges
    coverage: dict[str, list[Exchange]] = field(default_factory=dict)
    # ── extended metadata ──
    #: Geographic markets covered (e.g., ["CN", "US", "HK"])
    markets: list[str] = field(default_factory=list)
    #: Data delay: "realtime", "15min", "eod"
    data_delay: str = ""
    #: Free-form notes (limits, caveats, etc.)
    notes: str = ""


class ProviderRegistry:
    """Central registry of all data providers and their fetchers.

    Maps (model_name, provider_name) → Fetcher class.
    """

    def __init__(self) -> None:
        self._providers: dict[str, ProviderInfo] = {}
        # model_name → {provider_name → Fetcher class}
        self._fetchers: dict[str, dict[str, type[Fetcher]]] = {}

    def register_provider(self, info: ProviderInfo) -> None:
        """Register a provider."""
        self._providers[info.name] = info
        logger.debug("Registered provider: %s", info.name)

    def register_fetcher(self, fetcher_cls: type[Fetcher]) -> None:
        """Register a fetcher class. Automatically updates provider coverage."""
        model = fetcher_cls.model_name
        provider = fetcher_cls.provider_name
        exchanges = fetcher_cls.supported_exchanges

        if model not in self._fetchers:
            self._fetchers[model] = {}
        self._fetchers[model][provider] = fetcher_cls

        # Update provider coverage
        if provider in self._providers:
            self._providers[provider].coverage[model] = exchanges

        logger.debug(
            "Registered fetcher: %s/%s (exchanges: %s)",
            provider,
            model,
            [e.value for e in exchanges],
        )

    def get_fetcher(self, model_name: str, provider_name: str) -> type[Fetcher]:
        """Get a specific fetcher."""
        fetchers = self._fetchers.get(model_name, {})
        if provider_name not in fetchers:
            from unifin.core.errors import FetcherNotFoundError

            raise FetcherNotFoundError(model_name, provider_name, sorted(fetchers.keys()))
        return fetchers[provider_name]

    def get_providers_for_model(self, model_name: str) -> dict[str, type[Fetcher]]:
        """Get all providers that support a model."""
        return self._fetchers.get(model_name, {})

    def get_providers_for_exchange(self, model_name: str, exchange: Exchange) -> list[str]:
        """Get provider names that support a model for a specific exchange."""
        result = []
        for provider_name, fetcher_cls in self._fetchers.get(model_name, {}).items():
            if exchange in fetcher_cls.supported_exchanges:
                result.append(provider_name)
        return result

    def get_provider_info(self, name: str) -> ProviderInfo:
        """Get provider metadata."""
        if name not in self._providers:
            from unifin.core.errors import ProviderNotFoundError

            raise ProviderNotFoundError(name, sorted(self._providers.keys()))
        return self._providers[name]

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return sorted(self._providers.keys())

    def get_credentials(self, provider_name: str) -> dict[str, str]:
        """Load credentials from environment variables for a provider."""
        import os

        info = self.get_provider_info(provider_name)
        creds = {}
        for key, env_var in info.credentials_env.items():
            value = os.environ.get(env_var)
            if value:
                creds[key] = value
        return creds


# ──────────────────────────────────────────────
# Global singletons
# ──────────────────────────────────────────────

model_registry = ModelRegistry()
provider_registry = ProviderRegistry()
