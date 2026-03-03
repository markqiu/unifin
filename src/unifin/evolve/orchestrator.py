"""Orchestrator — Issue-driven self-evolution workflow.

Drives the full pipeline via GitHub Issues:

Stage 1 (ANALYZING):        Parse issue title/body → DataNeed
Stage 2 (DISCOVERED):       Search provider catalogs → SourceCandidates
Stage 3 (AWAITING_APPROVAL): Post findings as issue comment, wait for user
Stage 4 (GENERATING):       Generate model + fetcher + test code
Stage 5 (TESTING):          Run generated tests
Stage 6 (PR_CREATED):       Create branch + PR with all changes
Stage 7 (COMPLETED):        Close issue after merge

Usage (GitHub Actions):
    unifin-evolve process-issue --issue-number 42
    unifin-evolve process-approval --issue-number 42

Usage (programmatic):
    from unifin.evolve.orchestrator import orchestrator
    plan = orchestrator.analyze("我需要基金净值数据")
    result = orchestrator.execute(plan)
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from unifin.evolve.discoverer import discoverer
from unifin.evolve.generator import CodeGenerator
from unifin.evolve.github import GitHubClient
from unifin.evolve.loader import loader
from unifin.evolve.schema import EvolvePlan, Stage

logger = logging.getLogger("unifin")

# Stage markers embedded in issue comments for identification
_STAGE_MARKER_PREFIX = "<!-- unifin-evolve-stage:"
_STAGE_MARKER_SUFFIX = " -->"

# Labels used to track workflow state
LABEL_DATA_REQUEST = "data-request"
LABEL_AWAITING = "awaiting-approval"
LABEL_APPROVED = "approved"
LABEL_IN_PROGRESS = "in-progress"
LABEL_COMPLETED = "completed"


def _stage_marker(stage: Stage) -> str:
    return f"{_STAGE_MARKER_PREFIX}{stage.value}{_STAGE_MARKER_SUFFIX}"


class Orchestrator:
    """End-to-end orchestration of the Issue-driven self-evolution pipeline."""

    def __init__(self, **llm_kwargs: Any):
        self._generator = CodeGenerator(**llm_kwargs)
        self._plans: dict[str, EvolvePlan] = {}

    # ===================================================================
    # Public API — programmatic (used by REST + CLI)
    # ===================================================================

    def analyze(
        self,
        user_request: str,
        *,
        provider: str | None = None,
    ) -> EvolvePlan:
        """Analyze a data request and return a draft EvolvePlan."""
        logger.info("Analyzing data need: %s", user_request[:80])
        need = self._generator.analyze_need(user_request)

        keywords = self._generator._extract_keywords(user_request, need)
        sources = discoverer.search(keywords, provider=provider)

        plan = self._generator.generate_plan(need, sources)
        plan.stage = Stage.DISCOVERED

        plan_id = f"{need.model_name}_{plan.created_at}"
        self._plans[plan_id] = plan
        return plan

    def execute(self, plan: EvolvePlan) -> dict[str, Any]:
        """Execute a plan — write files, hot-register, refresh API."""
        plan.stage = Stage.GENERATING
        result = loader.execute_plan(plan)

        if result.get("registered"):
            try:
                self._refresh_api_endpoints(plan.model_name)
                result["api_endpoint_added"] = True
            except Exception as e:
                logger.warning("Failed to refresh API endpoints: %s", e)
                result["api_endpoint_added"] = False

        plan.stage = Stage.COMPLETED if result.get("registered") else Stage.FAILED
        return result

    def auto_evolve(
        self,
        user_request: str,
        *,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Analyze + execute in one call (non-interactive)."""
        plan = self.analyze(user_request, provider=provider)
        return {
            "plan_summary": plan.summary(),
            "execution_result": self.execute(plan),
        }

    def list_plans(self) -> list[dict[str, str]]:
        return [
            {
                "plan_id": pid,
                "model_name": p.model_name,
                "stage": p.stage.value,
                "created_at": p.created_at,
            }
            for pid, p in self._plans.items()
        ]

    def get_plan(self, plan_id: str) -> EvolvePlan | None:
        return self._plans.get(plan_id)

    # ===================================================================
    # Issue-driven workflow (called by CLI / GitHub Actions)
    # ===================================================================

    def process_new_issue(
        self,
        issue_number: int,
        gh: GitHubClient | None = None,
    ) -> EvolvePlan:
        """Process a newly opened issue with label ``data-request``.

        1. Read the issue title + body
        2. Analyze → DataNeed
        3. Discover data sources
        4. Post findings as issue comment
        5. Add label ``awaiting-approval``
        """
        gh = gh or GitHubClient()
        issue = gh.get_issue(issue_number)

        user_request = f"{issue['title']}\n\n{issue.get('body', '') or ''}"
        logger.info("Processing issue #%d: %s", issue_number, issue["title"])

        # Pre-check: LLM must be configured
        if not self._generator.has_llm:
            error_msg = (
                "⚠️ **LLM 未配置**\n\n"
                "自动分析需要配置 LLM API 密钥。请在 GitHub Actions Secrets 中设置以下任一变量：\n"
                "- `UNIFIN_LLM_API_KEY`\n"
                "- `OPENAI_API_KEY`\n"
                "- `ANTHROPIC_API_KEY`\n\n"
                "配置完成后，请重新触发此 Issue 的处理流程。"
            )
            gh.post_comment(issue_number, error_msg)
            logger.error("LLM API key not configured, cannot process issue #%d", issue_number)
            raise RuntimeError(
                "LLM API key is required to process issues. "
                "Set UNIFIN_LLM_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY."
            )

        # Analyze
        gh.add_labels(issue_number, [LABEL_IN_PROGRESS])
        plan = self.analyze(user_request)
        plan.issue_number = issue_number

        # Build comment
        comment_body = self._build_discovery_comment(plan)
        gh.post_comment(issue_number, comment_body)

        # Update labels
        gh.remove_label(issue_number, LABEL_IN_PROGRESS)
        gh.add_labels(issue_number, [LABEL_AWAITING])

        plan.stage = Stage.AWAITING_APPROVAL
        self._plans[f"issue_{issue_number}"] = plan
        return plan

    def process_approval(
        self,
        issue_number: int,
        gh: GitHubClient | None = None,
    ) -> dict[str, Any]:
        """Process an approved issue — generate code, test, create PR.

        Triggered when user adds ``approved`` label or comments ``/approve``.
        """
        gh = gh or GitHubClient()
        issue = gh.get_issue(issue_number)

        # Retrieve or re-analyze the plan
        plan_key = f"issue_{issue_number}"
        plan = self._plans.get(plan_key)
        if plan is None:
            # Re-analyze from issue content
            user_request = f"{issue['title']}\n\n{issue.get('body', '') or ''}"
            plan = self.analyze(user_request)
            plan.issue_number = issue_number
            self._plans[plan_key] = plan

        # Update labels
        gh.remove_label(issue_number, LABEL_AWAITING)
        gh.add_labels(issue_number, [LABEL_IN_PROGRESS])

        # Stage 4: Generate code
        plan.stage = Stage.GENERATING
        gh.post_comment(
            issue_number,
            _stage_marker(Stage.GENERATING)
            + "\n\n⚙️ **正在生成代码...**\n\n"
            + "将生成以下文件:\n"
            + "\n".join(f"- `{f.path}`" for f in plan.files),
        )

        # Execute the plan (writes files + registers)
        result = loader.execute_plan(plan)

        if result.get("files_failed"):
            plan.stage = Stage.FAILED
            plan.error = str(result["files_failed"])
            gh.post_comment(
                issue_number,
                _stage_marker(Stage.FAILED) + f"\n\n❌ **代码生成失败**\n\n```\n{plan.error}\n```",
            )
            return result

        # Stage 5: Run tests
        plan.stage = Stage.TESTING
        test_results = self._run_tests(plan)
        if not test_results["success"]:
            plan.stage = Stage.FAILED
            plan.error = test_results.get("output", "Tests failed")
            gh.post_comment(
                issue_number,
                _stage_marker(Stage.FAILED) + f"\n\n❌ **测试失败**\n\n```\n{plan.error}\n```",
            )
            return {"error": plan.error, **result}

        # Stage 6: Create branch + PR
        branch_name = f"evolve/{plan.model_name}"
        plan.branch_name = branch_name

        try:
            gh.git_create_branch(branch_name)
            gh.git_add_commit_push(
                branch_name,
                f"feat: add {plan.model_name} model (auto-evolved from #{issue_number})",
            )
            pr = gh.create_pull_request(
                title=f"feat: add `{plan.model_name}` data model",
                body=(
                    f"Auto-generated from issue #{issue_number}.\n\n"
                    f"{plan.summary()}\n\n"
                    "---\n"
                    f"Closes #{issue_number}"
                ),
                head=branch_name,
            )
            plan.stage = Stage.PR_CREATED
            result["pr_number"] = pr["number"]
            result["pr_url"] = pr["html_url"]

            gh.post_comment(
                issue_number,
                _stage_marker(Stage.PR_CREATED)
                + f"\n\n✅ **PR 已创建**: #{pr['number']}\n\n"
                + f"🔗 {pr['html_url']}\n\n"
                + "合并 PR 后此 Issue 将自动关闭。",
            )
            gh.remove_label(issue_number, LABEL_IN_PROGRESS)

        except Exception as e:
            logger.error("Failed to create PR: %s", e)
            plan.stage = Stage.FAILED
            plan.error = str(e)
            gh.post_comment(
                issue_number,
                _stage_marker(Stage.FAILED) + f"\n\n❌ **创建 PR 失败**: {e}",
            )

        return result

    # ===================================================================
    # Comment building
    # ===================================================================

    def _build_discovery_comment(self, plan: EvolvePlan) -> str:
        """Build the discovery comment posted after analyzing an issue."""
        parts = [
            _stage_marker(Stage.DISCOVERED),
            "",
            "🔍 **数据探索完成！** 以下是分析结果：",
            "",
            plan.summary(),
            "",
            "---",
            "",
            "### 下一步操作",
            "",
        ]
        if plan.sources:
            parts.extend(
                [
                    "如果您认为以上方案可行，请执行以下任一操作来批准：",
                    "",
                    "1. 给此 Issue 添加 `approved` 标签",
                    "2. 回复评论 `/approve`",
                    "",
                    "我将自动生成代码、运行测试并创建 PR。",
                ]
            )
        else:
            parts.extend(
                [
                    "⚠️ 未找到匹配的数据源。请提供更多信息：",
                    "- 具体的数据接口或网站",
                    "- 数据字段说明",
                    "- 数据源的 Python 包名",
                ]
            )

        return "\n".join(parts)

    # ===================================================================
    # Test runner
    # ===================================================================

    @staticmethod
    def _run_tests(plan: EvolvePlan) -> dict[str, Any]:
        """Run the generated test file."""
        test_files = [f.path for f in plan.files if f.path.startswith("tests/")]
        if not test_files:
            return {"success": True, "output": "No test files to run."}

        try:
            result = subprocess.run(
                ["uv", "run", "pytest", *test_files, "-xvs"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout + result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "Tests timed out after 120s."}
        except FileNotFoundError:
            # fallback to pytest directly
            try:
                result = subprocess.run(
                    ["pytest", *test_files, "-xvs"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                return {
                    "success": result.returncode == 0,
                    "output": result.stdout + result.stderr,
                }
            except Exception as e:
                return {"success": False, "output": str(e)}

    # ===================================================================
    # Internal helpers
    # ===================================================================

    @staticmethod
    def _refresh_api_endpoints(model_name: str) -> None:
        try:
            from unifin.api.app import _add_model_endpoint

            _add_model_endpoint(model_name)
            logger.info("Added REST endpoint for model: %s", model_name)
        except Exception as e:
            logger.debug("Could not add REST endpoint: %s", e)


# Global singleton
orchestrator = Orchestrator()
