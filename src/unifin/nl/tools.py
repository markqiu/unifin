"""Auto-generate OpenAI function-calling tool schemas from the model registry.

This module reads ``ModelRegistry`` and produces a list of tool definitions
(``{"type": "function", "function": {...}}``) that can be passed directly to
any OpenAI-compatible Chat Completions API (``tools=`` parameter).

When you register a **new model** in ``unifin.models``, a matching tool
definition is automatically available — no manual wiring needed.
"""

from __future__ import annotations

import datetime as dt
import enum
import logging
from typing import Any, Union, get_args, get_origin

from unifin.core.registry import model_registry

logger = logging.getLogger("unifin")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_tools() -> list[dict[str, Any]]:
    """Return OpenAI function-calling tool definitions for every registered model.

    Example output element::

        {
            "type": "function",
            "function": {
                "name": "query_equity_historical",
                "description": "Historical OHLCV price data ...",
                "parameters": {
                    "type": "object",
                    "properties": { ... },
                    "required": [ ... ],
                },
            },
        }
    """
    tools: list[dict[str, Any]] = []
    for model_name in model_registry.list_models():
        info = model_registry.get(model_name)
        schema = _query_to_json_schema(info.query_type)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": f"query_{model_name}",
                    "description": info.description,
                    "parameters": schema,
                },
            }
        )
    return tools


def tool_name_to_model(tool_name: str) -> str:
    """Convert ``query_equity_historical`` → ``equity_historical``."""
    if tool_name.startswith("query_"):
        return tool_name[6:]
    return tool_name


# ---------------------------------------------------------------------------
# Internal — Pydantic v2 → JSON Schema (simplified, no $ref)
# ---------------------------------------------------------------------------

_PY_TO_JSON: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _query_to_json_schema(model_cls) -> dict[str, Any]:
    """Convert a Pydantic BaseModel class into a flat JSON Schema dict."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, field_info in model_cls.model_fields.items():
        prop = _annotation_to_schema(field_info.annotation)
        if field_info.description:
            prop["description"] = field_info.description
        if field_info.default is not None and not field_info.is_required():
            prop["default"] = _serialize_default(field_info.default)
        properties[name] = prop
        if field_info.is_required():
            required.append(name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _annotation_to_schema(annotation) -> dict[str, Any]:
    """Map a Python type annotation to a JSON Schema property."""
    # Handle None / NoneType
    if annotation is type(None):
        return {"type": "null"}

    # Unwrap Optional[X] (= Union[X, None])
    origin = get_origin(annotation)
    if origin is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return _annotation_to_schema(args[0])
        # Union of multiple types
        return {"anyOf": [_annotation_to_schema(a) for a in args]}

    # Enum → string with enum values
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return {
            "type": "string",
            "enum": [e.value for e in annotation],
        }

    # date / datetime → string with format
    if annotation is dt.date:
        return {"type": "string", "format": "date", "description": "ISO date (YYYY-MM-DD)"}
    if annotation is dt.datetime:
        return {"type": "string", "format": "date-time"}

    # Primitive
    json_type = _PY_TO_JSON.get(annotation)
    if json_type:
        return {"type": json_type}

    # Fallback
    return {"type": "string"}


def _serialize_default(value: Any) -> Any:
    """Make defaults JSON-serialisable."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value
