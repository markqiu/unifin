"""Tests for fund_nav model and fetchers."""

from unifin.core.registry import model_registry, provider_registry


class TestModelFundNav:
    """Tests for fund_nav model registration."""

    def test_model_registered(self):
        assert "fund_nav" in model_registry

    def test_model_info(self):
        info = model_registry.get("fund_nav")
        assert info.name == "fund_nav"
        assert info.category == "fund.price"

    def test_query_fields(self):
        info = model_registry.get("fund_nav")
        fields = info.query_type.model_fields
        assert "symbol" in fields
        assert "start_date" in fields
        assert "end_date" in fields

    def test_result_fields(self):
        info = model_registry.get("fund_nav")
        fields = info.result_type.model_fields
        assert "date" in fields
        assert "nav" in fields
        assert "acc_nav" in fields
        assert "daily_return" in fields
        assert "symbol" in fields
        assert "name" in fields


class TestFetcherAkshareFundNav:
    """Tests for akshare fetcher of fund_nav."""

    def test_fetcher_registered(self):
        fetcher = provider_registry.get_fetcher("fund_nav", "akshare")
        assert fetcher is not None
        assert fetcher.model_name == "fund_nav"
        assert fetcher.provider_name == "akshare"

    def test_supported_exchanges(self):
        fetcher = provider_registry.get_fetcher("fund_nav", "akshare")
        assert len(fetcher.supported_exchanges) > 0

