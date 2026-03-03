"""FastAPI application — auto-generates REST endpoints from the model registry.

Usage:
    uvicorn unifin.api.app:app --reload

Every model registered in ``ModelRegistry`` gets a ``POST /api/{category}/{name}``
endpoint whose request body **is** the model's Query schema and whose response is
a list of the model's Data schema.  Adding a new model + fetcher automatically
exposes a new endpoint — no manual wiring required.

Additional convenience endpoints:

    GET  /api/models          — list all registered models
    GET  /api/providers       — list all registered providers
    GET  /api/health          — health check
"""

import logging
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel as PydanticBaseModel

logger = logging.getLogger("unifin")

# ── Ensure models & providers are registered ──
import unifin  # noqa: F401, E402  (triggers __init__.py registration)
from unifin.core.registry import ModelInfo, model_registry, provider_registry  # noqa: E402
from unifin.core.router import router  # noqa: E402

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="unifin API",
    description=(
        "Unified financial data platform — auto-generated endpoints "
        "from the model registry.  Every data model is a POST endpoint.\n\n"
        "**Natural language**: POST ``/api/nl/ask`` with a free-form question."
    ),
    version=unifin.__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Meta endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok", "version": unifin.__version__}


class ModelSummary(PydanticBaseModel):
    name: str
    category: str
    description: str
    query_fields: dict[str, str]
    result_fields: dict[str, str]


@app.get("/api/models", tags=["meta"], response_model=list[ModelSummary])
def list_models() -> list[dict[str, Any]]:
    """List every registered data model with query & result schemas."""
    out: list[dict[str, Any]] = []
    for name in model_registry.list_models():
        info = model_registry.get(name)
        out.append(
            {
                "name": info.name,
                "category": info.category,
                "description": info.description,
                "query_fields": {
                    k: _field_summary(v) for k, v in info.query_type.model_fields.items()
                },
                "result_fields": {
                    k: _field_summary(v) for k, v in info.result_type.model_fields.items()
                },
            }
        )
    return out


class ProviderSummary(PydanticBaseModel):
    name: str
    description: str
    website: str
    models: list[str]


@app.get("/api/providers", tags=["meta"], response_model=list[ProviderSummary])
def list_providers() -> list[dict[str, Any]]:
    """List every registered provider and the models it covers."""
    out: list[dict[str, Any]] = []
    for name in provider_registry.list_providers():
        info = provider_registry.get_provider_info(name)
        out.append(
            {
                "name": info.name,
                "description": info.description,
                "website": info.website,
                "models": sorted(info.coverage.keys()),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Auto-generated data endpoints
# ---------------------------------------------------------------------------


def _register_data_endpoints() -> None:
    """Walk the registry and create one POST endpoint per model."""
    for model_name in model_registry.list_models():
        _add_model_endpoint(model_name)


def _add_model_endpoint(model_name: str) -> None:
    """Create ``POST /api/{category_path}/{leaf}`` for *model_name*."""
    info: ModelInfo = model_registry.get(model_name)
    query_type = info.query_type
    result_type = info.result_type

    # Build URL path from category: "equity.price" → "/api/equity/price/historical"
    cat_path = info.category.replace(".", "/")
    leaf = model_name
    path = f"/api/{cat_path}/{leaf}"

    tag = info.category

    # Capture model_name in a factory to avoid closure issues
    def _make_endpoint(_model_name: str, _query_type: type):
        async def _endpoint(
            request_body: _query_type = Body(...),  # type: ignore[valid-type]
            provider: str | None = Query(default=None, description="Explicit provider name"),
        ) -> list[dict[str, Any]]:
            try:
                results = router.query(_model_name, request_body, provider=provider)
                return results
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        _endpoint.__name__ = f"query_{_model_name}"
        _endpoint.__qualname__ = f"query_{_model_name}"
        _endpoint.__doc__ = info.description or f"Query {_model_name}"
        return _endpoint

    endpoint_fn = _make_endpoint(model_name, query_type)

    app.post(
        path,
        tags=[tag],
        response_model=list[result_type],  # type: ignore[valid-type]
        summary=info.description,
        name=model_name,
    )(endpoint_fn)

    # Also register a convenience alias via model name directly
    alias_path = f"/api/query/{model_name}"
    app.post(
        alias_path,
        tags=[tag],
        response_model=list[result_type],  # type: ignore[valid-type]
        summary=info.description,
        name=f"{model_name}_alias",
        include_in_schema=False,  # keep docs clean
    )(endpoint_fn)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _field_summary(field_info) -> str:
    """Return a short human-readable type string for a Pydantic field."""
    annotation = field_info.annotation
    desc = field_info.description or ""
    type_name = getattr(annotation, "__name__", str(annotation))
    required = field_info.is_required()
    parts = [type_name]
    if not required:
        parts.append("optional")
    if desc:
        parts.append(desc)
    return " | ".join(parts)


# ── Register all endpoints on import ──
_register_data_endpoints()


# ---------------------------------------------------------------------------
# Natural Language endpoint
# ---------------------------------------------------------------------------


class NLRequest(PydanticBaseModel):
    question: str
    provider: str | None = None


class NLResponse(PydanticBaseModel):
    answer: str
    data: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []


@app.post("/api/nl/ask", tags=["natural-language"], response_model=NLResponse)
def nl_ask(req: NLRequest) -> dict[str, Any]:
    """Ask a natural-language question, get structured data + answer."""
    from unifin.nl.engine import NLEngine

    engine = NLEngine()
    return engine.ask(req.question, provider=req.provider)


# ---------------------------------------------------------------------------
# Tool schema introspection (useful for AI agent integration)
# ---------------------------------------------------------------------------


@app.get("/api/nl/tools", tags=["natural-language"])
def nl_tools() -> list[dict[str, Any]]:
    """Return OpenAI function-calling tool definitions for all models."""
    from unifin.nl.tools import generate_tools

    return generate_tools()


# ---------------------------------------------------------------------------
# Self-evolution endpoints
# ---------------------------------------------------------------------------


class EvolveAnalyzeRequest(PydanticBaseModel):
    request: str
    provider: str | None = None


class EvolveFilePreview(PydanticBaseModel):
    path: str
    content: str
    description: str


class EvolveAnalyzeResponse(PydanticBaseModel):
    model_name: str
    category: str
    description: str
    summary: str
    sources: list[dict[str, Any]] = []
    files: list[EvolveFilePreview] = []
    status: str = "draft"


@app.post("/api/evolve/analyze", tags=["self-evolution"], response_model=EvolveAnalyzeResponse)
def evolve_analyze(req: EvolveAnalyzeRequest) -> dict[str, Any]:
    """Analyze a data need and return a draft plan with generated code.

    The user describes what data they need in natural language.
    The system analyzes the need, searches for data sources, and generates
    model + fetcher + test code — all returned for review before execution.
    """
    from unifin.evolve.orchestrator import orchestrator

    plan = orchestrator.analyze(req.request, provider=req.provider)
    return {
        "model_name": plan.need.model_name,
        "category": plan.need.category,
        "description": plan.need.description,
        "summary": plan.summary(),
        "sources": [
            {
                "provider": s.provider,
                "function": s.function_name,
                "description": s.description,
                "columns": s.sample_columns,
                "exchanges": s.exchanges,
            }
            for s in plan.sources
        ],
        "files": [
            {"path": f.path, "content": f.content, "description": f.description}
            for f in plan.files
        ],
        "status": plan.status,
    }


class EvolveExecuteRequest(PydanticBaseModel):
    request: str
    provider: str | None = None


class EvolveExecuteResponse(PydanticBaseModel):
    model_name: str
    files_written: list[str] = []
    files_failed: list[dict[str, str]] = []
    registered: bool = False
    init_updated: bool = False
    api_endpoint_added: bool = False


@app.post("/api/evolve/execute", tags=["self-evolution"], response_model=EvolveExecuteResponse)
def evolve_execute(req: EvolveExecuteRequest) -> dict[str, Any]:
    """Execute: analyze → discover → generate → write → register.

    After confirmation, the system writes files, hot-registers the new model
    and fetcher(s), and adds REST/NL endpoints — all in one call.
    """
    from unifin.evolve.orchestrator import orchestrator

    plan = orchestrator.analyze(req.request, provider=req.provider)
    result = orchestrator.execute(plan)
    return result


@app.get("/api/evolve/sources", tags=["self-evolution"])
def evolve_list_sources(provider: str | None = None) -> list[dict[str, str]]:
    """List all known data sources in the discovery catalog."""
    from unifin.evolve.discoverer import discoverer

    return discoverer.list_available_sources(provider=provider)


@app.get("/api/evolve/search", tags=["self-evolution"])
def evolve_search_sources(
    q: str = Query(..., description="Search keywords (Chinese or English)"),
    provider: str | None = Query(default=None, description="Limit to a specific provider"),
) -> list[dict[str, Any]]:
    """Search for data sources matching keywords."""
    from unifin.evolve.discoverer import discoverer

    keywords = q.split()
    candidates = discoverer.search(keywords, provider=provider)
    return [
        {
            "provider": c.provider,
            "function": c.function_name,
            "description": c.description,
            "columns": c.sample_columns,
            "exchanges": c.exchanges,
        }
        for c in candidates
    ]
