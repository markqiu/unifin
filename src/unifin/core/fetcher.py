"""Fetcher base class — the contract every provider must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel

from unifin.core.types import Exchange


class Fetcher(ABC):
    """Base class for all provider fetchers.

    Each fetcher binds to exactly one (provider, model) pair and declares
    which exchanges it supports.

    Subclasses must implement:
        - transform_query: convert unified query dict → provider params
        - extract_data:    call the provider API, return raw data
        - transform_data:  convert raw data → list of unified result dicts
    """

    # ── metadata (set by subclasses) ──
    provider_name: ClassVar[str]
    model_name: ClassVar[str]
    supported_exchanges: ClassVar[list[Exchange]]
    requires_credentials: ClassVar[list[str]] = []

    # ── coverage metadata (optional but recommended) ──
    #: List of result-model field names this fetcher actually populates.
    #: If empty / unset, the platform assumes *all* Optional fields may be None.
    supported_fields: ClassVar[list[str]] = []

    #: Earliest date for which the provider has data  (ISO string, e.g. "1990-01-01").
    data_start_date: ClassVar[str] = ""

    #: Data delay description: "realtime", "15min", "eod" (end-of-day).
    data_delay: ClassVar[str] = ""

    #: Free-form notes on data quality, limits, or quirks.
    notes: ClassVar[str] = ""

    @staticmethod
    @abstractmethod
    def transform_query(query: BaseModel) -> dict[str, Any]:
        """Convert unified query model → provider-specific parameters.

        The symbol in `query` is already converted to provider format
        by the router before this method is called.
        """

    @staticmethod
    @abstractmethod
    def extract_data(params: dict[str, Any], credentials: dict[str, str] | None = None) -> Any:
        """Call the provider API and return raw data (dict, DataFrame, etc.)."""

    @staticmethod
    @abstractmethod
    def transform_data(raw_data: Any, query: BaseModel) -> list[dict[str, Any]]:
        """Convert raw provider data → list of dicts matching the unified model schema."""
