"""Structured, AI-friendly error hierarchy for unifin.

Design principle:
  Every error includes enough context for an AI caller to automatically
  learn what went wrong and self-correct on the next attempt.

Machine-parseable fields:
  - code:     stable error code  (e.g. "INVALID_SYMBOL")
  - received: the actual value that triggered the error
  - expected: list of valid values / examples
  - hint:     actionable human-readable fix suggestion
  - context:  optional dict with extra structured data
"""

from __future__ import annotations

from typing import Any


class UnifinError(Exception):
    """Base error for all unifin operations.

    Attributes:
        code:     Machine-readable error code (e.g. "INVALID_SYMBOL").
        received: The value that was received and caused the error.
        expected: List of valid values or example strings.
        hint:     Short, actionable fix suggestion.
        context:  Dict of additional structured data.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "UNIFIN_ERROR",
        received: Any = None,
        expected: list[str] | None = None,
        hint: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.received = received
        self.expected = expected or []
        self.hint = hint
        self.context = context or {}
        # Build the full message
        parts = [message]
        if received is not None:
            parts.append(f"  Received: {received!r}")
        if expected:
            parts.append(f"  Valid values: {expected}")
        if hint:
            parts.append(f"  Hint: {hint}")
        self._full_message = "\n".join(parts)
        super().__init__(self._full_message)


# ── Symbol errors ──────────────────────────────


class SymbolError(UnifinError, ValueError):
    """Symbol format or resolution error.

    Inherits from ValueError so Pydantic field_validators propagate it
    correctly as a ValidationError.
    """

    def __init__(
        self,
        message: str,
        *,
        received: Any = None,
        expected: list[str] | None = None,
        hint: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="INVALID_SYMBOL",
            received=received,
            expected=expected
            or [
                "AAPL",
                "000001.XSHE",
                "0700.XHKG",
                "600519",
                "^GSPC",
                "BRK.B",
            ],
            hint=hint,
            context=context,
        )


# ── Provider errors ────────────────────────────


class ProviderError(UnifinError):
    """Provider not found, not available for a model/exchange, or failed."""


class ProviderNotFoundError(ProviderError):
    """A requested provider name is not registered."""

    def __init__(
        self,
        provider_name: str,
        available: list[str],
    ) -> None:
        super().__init__(
            f"Provider '{provider_name}' is not registered.",
            code="PROVIDER_NOT_FOUND",
            received=provider_name,
            expected=available,
            hint=f"Use one of the registered providers: {available}",
        )


class NoProviderError(ProviderError):
    """No provider can serve a particular model + exchange combination."""

    def __init__(
        self,
        model_name: str,
        exchange: Any = None,
        requested_provider: str | None = None,
        available_providers: list[str] | None = None,
    ) -> None:
        ctx: dict[str, Any] = {"model": model_name}
        if exchange:
            ctx["exchange"] = str(exchange)
        if requested_provider:
            ctx["requested_provider"] = requested_provider
        if available_providers:
            ctx["available_providers"] = available_providers

        msg = f"No provider available for model '{model_name}'."
        parts: list[str] = []
        if exchange:
            parts.append(f"exchange={exchange}")
        if requested_provider:
            parts.append(f"requested_provider='{requested_provider}'")
        if parts:
            msg += f" (filters: {', '.join(parts)})"

        hint_parts = []
        if requested_provider and available_providers:
            hint_parts.append(
                f"Provider '{requested_provider}' does not support this model. "
                f"Try: {available_providers}"
            )
        elif exchange and available_providers:
            hint_parts.append(
                f"No provider covers exchange {exchange} for this model. "
                f"Available providers: {available_providers}"
            )
        else:
            hint_parts.append("Ensure the provider package is installed and imported.")

        super().__init__(
            msg,
            code="NO_PROVIDER",
            received=requested_provider or model_name,
            expected=available_providers or [],
            hint=" ".join(hint_parts),
            context=ctx,
        )


class AllProvidersFailedError(ProviderError):
    """All candidate providers raised exceptions."""

    def __init__(
        self,
        model_name: str,
        tried: list[str],
        last_error: Exception | None = None,
    ) -> None:
        last_msg = str(last_error) if last_error else "unknown"
        super().__init__(
            f"All providers failed for model '{model_name}'.",
            code="ALL_PROVIDERS_FAILED",
            received=model_name,
            expected=tried,
            hint=(
                f"Tried providers {tried} and all raised errors. "
                f"Last error: {last_msg}. "
                "Check network connectivity, API credentials, and symbol validity."
            ),
            context={
                "model": model_name,
                "tried_providers": tried,
                "last_error_type": type(last_error).__name__ if last_error else None,
                "last_error_message": last_msg,
            },
        )


# ── Model / registry errors ───────────────────


class ModelNotFoundError(UnifinError):
    """Requested model name is not in the registry."""

    def __init__(self, model_name: str, available: list[str]) -> None:
        # Suggest similar names for typo recovery
        suggestions = _fuzzy_suggestions(model_name, available)
        hint = f"Did you mean one of: {suggestions}?" if suggestions else ""
        if not hint:
            hint = f"Available models: {available}"
        super().__init__(
            f"Model '{model_name}' is not registered.",
            code="MODEL_NOT_FOUND",
            received=model_name,
            expected=available,
            hint=hint,
        )


class FetcherNotFoundError(UnifinError):
    """No fetcher registered for a (model, provider) pair."""

    def __init__(
        self,
        model_name: str,
        provider_name: str,
        available_providers: list[str],
    ) -> None:
        super().__init__(
            f"No fetcher for model='{model_name}', provider='{provider_name}'.",
            code="FETCHER_NOT_FOUND",
            received=f"{provider_name}/{model_name}",
            expected=[f"{p}/{model_name}" for p in available_providers],
            hint=(
                f"Provider '{provider_name}' does not implement model "
                f"'{model_name}'. Providers with this model: {available_providers}. "
                f"Either omit 'provider' to auto-select, or use one of them."
            ),
        )


# ── Parameter errors ───────────────────────────


class ParamError(UnifinError, ValueError):
    """Invalid parameter value (date, enum, etc.).

    Inherits from ValueError so Pydantic model_validators propagate it
    correctly as a ValidationError.
    """


class InvalidDateRangeError(ParamError):
    """start_date > end_date."""

    def __init__(self, start_date: Any, end_date: Any) -> None:
        super().__init__(
            "start_date must be on or before end_date.",
            code="INVALID_DATE_RANGE",
            received=f"start_date={start_date}, end_date={end_date}",
            expected=["start_date <= end_date"],
            hint="Swap start_date and end_date, or adjust the range.",
        )


class InvalidEnumValueError(ParamError):
    """Value is not a valid member of the target enum."""

    def __init__(
        self,
        param_name: str,
        received_value: Any,
        enum_class: type,
    ) -> None:
        valid = [e.value for e in enum_class]
        super().__init__(
            f"Invalid value for parameter '{param_name}'.",
            code="INVALID_ENUM_VALUE",
            received=received_value,
            expected=valid,
            hint=f"Use one of: {valid}",
            context={"param": param_name, "enum": enum_class.__name__},
        )


class InvalidDateFormatError(ParamError):
    """Date string cannot be parsed as ISO format."""

    def __init__(self, param_name: str, received_value: Any) -> None:
        super().__init__(
            f"Cannot parse '{param_name}' as a date.",
            code="INVALID_DATE_FORMAT",
            received=received_value,
            expected=["YYYY-MM-DD", "2024-01-15", "2024-12-31"],
            hint=(
                f"Provide '{param_name}' as an ISO 8601 date string "
                "(e.g., '2024-01-15') or a datetime.date object."
            ),
        )


# ── Helper ─────────────────────────────────────


def _fuzzy_suggestions(target: str, candidates: list[str], max_results: int = 3) -> list[str]:
    """Return candidates that are close to `target` (simple substring / edit match)."""
    target_lower = target.lower()
    scored: list[tuple[float, str]] = []
    for c in candidates:
        c_lower = c.lower()
        # Exact substring match
        if target_lower in c_lower or c_lower in target_lower:
            scored.append((0.0, c))
            continue
        # Simple character overlap ratio
        common = sum(1 for ch in target_lower if ch in c_lower)
        ratio = common / max(len(target_lower), len(c_lower))
        if ratio > 0.4:
            scored.append((1.0 - ratio, c))
    scored.sort()
    return [c for _, c in scored[:max_results]]
