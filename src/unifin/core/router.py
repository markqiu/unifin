"""Smart router — automatically selects the best provider for a query.

Every successful fetch is automatically persisted to the local DuckDB store.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from unifin.core.registry import model_registry, provider_registry
from unifin.core.symbol import parse_symbol, to_provider_symbol, to_unified_symbol
from unifin.core.types import Exchange

logger = logging.getLogger("unifin")

# Provider priority: higher = preferred.
_PROVIDER_PRIORITY: dict[str, int] = {
    "eastmoney": 90,
    "akshare": 70,
    "tushare": 60,
    "joinquant": 80,
    "yfinance": 75,
    "fmp": 85,
    "eodhd": 65,
    "jquants": 70,
    "jugaad": 70,
}

# Models that have (date, symbol) natural dedup keys
_TIME_SERIES_MODELS = {
    "equity_historical",
    "index_historical",
}


class SmartRouter:
    """Routes data requests to the best available provider.

    Selection logic:
    1. If ``provider`` is explicitly specified → use it directly.
    2. Detect exchange from symbol.
    3. Find all providers that support the model + exchange.
    4. Sort by priority, pick the best one.
    5. Fall back to next provider on failure.

    After a successful fetch the results are **automatically persisted** to
    the local DuckDB store (non-fatal on failure).
    """

    def query(
        self,
        model_name: str,
        query: BaseModel,
        provider: str | None = None,
        *,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """Execute a query, routing to the best provider.

        Args:
            model_name: Registered model name (e.g., "equity_historical").
            query: Unified query model instance.
            provider: Optional explicit provider name.
            use_cache: When True, check local DuckDB cache before fetching.

        Returns:
            List of result dicts conforming to the model's result schema.
        """
        model_registry.get(model_name)  # validates model exists

        # Determine symbol and exchange
        symbol = getattr(query, "symbol", None)
        _, exchange = parse_symbol(symbol) if symbol else (None, None)

        # ── Try cache first ──
        if use_cache and symbol:
            cached = self._load_cache(model_name, query)
            if cached:
                return cached

        # Resolve provider(s) to try
        providers_to_try = self._resolve_providers(model_name, exchange, provider)
        if not providers_to_try:
            from unifin.core.errors import NoProviderError

            all_for_model = list(provider_registry.get_providers_for_model(model_name).keys())
            raise NoProviderError(
                model_name=model_name,
                exchange=exchange,
                requested_provider=provider,
                available_providers=all_for_model or None,
            )

        # Try providers in priority order
        last_error: Exception | None = None
        for prov_name in providers_to_try:
            try:
                results = self._execute(model_name, query, prov_name)
                # Persist results (non-fatal)
                self._save_cache(model_name, results)
                return results
            except Exception as e:
                logger.warning(
                    "Provider '%s' failed for %s: %s. Trying next...",
                    prov_name,
                    model_name,
                    e,
                )
                last_error = e

        from unifin.core.errors import AllProvidersFailedError

        raise AllProvidersFailedError(
            model_name=model_name,
            tried=providers_to_try,
            last_error=last_error,
        )

    # ── cache helpers ──

    def _load_cache(
        self,
        model_name: str,
        query: BaseModel,
    ) -> list[dict[str, Any]] | None:
        """Attempt to load results from local store."""
        try:
            from unifin.core.store import store
            from unifin.core.symbol import to_unified_symbol as _uni

            symbol = getattr(query, "symbol", None)
            unified = _uni(symbol) if symbol else None
            start = getattr(query, "start_date", None)
            end = getattr(query, "end_date", None)

            rows = store.load(
                model_name,
                symbol=unified,
                start_date=str(start) if start else None,
                end_date=str(end) if end else None,
            )
            if rows:
                logger.debug("Cache hit: %d rows for %s/%s", len(rows), model_name, unified)
                return rows
        except Exception:
            pass
        return None

    def _save_cache(
        self,
        model_name: str,
        data: list[dict[str, Any]],
    ) -> None:
        """Persist results to local store (non-fatal)."""
        if not data:
            return
        try:
            from unifin.core.store import store

            dedup = ["date", "symbol"] if model_name in _TIME_SERIES_MODELS else None
            store.save(model_name, data, dedup_keys=dedup)
        except Exception as exc:
            logger.debug("Cache save failed for %s: %s", model_name, exc)

    # ── provider resolution ──

    def _resolve_providers(
        self,
        model_name: str,
        exchange: Exchange | None,
        explicit_provider: str | None,
    ) -> list[str]:
        """Determine ordered list of providers to try."""
        if explicit_provider:
            return [explicit_provider]

        if exchange:
            # Get providers that support this model + exchange
            candidates = provider_registry.get_providers_for_exchange(model_name, exchange)
        else:
            # No exchange detected (e.g., US ticker) → try all providers for this model
            candidates = list(provider_registry.get_providers_for_model(model_name).keys())

        # Sort by priority (descending)
        candidates.sort(key=lambda p: _PROVIDER_PRIORITY.get(p, 50), reverse=True)
        return candidates

    def _execute(
        self,
        model_name: str,
        query: BaseModel,
        provider_name: str,
    ) -> list[dict[str, Any]]:
        """Execute a query against a specific provider."""
        fetcher_cls = provider_registry.get_fetcher(model_name, provider_name)
        model_info = model_registry.get(model_name)

        # Convert symbol to provider format
        original_symbol = getattr(query, "symbol", None)
        if original_symbol:
            provider_symbol = to_provider_symbol(original_symbol, provider_name)
            # Create a copy of the query with the converted symbol
            query = query.model_copy(update={"symbol": provider_symbol})

        # TET pipeline
        params = fetcher_cls.transform_query(query)
        credentials = provider_registry.get_credentials(provider_name)
        raw_data = fetcher_cls.extract_data(params, credentials or None)
        results = fetcher_cls.transform_data(raw_data, query)

        # Resolve the unified symbol for injection
        unified_symbol = to_unified_symbol(original_symbol) if original_symbol else None

        # Validate each row against the result Pydantic model and
        # inject / convert symbols
        result_type = model_info.result_type
        validated: list[dict[str, Any]] = []
        for row in results:
            # Inject symbol if the result schema has a symbol field
            if unified_symbol and "symbol" in result_type.model_fields:
                if "symbol" not in row or row["symbol"] is None:
                    row["symbol"] = unified_symbol
                else:
                    row["symbol"] = to_unified_symbol(str(row["symbol"]), provider_name)

            # Pydantic validation — ensures type correctness
            obj = result_type.model_validate(row)
            validated.append(obj.model_dump())

        logger.debug(
            "Fetched %d rows from %s for model=%s",
            len(validated),
            provider_name,
            model_name,
        )
        return validated


# Global singleton
router = SmartRouter()
