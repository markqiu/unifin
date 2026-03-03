"""Orchestrator — end-to-end self-evolution workflow.

Coordinates the full pipeline:
1. analyze  — User describes data need → DataNeed
2. discover — Search known provider APIs → SourceCandidates
3. plan     — Generate model+fetcher+test code → EvolvePlan
4. confirm  — User reviews and confirms the plan
5. execute  — Write files, hot-register, immediately available

Usage (programmatic):
    from unifin.evolve.orchestrator import orchestrator

    plan = orchestrator.analyze("我需要基金净值数据")
    print(plan.summary())         # Review the plan
    result = orchestrator.execute(plan)  # User says go

Usage (REST API):
    POST /api/evolve/analyze   {"request": "我需要基金净值数据"}
    POST /api/evolve/execute   {plan JSON}
"""

from __future__ import annotations

import logging
from typing import Any

from unifin.evolve.discoverer import discoverer
from unifin.evolve.generator import CodeGenerator
from unifin.evolve.loader import loader
from unifin.evolve.schema import DataNeed, EvolvePlan

logger = logging.getLogger("unifin")


class Orchestrator:
    """End-to-end orchestration of the self-evolution pipeline."""

    def __init__(self, **llm_kwargs: Any):
        self._generator = CodeGenerator(**llm_kwargs)
        # In-memory plan store (plan_id → EvolvePlan)
        self._plans: dict[str, EvolvePlan] = {}

    # ── Step 1+2+3: Analyze + Discover + Plan (returns draft plan) ──

    def analyze(
        self,
        user_request: str,
        *,
        provider: str | None = None,
    ) -> EvolvePlan:
        """Analyze a user's data request and return a draft plan.

        Args:
            user_request: Natural language description of the data need.
            provider: Optionally limit source search to a specific provider.

        Returns:
            EvolvePlan with status="draft", ready for user review.
        """
        # Step 1: Analyze the data need
        logger.info("Analyzing data need: %s", user_request[:80])
        need = self._generator.analyze_need(user_request)

        # Check if model already exists
        from unifin.core.registry import model_registry

        if need.model_name in model_registry:
            logger.info("Model '%s' already exists — enriching with new sources", need.model_name)

        # Step 2: Discover data sources
        keywords = self._extract_keywords(user_request, need)
        sources = discoverer.search(keywords, provider=provider)

        if not sources:
            logger.warning("No data sources found for: %s", user_request[:80])
            # Still create the plan — user might provide source info manually

        # Step 3: Generate the plan
        plan = self._generator.generate_plan(need, sources)

        # Store the plan
        plan_id = f"{need.model_name}_{plan.created_at}"
        self._plans[plan_id] = plan

        return plan

    # ── Step 4+5: Execute a confirmed plan ──

    def execute(self, plan: EvolvePlan) -> dict[str, Any]:
        """Execute a confirmed plan — write files and hot-register.

        Args:
            plan: The EvolvePlan to execute (typically reviewed by user first).

        Returns:
            Report dict with success/failure details.
        """
        if plan.status not in ("draft", "confirmed"):
            return {"error": f"Plan status is '{plan.status}', expected 'draft' or 'confirmed'"}

        plan.status = "confirmed"
        logger.info("Executing plan for model: %s", plan.model_name)

        result = loader.execute_plan(plan)

        # If successful, refresh FastAPI endpoints
        if result.get("registered"):
            try:
                self._refresh_api_endpoints(plan.model_name)
                result["api_endpoint_added"] = True
            except Exception as e:
                logger.warning("Failed to refresh API endpoints: %s", e)
                result["api_endpoint_added"] = False

        return result

    # ── Convenience: analyze + execute in one call ──

    def auto_evolve(
        self,
        user_request: str,
        *,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Full auto: analyze → discover → plan → execute.

        Use this for non-interactive / automated evolution.
        For interactive use, call analyze() first, let user review,
        then call execute().
        """
        plan = self.analyze(user_request, provider=provider)
        return {
            "plan_summary": plan.summary(),
            "execution_result": self.execute(plan),
        }

    # ── List / retrieve plans ──

    def list_plans(self) -> list[dict[str, str]]:
        """List all in-memory plans."""
        return [
            {
                "plan_id": pid,
                "model_name": p.model_name,
                "status": p.status,
                "created_at": p.created_at,
            }
            for pid, p in self._plans.items()
        ]

    def get_plan(self, plan_id: str) -> EvolvePlan | None:
        """Retrieve a plan by ID."""
        return self._plans.get(plan_id)

    # ── Internals ──

    @staticmethod
    def _extract_keywords(user_request: str, need: DataNeed) -> list[str]:
        """Extract search keywords from the user request and analyzed need."""
        keywords: list[str] = []

        # From model name
        keywords.extend(need.model_name.split("_"))

        # From description
        keywords.extend(need.description.split()[:5])

        # From user request — extract Chinese and English words
        import re

        # Chinese characters (words/phrases)
        cn_words = re.findall(r"[\u4e00-\u9fff]+", user_request)
        keywords.extend(cn_words)

        # English words
        en_words = re.findall(r"[a-zA-Z]{2,}", user_request)
        keywords.extend(en_words)

        # Deduplicate while preserving order, filter out generic words
        generic = {"数据", "需要", "获取", "查询", "想", "我", "data", "get", "want"}
        seen: set[str] = set()
        unique: list[str] = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen and kw_lower not in generic and len(kw) > 1:
                seen.add(kw_lower)
                unique.append(kw)

        return unique

    @staticmethod
    def _refresh_api_endpoints(model_name: str) -> None:
        """Add a new REST endpoint for the just-registered model.

        This reuses the same endpoint factory from app.py.
        """
        try:
            from unifin.api.app import _add_model_endpoint

            _add_model_endpoint(model_name)
            logger.info("Added REST endpoint for model: %s", model_name)
        except Exception as e:
            logger.debug("Could not add REST endpoint: %s", e)


# Global singleton
orchestrator = Orchestrator()
