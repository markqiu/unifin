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

    def review_pr(
        self,
        pr_number: int,
        gh: GitHubClient | None = None,
    ) -> dict[str, Any]:
        """Run tests and LLM code review on a pull request.

        1. Checkout the PR branch and run full test suite
        2. Run ruff lint
        3. Use LLM to review the diff
        4. Post all results as a PR comment/review
        """
        gh = gh or GitHubClient()
        pr = gh.get_pull_request(pr_number)
        head_branch = pr["head"]["ref"]
        logger.info("Reviewing PR #%d (%s)", pr_number, head_branch)

        result: dict[str, Any] = {"pr_number": pr_number, "branch": head_branch}

        # 1. Run test suite
        test_result = self._run_full_tests()
        result["tests"] = test_result

        # 2. Run ruff lint
        lint_result = self._run_lint()
        result["lint"] = lint_result

        # 3. Get diff and changed files for LLM review
        changed_files = gh.get_pr_files(pr_number)
        file_summaries = [
            f"{f['filename']} (+{f.get('additions', 0)} -{f.get('deletions', 0)})"
            for f in changed_files
        ]
        result["changed_files"] = [f["filename"] for f in changed_files]

        # 4. LLM code review
        llm_review: dict[str, str] | None = None
        if self._generator.has_llm:
            try:
                diff = gh.get_pr_diff(pr_number)
                llm_review = self._generator.review_code(diff, file_summaries)
                result["llm_review"] = llm_review
            except Exception as e:
                logger.warning("LLM review failed: %s", e)
                result["llm_review_error"] = str(e)
        else:
            result["llm_review_skipped"] = "LLM not configured"

        # 5. Build and post review comment
        comment_body = self._build_review_comment(
            test_result=test_result,
            lint_result=lint_result,
            file_summaries=file_summaries,
            llm_review=llm_review,
        )

        # Determine review event based on results
        all_pass = test_result["success"] and lint_result["success"]
        if not all_pass:
            event = "REQUEST_CHANGES"
        elif llm_review and llm_review.get("verdict") == "REQUEST_CHANGES":
            event = "REQUEST_CHANGES"
        elif llm_review and llm_review.get("verdict") == "APPROVE" and all_pass:
            event = "APPROVE"
        else:
            event = "COMMENT"

        try:
            gh.post_pr_review(pr_number, comment_body, event=event)
            result["review_event"] = event
            result["review_posted"] = True
        except Exception as e:
            logger.warning("Failed to post PR review, trying comment: %s", e)
            try:
                gh.post_pr_comment(pr_number, comment_body)
                result["review_posted"] = True
                result["review_fallback"] = "comment"
            except Exception as e2:
                logger.error("Failed to post PR comment: %s", e2)
                result["review_posted"] = False

        return result

    def fix_pr(
        self,
        pr_number: int,
        gh: GitHubClient | None = None,
        *,
        max_attempts: int = 1,
    ) -> dict[str, Any]:
        """Auto-fix issues found in a PR review.

        1. Check if the latest commit is from unifin-bot (loop guard)
        2. Run ``ruff check --fix`` + ``ruff format`` for lint fixes
        3. Use LLM to fix code issues based on the review
        4. Commit and push fixes (triggers re-review via synchronize)

        Parameters
        ----------
        pr_number : int
            PR number to fix.
        max_attempts : int
            Guard against runaway loops (default 1 fix per review cycle).
        """
        gh = gh or GitHubClient()
        pr = gh.get_pull_request(pr_number)
        head_branch = pr["head"]["ref"]
        logger.info("Attempting to fix PR #%d (%s)", pr_number, head_branch)

        result: dict[str, Any] = {
            "pr_number": pr_number,
            "branch": head_branch,
        }

        # Checkout the PR branch so fixes apply to the right codebase
        self._checkout_branch(head_branch)

        # Loop guard: check if latest commit was from the bot
        if self._is_bot_commit():
            logger.info("Latest commit is from unifin-bot, skipping fix to prevent infinite loop.")
            result["skipped"] = True
            result["reason"] = "bot_commit"
            gh.post_pr_comment(
                pr_number,
                "⏭️ 跳过自动修复（最近的 commit 已由 bot 提交，避免无限循环）。请人工检查剩余问题。",
            )
            return result

        fixes_applied: list[str] = []

        # Step 1: Auto-fix lint issues with ruff
        lint_fixed = self._auto_fix_lint()
        if lint_fixed["changed"]:
            fixes_applied.append(f"ruff 自动修复 {lint_fixed.get('fix_count', '?')} 个问题")
        result["lint_fix"] = lint_fixed

        # Step 2: LLM-powered code fix
        llm_fix_result: dict[str, Any] = {"applied": False}
        if self._generator.has_llm:
            try:
                llm_fix_result = self._llm_fix_pr(pr_number, gh)
                if llm_fix_result.get("applied"):
                    fixes_applied.append(f"AI 修复: {llm_fix_result.get('summary', '?')}")
            except Exception as e:
                logger.warning("LLM fix failed: %s", e)
                llm_fix_result["error"] = str(e)
        result["llm_fix"] = llm_fix_result

        # Step 3: Commit and push if any fixes were applied
        if fixes_applied:
            try:
                commit_msg = "fix: auto-fix issues from PR review\n\n"
                commit_msg += "\n".join(f"- {f}" for f in fixes_applied)
                gh.git_add_commit_push_fix(head_branch, commit_msg)
                result["pushed"] = True
                result["fixes"] = fixes_applied

                gh.post_pr_comment(
                    pr_number,
                    "🔧 **自动修复已提交**\n\n"
                    + "\n".join(f"- {f}" for f in fixes_applied)
                    + "\n\n将自动触发重新审查。",
                )
            except Exception as e:
                logger.error("Failed to push fixes: %s", e)
                result["push_error"] = str(e)
        else:
            result["pushed"] = False
            result["reason"] = "no_fixable_issues"
            gh.post_pr_comment(
                pr_number,
                "ℹ️ 自动修复未发现可自动处理的问题，请人工检查。",
            )

        return result

    @staticmethod
    def _checkout_branch(branch: str) -> None:
        """Fetch and checkout a remote branch locally."""
        subprocess.run(
            ["git", "fetch", "origin", branch],
            check=True,
            capture_output=True,
        )
        # Try checkout; if the local branch doesn't exist, create it
        result = subprocess.run(
            ["git", "checkout", branch],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            subprocess.run(
                ["git", "checkout", "-b", branch, f"origin/{branch}"],
                check=True,
                capture_output=True,
            )
        logger.info("Checked out branch %s", branch)

    # ===================================================================
    # Passive scanning (backup for missed events)
    # ===================================================================

    def scan_pending_issues(
        self,
        gh: GitHubClient | None = None,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Scan all data-request issues and PRs for pending tasks.

        Uses LLM to read all comments and determine the current status and
        needed action for each issue/PR.  Falls back to basic heuristics when
        LLM is not configured.

        Parameters
        ----------
        dry_run : bool
            If True, only report what would be done without taking action.

        Returns
        -------
        dict with counts and actions taken.
        """
        gh = gh or GitHubClient()
        result: dict[str, Any] = {
            "scanned": True,
            "dry_run": dry_run,
            "pending_analysis": [],
            "pending_approval_processing": [],
            "pending_reviews": [],
            "pending_fixes": [],
            "actions_taken": [],
        }

        # 1. Scan data-request issues
        issues = gh.list_issues(state="open", labels="data-request")
        logger.info("Found %d open data-request issues", len(issues))

        for issue in issues:
            issue_number = issue["number"]
            labels = [lb["name"] for lb in issue.get("labels", [])]
            comments = gh.get_issue_comments(issue_number)

            status = self._analyze_status(
                title=issue.get("title", ""),
                body=issue.get("body", ""),
                comments=comments,
                labels=labels,
            )
            action = status.get("needs_action", "none")
            logger.info(
                "Issue #%d: stage=%s, action=%s (confidence=%.2f, reason=%s)",
                issue_number,
                status.get("stage"),
                action,
                status.get("confidence", 0),
                status.get("reasoning", ""),
            )

            if action == "analyze":
                result["pending_analysis"].append(issue_number)
                if not dry_run:
                    try:
                        self.process_new_issue(issue_number)
                        result["actions_taken"].append(
                            {"issue": issue_number, "action": "analyzed"}
                        )
                    except Exception as e:
                        logger.warning("Failed to analyze issue #%d: %s", issue_number, e)

            elif action == "process_approval":
                result["pending_approval_processing"].append(issue_number)
                if not dry_run:
                    try:
                        approval_result = self.process_approval(issue_number)
                        result["actions_taken"].append(
                            {
                                "issue": issue_number,
                                "action": "processed_approval",
                                "pr_number": approval_result.get("pr_number"),
                            }
                        )
                    except Exception as e:
                        logger.warning("Failed to process approval #%d: %s", issue_number, e)

        # 2. Scan open PRs from evolve/* branches
        prs = gh.list_pull_requests(state="open")
        evolve_prs = [pr for pr in prs if pr.get("head", {}).get("ref", "").startswith("evolve/")]

        for pr in evolve_prs:
            pr_number = pr["number"]
            comments = gh.get_issue_comments(pr_number)

            status = self._analyze_status(
                title=pr.get("title", ""),
                body=pr.get("body", ""),
                comments=comments,
                labels=[lb["name"] for lb in pr.get("labels", [])],
            )
            action = status.get("needs_action", "none")
            logger.info(
                "PR #%d: stage=%s, action=%s (confidence=%.2f, reason=%s)",
                pr_number,
                status.get("stage"),
                action,
                status.get("confidence", 0),
                status.get("reasoning", ""),
            )

            if action == "review_pr":
                result["pending_reviews"].append(pr_number)
                if not dry_run:
                    try:
                        self.review_pr(pr_number)
                        result["actions_taken"].append({"pr": pr_number, "action": "reviewed"})
                    except Exception as e:
                        logger.warning("Failed to review PR #%d: %s", pr_number, e)

            elif action == "fix_pr":
                result["pending_fixes"].append(pr_number)
                if not dry_run:
                    try:
                        fix_result = self.fix_pr(pr_number, gh=gh)
                        result["actions_taken"].append(
                            {
                                "pr": pr_number,
                                "action": "fixed",
                                "pushed": fix_result.get("pushed", False),
                            }
                        )
                    except Exception as e:
                        logger.warning("Failed to auto-fix PR #%d: %s", pr_number, e)

        # Summary
        result["summary"] = {
            "pending_analysis_count": len(result["pending_analysis"]),
            "pending_approval_count": len(result["pending_approval_processing"]),
            "pending_review_count": len(result["pending_reviews"]),
            "pending_fix_count": len(result["pending_fixes"]),
            "actions_taken_count": len(result["actions_taken"]),
        }

        return result

    def _analyze_status(
        self,
        title: str,
        body: str,
        comments: list[dict[str, Any]],
        labels: list[str],
    ) -> dict[str, Any]:
        """Determine issue/PR status using LLM, with keyword fallback.

        Tries LLM analysis first.  If LLM is not configured or returns
        low-confidence / unknown, falls back to deterministic heuristics.
        """
        comment_dicts = [
            {
                "author": c.get("user", {}).get("login", "unknown"),
                "body": c.get("body", ""),
                "created_at": c.get("created_at", ""),
            }
            for c in comments
        ]

        status = self._generator.analyze_pr_status(
            title=title,
            body=body,
            comments=comment_dicts,
            labels=labels,
        )

        # Trust LLM result when confidence is reasonable
        confidence = status.get("confidence", 0)
        if isinstance(confidence, (int, float)) and confidence >= 0.5:
            return status

        # Fallback: basic deterministic heuristics
        logger.debug("LLM confidence too low (%.2f), using heuristic fallback", confidence)
        return self._keyword_fallback(comments, labels)

    @staticmethod
    def _keyword_fallback(
        comments: list[dict[str, Any]],
        labels: list[str],
    ) -> dict[str, Any]:
        """Simple keyword heuristics — used when LLM is unavailable."""
        bot_comments = [
            c
            for c in comments
            if c.get("user", {}).get("login") == "github-actions[bot]"
            or c.get("user", {}).get("type") == "Bot"
        ]

        has_discovered = any(
            _stage_marker(Stage.DISCOVERED) in c.get("body", "") for c in bot_comments
        )
        has_pr = any(
            "pull" in c.get("body", "").lower() and "/pull/" in c.get("body", "")
            for c in bot_comments
        )
        has_approved = "approved" in labels

        # Issue-level checks
        if not has_discovered:
            return {
                "stage": "not_analyzed",
                "needs_action": "analyze",
                "confidence": 0.8,
                "reasoning": "No analysis comment found (keyword fallback)",
            }
        if has_approved and not has_pr:
            return {
                "stage": "approved_pending_pr",
                "needs_action": "process_approval",
                "confidence": 0.8,
                "reasoning": "Approved label present but no PR link (keyword fallback)",
            }

        # PR-level checks (review / fix)
        has_review = any(
            "\U0001f916" in c.get("body", "") or "审查报告" in c.get("body", "")
            for c in bot_comments
        )
        if not has_review:
            return {
                "stage": "pr_created",
                "needs_action": "review_pr",
                "confidence": 0.8,
                "reasoning": "No review comment found (keyword fallback)",
            }

        # Check if changes requested
        needs_fix = False
        for c in reversed(bot_comments):
            b = c.get("body", "")
            if "审查报告" in b or "\U0001f916" in b:
                if "请修复" in b or "CHANGES_REQUESTED" in b or "需要修改" in b:
                    needs_fix = True
                break

        if needs_fix:
            # Check if fix already attempted
            fix_done = any(
                "修复已提交" in c.get("body", "") or "跳过" in c.get("body", "")
                for c in bot_comments
            )
            if not fix_done:
                return {
                    "stage": "reviewed_changes_requested",
                    "needs_action": "fix_pr",
                    "confidence": 0.7,
                    "reasoning": "Review requested changes, no fix yet (keyword fallback)",
                }

        return {
            "stage": "unknown",
            "needs_action": "none",
            "confidence": 0.5,
            "reasoning": "No pending action detected (keyword fallback)",
        }

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

    @staticmethod
    def _run_full_tests() -> dict[str, Any]:
        """Run the full project test suite."""
        for cmd in [
            ["uv", "run", "pytest", "--tb=short", "-q"],
            ["pytest", "--tb=short", "-q"],
        ]:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                output = result.stdout + result.stderr
                # Extract summary line (e.g. "246 passed in 8.12s")
                summary = ""
                for line in output.strip().splitlines():
                    if "passed" in line or "failed" in line or "error" in line:
                        summary = line.strip()
                return {
                    "success": result.returncode == 0,
                    "output": output,
                    "summary": summary,
                }
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "output": "Tests timed out after 300s.",
                    "summary": "TIMEOUT",
                }
            except FileNotFoundError:
                continue
        return {"success": False, "output": "pytest not found.", "summary": "NOT FOUND"}

    @staticmethod
    def _run_lint() -> dict[str, Any]:
        """Run ruff lint check on the source code."""
        for cmd in [
            ["uv", "run", "ruff", "check", "src/", "tests/", "--output-format=concise"],
            ["ruff", "check", "src/", "tests/", "--output-format=concise"],
        ]:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                output = result.stdout + result.stderr
                # Count issues
                issue_lines = [
                    line
                    for line in output.strip().splitlines()
                    if line.strip() and not line.startswith("All checks")
                ]
                return {
                    "success": result.returncode == 0,
                    "output": output,
                    "issue_count": len(issue_lines) if result.returncode != 0 else 0,
                }
            except subprocess.TimeoutExpired:
                return {"success": False, "output": "Lint timed out.", "issue_count": -1}
            except FileNotFoundError:
                continue
        return {"success": False, "output": "ruff not found.", "issue_count": -1}

    @staticmethod
    def _build_review_comment(
        *,
        test_result: dict[str, Any],
        lint_result: dict[str, Any],
        file_summaries: list[str],
        llm_review: dict[str, str] | None,
    ) -> str:
        """Build the PR review comment body."""
        parts: list[str] = ["## 🤖 自动化 PR 审查报告\n"]

        # Changed files
        parts.append("### 📁 变更文件")
        for f in file_summaries:
            parts.append(f"- `{f}`")
        parts.append("")

        # Test results
        test_icon = "✅" if test_result["success"] else "❌"
        parts.append(f"### {test_icon} 测试结果")
        if test_result.get("summary"):
            parts.append(f"```\n{test_result['summary']}\n```")
        else:
            # Truncate output for display
            output = test_result.get("output", "")
            if len(output) > 2000:
                output = output[-2000:]
                output = "...(truncated)\n" + output
            parts.append(f"```\n{output}\n```")
        parts.append("")

        # Lint results
        lint_icon = "✅" if lint_result["success"] else "⚠️"
        parts.append(f"### {lint_icon} Lint 检查 (ruff)")
        if lint_result["success"]:
            parts.append("所有检查通过，无 lint 问题。")
        else:
            output = lint_result.get("output", "")
            if len(output) > 2000:
                output = output[:2000] + "\n...(truncated)"
            parts.append(f"发现 {lint_result.get('issue_count', '?')} 个问题：")
            parts.append(f"```\n{output}\n```")
        parts.append("")

        # LLM review
        if llm_review:
            parts.append("### 🧠 AI 代码审查")
            parts.append(llm_review.get("review_body", "无审查内容"))
            parts.append("")

        # Overall verdict
        parts.append("---")
        all_pass = test_result["success"] and lint_result["success"]
        if all_pass:
            if llm_review and llm_review.get("verdict") == "APPROVE":
                parts.append("✅ **总体结论**: 所有检查通过，AI 审查通过，建议合并。")
            elif llm_review and llm_review.get("verdict") == "REQUEST_CHANGES":
                parts.append("⚠️ **总体结论**: 测试和 lint 通过，但 AI 审查发现需要修改的问题。")
            else:
                parts.append("✅ **总体结论**: 所有自动检查通过。")
        else:
            issues: list[str] = []
            if not test_result["success"]:
                issues.append("测试失败")
            if not lint_result["success"]:
                issues.append("lint 检查未通过")
            parts.append(f"❌ **总体结论**: {', '.join(issues)}，请修复后重新提交。")

        return "\n".join(parts)

    # ===================================================================
    # Internal helpers
    # ===================================================================

    @staticmethod
    def _is_bot_commit() -> bool:
        """Check if the latest commit was made by unifin-bot."""
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%an"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            author = result.stdout.strip()
            return author == "unifin-bot"
        except Exception:
            return False

    @staticmethod
    def _auto_fix_lint() -> dict[str, Any]:
        """Run ruff check --fix and ruff format to auto-fix lint issues."""
        changed = False
        fix_count = 0

        for fix_cmd in [
            ["uv", "run", "ruff", "check", "--fix", "src/", "tests/"],
            ["ruff", "check", "--fix", "src/", "tests/"],
        ]:
            try:
                result = subprocess.run(
                    fix_cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                # Count fixed issues from output
                for line in result.stderr.splitlines():
                    if "fixed" in line.lower():
                        # e.g. "Found 3 errors (2 fixed, 1 remaining)."
                        import re

                        m = re.search(r"(\d+)\s+fixed", line)
                        if m:
                            fix_count = int(m.group(1))
                changed = fix_count > 0
                break
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                return {"changed": False, "error": "ruff timeout"}

        # Also run ruff format
        for fmt_cmd in [
            ["uv", "run", "ruff", "format", "src/", "tests/"],
            ["ruff", "format", "src/", "tests/"],
        ]:
            try:
                fmt_result = subprocess.run(
                    fmt_cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                # Check if files were reformatted
                if "file" in fmt_result.stderr.lower():
                    changed = True
                break
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                pass

        # Check git diff to confirm actual changes
        try:
            diff_result = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if diff_result.stdout.strip():
                changed = True
        except Exception:
            pass

        return {"changed": changed, "fix_count": fix_count}

    def _llm_fix_pr(
        self,
        pr_number: int,
        gh: GitHubClient,
    ) -> dict[str, Any]:
        """Use LLM to fix code issues based on the latest review."""
        # Find the latest review comment from the bot
        comments = gh.get_issue_comments(pr_number)
        review_body = ""
        for comment in reversed(comments):
            body = comment.get("body", "")
            if "🤖 自动化 PR 审查报告" in body:
                review_body = body
                break

        if not review_body:
            return {"applied": False, "reason": "no_review_comment"}

        # Only fix if review had REQUEST_CHANGES
        if "请修复后重新提交" not in review_body and "REQUEST_CHANGES" not in review_body:
            return {"applied": False, "reason": "no_changes_requested"}

        # Get changed files content
        changed_files = gh.get_pr_files(pr_number)
        file_contents: dict[str, str] = {}
        for f in changed_files:
            fpath = f["filename"]
            # Only fix Python source files (not tests initially)
            if not fpath.endswith(".py"):
                continue
            try:
                with open(fpath, encoding="utf-8") as fh:
                    file_contents[fpath] = fh.read()
            except FileNotFoundError:
                logger.debug("File not found locally: %s", fpath)

        if not file_contents:
            return {"applied": False, "reason": "no_python_files"}

        # Ask LLM to fix
        fix_result = self._generator.fix_code(review_body, file_contents)
        fixed_files = fix_result.get("files", [])
        if not fixed_files:
            return {"applied": False, "reason": "llm_no_fixes"}

        # Write fixed files
        written: list[str] = []
        for finfo in fixed_files:
            fpath = finfo.get("path", "")
            content = finfo.get("content", "")
            if not fpath or not content:
                continue
            try:
                with open(fpath, "w", encoding="utf-8") as fh:
                    fh.write(content)
                written.append(fpath)
                logger.info("Fixed file: %s", fpath)
            except Exception as e:
                logger.warning("Failed to write fix for %s: %s", fpath, e)

        return {
            "applied": len(written) > 0,
            "files_fixed": written,
            "summary": fix_result.get("summary", ""),
        }

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
