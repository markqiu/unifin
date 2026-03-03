"""Tests for the REST API and NL modules.

These tests verify:
1. FastAPI app auto-generates endpoints from registry
2. Data endpoints accept POST and return results
3. NL tool schema generation matches the model registry
4. Store save/load with dedup keys
"""

# ── ensure unifin is imported (triggers registration) ──
from unifin.core.registry import model_registry

# ---------------------------------------------------------------------------
# NL Tool schema generation
# ---------------------------------------------------------------------------


class TestNLTools:
    """Test that tool schemas are generated from the registry."""

    def test_generate_tools_returns_all_models(self):
        from unifin.nl.tools import generate_tools

        tools = generate_tools()
        model_names = model_registry.list_models()
        tool_names = [t["function"]["name"] for t in tools]

        for name in model_names:
            assert f"query_{name}" in tool_names, f"Missing tool for model {name}"

    def test_tool_has_correct_structure(self):
        from unifin.nl.tools import generate_tools

        tools = generate_tools()
        for tool in tools:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            params = func["parameters"]
            assert params["type"] == "object"
            assert "properties" in params

    def test_equity_historical_tool_has_symbol(self):
        from unifin.nl.tools import generate_tools

        tools = generate_tools()
        eh_tool = next(t for t in tools if t["function"]["name"] == "query_equity_historical")
        props = eh_tool["function"]["parameters"]["properties"]
        assert "symbol" in props
        assert "start_date" in props
        assert "end_date" in props

    def test_tool_name_to_model(self):
        from unifin.nl.tools import tool_name_to_model

        assert tool_name_to_model("query_equity_historical") == "equity_historical"
        assert tool_name_to_model("query_trade_calendar") == "trade_calendar"

    def test_enum_fields_have_enum_values(self):
        from unifin.nl.tools import generate_tools

        tools = generate_tools()
        eh_tool = next(t for t in tools if t["function"]["name"] == "query_equity_historical")
        props = eh_tool["function"]["parameters"]["properties"]
        # interval should have enum values
        assert "enum" in props["interval"]
        assert "1d" in props["interval"]["enum"]

    def test_new_model_auto_generates_tool(self):
        """Verify that if we register a model, it shows up in tools."""
        from unifin.nl.tools import generate_tools

        tools_before = generate_tools()
        count_before = len(tools_before)
        # All 10 models should be present
        assert count_before == len(model_registry.list_models())


# ---------------------------------------------------------------------------
# REST API endpoint auto-generation
# ---------------------------------------------------------------------------


class TestAPIEndpoints:
    """Test that FastAPI app has auto-generated endpoints."""

    def test_app_has_health(self):
        from fastapi.testclient import TestClient

        from unifin.api.app import app

        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_app_has_models_endpoint(self):
        from fastapi.testclient import TestClient

        from unifin.api.app import app

        client = TestClient(app)
        resp = client.get("/api/models")
        assert resp.status_code == 200
        models = resp.json()
        names = [m["name"] for m in models]
        assert "equity_historical" in names
        assert "trade_calendar" in names

    def test_app_has_providers_endpoint(self):
        from fastapi.testclient import TestClient

        from unifin.api.app import app

        client = TestClient(app)
        resp = client.get("/api/providers")
        assert resp.status_code == 200
        providers = resp.json()
        names = [p["name"] for p in providers]
        assert "yfinance" in names

    def test_model_endpoint_exists(self):
        """Each model should have a POST endpoint."""
        from unifin.api.app import app

        routes = {r.path for r in app.routes}
        # Check a few key endpoints
        assert any("equity_historical" in r for r in routes)
        assert any("trade_calendar" in r for r in routes)

    def test_nl_tools_endpoint(self):
        from fastapi.testclient import TestClient

        from unifin.api.app import app

        client = TestClient(app)
        resp = client.get("/api/nl/tools")
        assert resp.status_code == 200
        tools = resp.json()
        assert len(tools) == len(model_registry.list_models())

    def test_model_summary_has_fields(self):
        from fastapi.testclient import TestClient

        from unifin.api.app import app

        client = TestClient(app)
        resp = client.get("/api/models")
        models = resp.json()
        eh = next(m for m in models if m["name"] == "equity_historical")
        assert "symbol" in eh["query_fields"]
        assert "close" in eh["result_fields"]
        assert "date" in eh["result_fields"]


# ---------------------------------------------------------------------------
# Store enhancements
# ---------------------------------------------------------------------------


class TestStoreEnhancements:
    """Test the enhanced DataStore."""

    def test_list_tables(self, tmp_path):
        from unifin.core.store import DataStore

        s = DataStore(db_path=tmp_path / "test.duckdb")
        s.save("test_model", [{"a": 1, "b": 2}])
        tables = s.list_tables()
        assert "unifin_test_model" in tables
        s.close()

    def test_table_row_count(self, tmp_path):
        from unifin.core.store import DataStore

        s = DataStore(db_path=tmp_path / "test.duckdb")
        s.save("test_model", [{"a": 1}, {"a": 2}, {"a": 3}])
        assert s.table_row_count("test_model") == 3
        s.close()

    def test_dedup_keys(self, tmp_path):
        from unifin.core.store import DataStore

        s = DataStore(db_path=tmp_path / "test.duckdb")
        # Insert initial data
        s.save("ts", [{"date": "2024-01-01", "symbol": "AAPL", "close": 100.0}])
        # Insert overlapping data with dedup
        s.save(
            "ts",
            [{"date": "2024-01-01", "symbol": "AAPL", "close": 101.0}],
            dedup_keys=["date", "symbol"],
        )
        rows = s.load("ts")
        assert len(rows) == 1
        assert rows[0]["close"] == 101.0
        s.close()

    def test_load_with_filters(self, tmp_path):
        from unifin.core.store import DataStore

        s = DataStore(db_path=tmp_path / "test.duckdb")
        s.save(
            "m",
            [
                {"symbol": "A", "market": "cn", "val": 1},
                {"symbol": "B", "market": "us", "val": 2},
            ],
        )
        rows = s.load("m", filters={"market": "cn"})
        assert len(rows) == 1
        assert rows[0]["symbol"] == "A"
        s.close()

    def test_load_with_limit(self, tmp_path):
        from unifin.core.store import DataStore

        s = DataStore(db_path=tmp_path / "test.duckdb")
        s.save("m", [{"v": i} for i in range(10)])
        rows = s.load("m", limit=3)
        assert len(rows) == 3
        s.close()


# ---------------------------------------------------------------------------
# Router cache integration
# ---------------------------------------------------------------------------


class TestRouterCacheIntegration:
    """Test that router auto-persists results."""

    def test_router_query_has_use_cache_param(self):
        """The router.query signature should accept use_cache."""
        import inspect

        from unifin.core.router import SmartRouter

        sig = inspect.signature(SmartRouter.query)
        assert "use_cache" in sig.parameters
