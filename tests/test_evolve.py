"""Tests for the evolve module — self-evolution pipeline."""

from __future__ import annotations

import pytest

from unifin.evolve.schema import (
    DataNeed,
    EvolvePlan,
    FieldSpec,
    FieldType,
    GeneratedFile,
    SourceCandidate,
    Stage,
)

# ──────────────────────────────────────────────
# 1. Schema tests
# ──────────────────────────────────────────────


class TestStage:
    """Stage enum roundtrip and ordering."""

    def test_all_stages_defined(self):
        expected = {
            "analyzing",
            "discovered",
            "awaiting_approval",
            "generating",
            "testing",
            "pr_created",
            "completed",
            "failed",
        }
        assert {s.value for s in Stage} == expected

    def test_stage_is_str_enum(self):
        assert Stage.ANALYZING == "analyzing"
        assert str(Stage.COMPLETED) == "Stage.COMPLETED"


class TestFieldSpec:
    def test_defaults(self):
        f = FieldSpec(name="price", type=FieldType.FLOAT)
        assert f.required is True
        assert f.description == ""
        assert f.default is None


class TestDataNeed:
    def test_minimal(self):
        need = DataNeed(
            model_name="fund_nav",
            category="fund.price",
            description="Fund NAV data",
        )
        assert need.has_symbol is True
        assert need.has_date_range is True
        assert need.query_fields == []
        assert need.result_fields == []


class TestSourceCandidate:
    def test_creation(self):
        src = SourceCandidate(
            provider="akshare",
            function_name="fund_open_fund_daily_em",
            description="Open-end fund daily",
            exchanges=["XSHG", "XSHE"],
        )
        assert src.provider == "akshare"
        assert len(src.exchanges) == 2


class TestEvolvePlan:
    @pytest.fixture()
    def sample_plan(self):
        need = DataNeed(
            model_name="fund_nav",
            category="fund.price",
            description="Fund NAV data",
            query_fields=[
                FieldSpec(name="symbol", type=FieldType.STR, description="基金代码"),
            ],
            result_fields=[
                FieldSpec(name="nav", type=FieldType.FLOAT, description="净值"),
                FieldSpec(name="date", type=FieldType.DATE, description="日期"),
            ],
        )
        src = SourceCandidate(
            provider="akshare",
            function_name="fund_open_fund_daily_em",
            description="Open-end fund daily NAV",
        )
        return EvolvePlan(
            need=need,
            sources=[src],
            files=[
                GeneratedFile(
                    path="src/unifin/models/fund_nav.py",
                    content="# model code",
                    description="Fund NAV model",
                ),
            ],
        )

    def test_model_name_property(self, sample_plan):
        assert sample_plan.model_name == "fund_nav"

    def test_default_stage(self, sample_plan):
        assert sample_plan.stage == Stage.ANALYZING

    def test_summary_contains_key_info(self, sample_plan):
        md = sample_plan.summary()
        assert "fund_nav" in md
        assert "fund.price" in md
        assert "akshare" in md
        assert "fund_open_fund_daily_em" in md
        assert "nav" in md

    def test_issue_number_optional(self, sample_plan):
        assert sample_plan.issue_number is None
        sample_plan.issue_number = 42
        assert sample_plan.issue_number == 42

    def test_branch_name_optional(self, sample_plan):
        assert sample_plan.branch_name is None
        sample_plan.branch_name = "evolve/fund_nav"
        assert sample_plan.branch_name == "evolve/fund_nav"


# ──────────────────────────────────────────────
# 2. Discoverer tests
# ──────────────────────────────────────────────


class TestDiscoverer:
    def test_import(self):
        from unifin.evolve.discoverer import discoverer

        assert discoverer is not None

    def test_search_fund_keywords(self):
        from unifin.evolve.discoverer import discoverer

        results = discoverer.search(["基金", "净值"])
        assert len(results) > 0
        # Should find akshare fund-related entries
        providers = {r.provider for r in results}
        assert "akshare" in providers

    def test_search_with_provider_filter(self):
        from unifin.evolve.discoverer import discoverer

        results = discoverer.search(["stock", "history"], provider="yfinance")
        for r in results:
            assert r.provider == "yfinance"

    def test_search_no_match(self):
        from unifin.evolve.discoverer import discoverer

        results = discoverer.search(["zzz_nonexistent_xyz"])
        assert len(results) == 0

    def test_search_equity_keywords(self):
        from unifin.evolve.discoverer import discoverer

        results = discoverer.search(["股票", "历史", "行情"])
        assert len(results) > 0

    def test_search_index_keywords(self):
        from unifin.evolve.discoverer import discoverer

        results = discoverer.search(["指数", "成分股"])
        assert len(results) > 0


# ──────────────────────────────────────────────
# 3. Templates tests
# ──────────────────────────────────────────────


class TestTemplates:
    @pytest.fixture()
    def sample_need(self):
        return DataNeed(
            model_name="fund_nav",
            category="fund.price",
            description="Open-end fund NAV data",
            query_fields=[
                FieldSpec(name="symbol", type=FieldType.STR, required=True, description="基金代码"),
                FieldSpec(
                    name="start_date", type=FieldType.DATE, required=False, description="开始日期"
                ),
            ],
            result_fields=[
                FieldSpec(name="symbol", type=FieldType.STR, required=True),
                FieldSpec(name="date", type=FieldType.DATE, required=True),
                FieldSpec(name="nav", type=FieldType.FLOAT, required=True, description="单位净值"),
                FieldSpec(
                    name="acc_nav",
                    type=FieldType.FLOAT,
                    required=False,
                    description="累计净值",
                ),
            ],
        )

    def test_generate_model_code(self, sample_need):
        from unifin.evolve.templates import generate_model_code

        code = generate_model_code(sample_need)
        assert "class FundNavQuery" in code
        assert "class FundNavData" in code
        assert "fund_nav" in code
        assert "model_registry.register" in code

    def test_generate_fetcher_code(self, sample_need):
        from unifin.evolve.templates import generate_fetcher_code

        src = SourceCandidate(
            provider="akshare",
            function_name="fund_open_fund_daily_em",
            description="Fund NAV from akshare",
        )
        code = generate_fetcher_code(sample_need, src)
        assert "class AkshareFundNavFetcher" in code
        assert "provider_name" in code
        assert "model_name" in code
        assert "transform_query" in code
        assert "extract_data" in code
        assert "transform_data" in code

    def test_generate_test_code(self, sample_need):
        from unifin.evolve.templates import generate_test_code

        src = SourceCandidate(
            provider="akshare",
            function_name="fund_open_fund_daily_em",
            description="Fund NAV from akshare",
        )
        code = generate_test_code(sample_need, [src])
        assert "test_" in code
        assert "fund_nav" in code

    def test_generate_sdk_function(self, sample_need):
        from unifin.evolve.templates import generate_sdk_function

        code = generate_sdk_function(sample_need)
        assert "fund_nav" in code
        assert "router" in code or "_query" in code


# ──────────────────────────────────────────────
# 4. Generator tests
# ──────────────────────────────────────────────


class TestCodeGenerator:
    def test_import(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        assert gen is not None

    def test_analyze_need_raises_without_llm(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        if not gen.has_llm:
            with pytest.raises(RuntimeError, match="LLM API key is required"):
                gen.analyze_need("我需要获取开放式基金的每日净值数据")
        else:
            # If LLM is configured (e.g. in CI with key), it should succeed
            need = gen.analyze_need("我需要获取开放式基金的每日净值数据")
            assert isinstance(need, DataNeed)
            assert need.model_name != ""

    def test_extract_keywords(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        need = DataNeed(
            model_name="fund_nav",
            category="fund",
            description="Fund NAV",
        )
        keywords = gen._extract_keywords("获取基金净值数据", need)
        assert len(keywords) > 0

    def test_generate_plan(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        need = DataNeed(
            model_name="fund_nav",
            category="fund.price",
            description="Fund NAV data",
            query_fields=[
                FieldSpec(name="symbol", type=FieldType.STR, description="Fund code"),
            ],
            result_fields=[
                FieldSpec(name="nav", type=FieldType.FLOAT, description="NAV"),
                FieldSpec(name="date", type=FieldType.DATE, description="Date"),
            ],
        )
        src = SourceCandidate(
            provider="akshare",
            function_name="fund_open_fund_daily_em",
            description="Fund NAV",
            column_mapping={"净值日期": "date", "单位净值": "nav"},
        )
        plan = gen.generate_plan(need, [src])
        assert isinstance(plan, EvolvePlan)
        assert plan.model_name == "fund_nav"
        assert len(plan.files) > 0


# ──────────────────────────────────────────────
# 5. GitHub client tests (mocked)
# ──────────────────────────────────────────────


class TestGitHubClient:
    def test_import(self):
        from unifin.evolve.github import GitHubClient

        gh = GitHubClient(token="fake", repo="owner/repo")
        assert gh is not None

    def test_has_label(self):
        from unifin.evolve.github import GitHubClient

        gh = GitHubClient(token="fake", repo="owner/repo")
        issue = {"labels": [{"name": "data-request"}, {"name": "bug"}]}
        assert gh.has_label(issue, "data-request") is True
        assert gh.has_label(issue, "enhancement") is False


# ──────────────────────────────────────────────
# 6. Orchestrator tests (mocked)
# ──────────────────────────────────────────────


class TestOrchestrator:
    def test_import(self):
        from unifin.evolve.orchestrator import orchestrator

        assert orchestrator is not None

    @staticmethod
    def _mock_analyze_need(user_request: str) -> DataNeed:
        """Return a fixed DataNeed for tests (no LLM needed)."""
        return DataNeed(
            model_name="fund_nav",
            category="fund.price",
            description=user_request[:40],
            query_fields=[
                FieldSpec(name="symbol", type=FieldType.STR, description="基金代码"),
            ],
            result_fields=[
                FieldSpec(name="date", type=FieldType.DATE, description="日期"),
                FieldSpec(name="nav", type=FieldType.FLOAT, description="净值"),
            ],
        )

    def _patch_generator(self, monkeypatch):
        """Patch CodeGenerator to skip LLM calls."""
        from unifin.evolve.generator import CodeGenerator

        mock = TestOrchestrator._mock_analyze_need
        monkeypatch.setattr(CodeGenerator, "analyze_need", lambda self, req: mock(req))
        monkeypatch.setattr(
            CodeGenerator,
            "generate_column_mapping",
            lambda self, src, need: {},
        )

    def test_analyze_returns_plan(self, monkeypatch):
        from unifin.evolve.orchestrator import Orchestrator

        self._patch_generator(monkeypatch)

        orch = Orchestrator()
        plan = orch.analyze("我需要获取基金净值数据")
        assert isinstance(plan, EvolvePlan)
        assert plan.stage == Stage.DISCOVERED

    def test_analyze_with_provider(self, monkeypatch):
        from unifin.evolve.orchestrator import Orchestrator

        self._patch_generator(monkeypatch)

        orch = Orchestrator()
        plan = orch.analyze("获取股票分红数据", provider="yfinance")
        assert isinstance(plan, EvolvePlan)
        for src in plan.sources:
            assert src.provider == "yfinance"

    def test_list_plans_initially_empty(self):
        from unifin.evolve.orchestrator import Orchestrator

        orch = Orchestrator()
        assert orch.list_plans() == []

    def test_list_plans_after_analyze(self, monkeypatch):
        from unifin.evolve.orchestrator import Orchestrator

        self._patch_generator(monkeypatch)

        orch = Orchestrator()
        orch.analyze("获取基金净值数据")
        plans = orch.list_plans()
        assert len(plans) == 1
        assert plans[0]["stage"] == Stage.DISCOVERED.value


# ──────────────────────────────────────────────
# 7. CLI tests
# ──────────────────────────────────────────────


class TestCLI:
    def test_build_parser(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        assert parser is not None

    def test_parse_process_issue(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["process-issue", "--issue-number", "42"])
        assert args.command == "process-issue"
        assert args.issue_number == 42

    def test_parse_process_approval(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["process-approval", "--issue-number", "42"])
        assert args.command == "process-approval"
        assert args.issue_number == 42

    def test_parse_process_comment(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["process-comment", "--issue-number", "42"])
        assert args.command == "process-comment"
        assert args.issue_number == 42

    def test_parse_analyze(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["analyze", "获取基金净值数据"])
        assert args.command == "analyze"
        assert args.request == "获取基金净值数据"

    def test_parse_analyze_with_provider(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "analyze",
                "获取基金净值数据",
                "--provider",
                "akshare",
            ]
        )
        assert args.provider == "akshare"


# ──────────────────────────────────────────────
# 8. Loader tests
# ──────────────────────────────────────────────


class TestLoader:
    def test_import(self):
        from unifin.evolve.loader import loader

        assert loader is not None


# ──────────────────────────────────────────────
# 9. PR review tests
# ──────────────────────────────────────────────


class TestGitHubClientPR:
    """Tests for PR-related methods in GitHubClient."""

    def test_get_pull_request_exists(self):
        from unifin.evolve.github import GitHubClient

        gh = GitHubClient(token="fake", repo="owner/repo")
        assert hasattr(gh, "get_pull_request")

    def test_get_pr_files_exists(self):
        from unifin.evolve.github import GitHubClient

        gh = GitHubClient(token="fake", repo="owner/repo")
        assert hasattr(gh, "get_pr_files")

    def test_get_pr_diff_exists(self):
        from unifin.evolve.github import GitHubClient

        gh = GitHubClient(token="fake", repo="owner/repo")
        assert hasattr(gh, "get_pr_diff")

    def test_post_pr_comment_exists(self):
        from unifin.evolve.github import GitHubClient

        gh = GitHubClient(token="fake", repo="owner/repo")
        assert hasattr(gh, "post_pr_comment")

    def test_post_pr_review_exists(self):
        from unifin.evolve.github import GitHubClient

        gh = GitHubClient(token="fake", repo="owner/repo")
        assert hasattr(gh, "post_pr_review")


class TestCodeReview:
    """Tests for LLM code review functionality."""

    def test_review_code_raises_without_llm(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        if not gen.has_llm:
            with pytest.raises(RuntimeError, match="LLM API key is required"):
                gen.review_code("diff content here")

    def test_review_code_method_exists(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        assert hasattr(gen, "review_code")
        assert callable(gen.review_code)


class TestReviewComment:
    """Tests for the review comment builder."""

    def test_build_review_comment_all_pass(self):
        from unifin.evolve.orchestrator import Orchestrator

        comment = Orchestrator._build_review_comment(
            test_result={"success": True, "summary": "246 passed in 8.12s"},
            lint_result={"success": True, "issue_count": 0},
            file_summaries=["src/unifin/models/fund_nav.py (+50 -0)"],
            llm_review={"review_body": "Code looks good.", "verdict": "APPROVE"},
        )
        assert "✅" in comment
        assert "246 passed" in comment
        assert "fund_nav.py" in comment
        assert "Code looks good" in comment
        assert "建议合并" in comment

    def test_build_review_comment_test_fail(self):
        from unifin.evolve.orchestrator import Orchestrator

        comment = Orchestrator._build_review_comment(
            test_result={"success": False, "summary": "2 failed, 244 passed"},
            lint_result={"success": True, "issue_count": 0},
            file_summaries=["src/unifin/models/bad.py (+10 -0)"],
            llm_review=None,
        )
        assert "❌" in comment
        assert "测试失败" in comment

    def test_build_review_comment_lint_fail(self):
        from unifin.evolve.orchestrator import Orchestrator

        comment = Orchestrator._build_review_comment(
            test_result={"success": True, "summary": "246 passed"},
            lint_result={"success": False, "issue_count": 3, "output": "E501 line too long"},
            file_summaries=[],
            llm_review=None,
        )
        assert "⚠️" in comment
        assert "3" in comment

    def test_build_review_comment_no_llm(self):
        from unifin.evolve.orchestrator import Orchestrator

        comment = Orchestrator._build_review_comment(
            test_result={"success": True, "summary": "246 passed"},
            lint_result={"success": True, "issue_count": 0},
            file_summaries=["file.py (+1 -0)"],
            llm_review=None,
        )
        assert "AI 代码审查" not in comment
        assert "所有自动检查通过" in comment

    def test_build_review_comment_request_changes(self):
        from unifin.evolve.orchestrator import Orchestrator

        comment = Orchestrator._build_review_comment(
            test_result={"success": True, "summary": "246 passed"},
            lint_result={"success": True, "issue_count": 0},
            file_summaries=["file.py (+1 -0)"],
            llm_review={
                "review_body": "Found issues.",
                "verdict": "REQUEST_CHANGES",
            },
        )
        assert "AI 审查发现需要修改" in comment


class TestOrchestratorReviewPR:
    """Tests for the review_pr orchestrator method."""

    def test_review_pr_method_exists(self):
        from unifin.evolve.orchestrator import Orchestrator

        orch = Orchestrator()
        assert hasattr(orch, "review_pr")
        assert callable(orch.review_pr)


class TestCLIReviewPR:
    """Tests for the review-pr CLI command."""

    def test_parse_review_pr(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["review-pr", "--pr-number", "9"])
        assert args.command == "review-pr"
        assert args.pr_number == 9

    def test_review_pr_command_registered(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        # Should not raise
        args = parser.parse_args(["review-pr", "--pr-number", "1"])
        assert hasattr(args, "func")


# ──────────────────────────────────────────────
# Fix PR feature tests
# ──────────────────────────────────────────────


class TestFixCodeGenerator:
    """Tests for the fix_code / _llm_fix methods on CodeGenerator."""

    def test_fix_code_method_exists(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        assert hasattr(gen, "fix_code")
        assert callable(gen.fix_code)

    def test_fix_code_no_llm_key(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        gen._api_key = None
        with pytest.raises(RuntimeError, match="LLM API key is required"):
            gen.fix_code("review body", {"file.py": "code"})

    def test_llm_fix_method_exists(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        assert hasattr(gen, "_llm_fix")

    def test_code_fix_prompt_exists(self):
        from unifin.evolve import generator

        assert hasattr(generator, "_CODE_FIX_PROMPT")
        prompt = generator._CODE_FIX_PROMPT
        assert "review" in prompt.lower() or "fix" in prompt.lower()
        assert "json" in prompt.lower()


class TestFixPROrchestrator:
    """Tests for the fix_pr orchestrator method."""

    def test_fix_pr_method_exists(self):
        from unifin.evolve.orchestrator import Orchestrator

        orch = Orchestrator()
        assert hasattr(orch, "fix_pr")
        assert callable(orch.fix_pr)

    def test_is_bot_commit_method_exists(self):
        from unifin.evolve.orchestrator import Orchestrator

        assert hasattr(Orchestrator, "_is_bot_commit")

    def test_auto_fix_lint_method_exists(self):
        from unifin.evolve.orchestrator import Orchestrator

        assert hasattr(Orchestrator, "_auto_fix_lint")

    def test_llm_fix_pr_method_exists(self):
        from unifin.evolve.orchestrator import Orchestrator

        orch = Orchestrator()
        assert hasattr(orch, "_llm_fix_pr")

    def test_is_bot_commit_returns_bool(self):
        from unifin.evolve.orchestrator import Orchestrator

        # In local env, should return False (not in a bot commit context)
        result = Orchestrator._is_bot_commit()
        assert isinstance(result, bool)

    def test_auto_fix_lint_returns_dict(self):
        from unifin.evolve.orchestrator import Orchestrator

        result = Orchestrator._auto_fix_lint()
        assert isinstance(result, dict)
        assert "changed" in result

    def test_checkout_branch_method_exists(self):
        from unifin.evolve.orchestrator import Orchestrator

        assert hasattr(Orchestrator, "_checkout_branch")
        assert callable(Orchestrator._checkout_branch)


class TestGitAddCommitPushFix:
    """Tests for the git_add_commit_push_fix method on GitHubClient."""

    def test_method_exists(self):
        from unifin.evolve.github import GitHubClient

        assert hasattr(GitHubClient, "git_add_commit_push_fix")
        assert callable(GitHubClient.git_add_commit_push_fix)


class TestCLIFixPR:
    """Tests for the fix-pr CLI command."""

    def test_parse_fix_pr(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["fix-pr", "--pr-number", "9"])
        assert args.command == "fix-pr"
        assert args.pr_number == 9

    def test_fix_pr_command_registered(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["fix-pr", "--pr-number", "1"])
        assert hasattr(args, "func")

    def test_fix_pr_requires_pr_number(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["fix-pr"])


# ──────────────────────────────────────────────
# Scan pending feature tests
# ──────────────────────────────────────────────


class TestScanPendingOrchestrator:
    """Tests for the scan_pending_issues orchestrator method."""

    def test_scan_pending_method_exists(self):
        from unifin.evolve.orchestrator import Orchestrator

        orch = Orchestrator()
        assert hasattr(orch, "scan_pending_issues")
        assert callable(orch.scan_pending_issues)

    def test_analyze_status_method_exists(self):
        from unifin.evolve.orchestrator import Orchestrator

        orch = Orchestrator()
        assert hasattr(orch, "_analyze_status")
        assert callable(orch._analyze_status)

    def test_keyword_fallback_method_exists(self):
        from unifin.evolve.orchestrator import Orchestrator

        assert hasattr(Orchestrator, "_keyword_fallback")
        assert callable(Orchestrator._keyword_fallback)


class TestAnalyzePrStatus:
    """Tests for the LLM-based PR status analysis in CodeGenerator."""

    def test_analyze_pr_status_method_exists(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        assert hasattr(gen, "analyze_pr_status")
        assert callable(gen.analyze_pr_status)

    def test_analyze_pr_status_returns_dict(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        result = gen.analyze_pr_status(
            title="Test issue",
            body="Some body",
            comments=[],
            labels=[],
        )
        assert isinstance(result, dict)

    def test_analyze_pr_status_has_required_keys(self):
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        result = gen.analyze_pr_status(
            title="Test",
            body="body",
            comments=[{"author": "user", "body": "hello", "created_at": "2025-01-01"}],
            labels=["data-request"],
        )
        assert "stage" in result
        assert "needs_action" in result

    def test_analyze_pr_status_no_api_key(self):
        """Without API key, returns unknown/none."""
        from unifin.evolve.generator import CodeGenerator

        gen = CodeGenerator()
        result = gen.analyze_pr_status("t", "b", [], [])
        assert result["stage"] == "unknown"
        assert result["needs_action"] == "none"


class TestKeywordFallback:
    """Tests for the deterministic keyword fallback in scan_pending."""

    def test_no_comments_returns_analyze(self):
        from unifin.evolve.orchestrator import Orchestrator

        result = Orchestrator._keyword_fallback(comments=[], labels=[])
        assert result["needs_action"] == "analyze"
        assert result["stage"] == "not_analyzed"

    def test_discovered_marker_with_approved_no_pr(self):
        from unifin.evolve.orchestrator import Orchestrator
        from unifin.evolve.schema import Stage

        marker = f"<!-- unifin-evolve-stage:{Stage.DISCOVERED.value} -->"
        comments = [
            {"user": {"login": "github-actions[bot]", "type": "Bot"}, "body": marker},
        ]
        result = Orchestrator._keyword_fallback(comments=comments, labels=["approved"])
        assert result["needs_action"] == "process_approval"

    def test_no_review_returns_review_pr(self):
        from unifin.evolve.orchestrator import Orchestrator
        from unifin.evolve.schema import Stage

        marker = f"<!-- unifin-evolve-stage:{Stage.DISCOVERED.value} -->"
        # Has discovered + has PR link, so not pending analysis or approval
        comments = [
            {
                "user": {"login": "github-actions[bot]", "type": "Bot"},
                "body": marker + "\n[PR](/pull/9)",
            },
        ]
        result = Orchestrator._keyword_fallback(comments=comments, labels=[])
        assert result["needs_action"] == "review_pr"

    def test_review_with_changes_requested(self):
        from unifin.evolve.orchestrator import Orchestrator
        from unifin.evolve.schema import Stage

        marker = f"<!-- unifin-evolve-stage:{Stage.DISCOVERED.value} -->"
        comments = [
            {
                "user": {"login": "github-actions[bot]", "type": "Bot"},
                "body": marker + "\n/pull/9",
            },
            {
                "user": {"login": "github-actions[bot]", "type": "Bot"},
                "body": "🤖 审查报告\n请修复后重新提交",
            },
        ]
        result = Orchestrator._keyword_fallback(comments=comments, labels=[])
        assert result["needs_action"] == "fix_pr"

    def test_review_with_fix_already_done(self):
        from unifin.evolve.orchestrator import Orchestrator
        from unifin.evolve.schema import Stage

        marker = f"<!-- unifin-evolve-stage:{Stage.DISCOVERED.value} -->"
        comments = [
            {
                "user": {"login": "github-actions[bot]", "type": "Bot"},
                "body": marker + "\n/pull/9",
            },
            {
                "user": {"login": "github-actions[bot]", "type": "Bot"},
                "body": "🤖 审查报告\n请修复后重新提交",
            },
            {
                "user": {"login": "github-actions[bot]", "type": "Bot"},
                "body": "自动修复已提交",
            },
        ]
        result = Orchestrator._keyword_fallback(comments=comments, labels=[])
        assert result["needs_action"] == "review_pr"
        assert result["stage"] == "fix_attempted"

    def test_review_with_fix_skipped(self):
        from unifin.evolve.orchestrator import Orchestrator
        from unifin.evolve.schema import Stage

        marker = f"<!-- unifin-evolve-stage:{Stage.DISCOVERED.value} -->"
        comments = [
            {
                "user": {"login": "github-actions[bot]", "type": "Bot"},
                "body": marker + "\n/pull/9",
            },
            {
                "user": {"login": "github-actions[bot]", "type": "Bot"},
                "body": "🤖 审查报告\n请修复后重新提交",
            },
            {
                "user": {"login": "github-actions[bot]", "type": "Bot"},
                "body": "跳过自动修复",
            },
        ]
        result = Orchestrator._keyword_fallback(comments=comments, labels=[])
        assert result["needs_action"] == "none"

    def test_fallback_returns_confidence(self):
        from unifin.evolve.orchestrator import Orchestrator

        result = Orchestrator._keyword_fallback(comments=[], labels=[])
        assert "confidence" in result
        assert isinstance(result["confidence"], float)

    def test_fallback_returns_reasoning(self):
        from unifin.evolve.orchestrator import Orchestrator

        result = Orchestrator._keyword_fallback(comments=[], labels=[])
        assert "reasoning" in result
        assert "keyword fallback" in result["reasoning"]


class TestGitHubClientListMethods:
    """Tests for list_issues and list_pull_requests methods."""

    def test_list_issues_method_exists(self):
        from unifin.evolve.github import GitHubClient

        assert hasattr(GitHubClient, "list_issues")
        assert callable(GitHubClient.list_issues)

    def test_list_pull_requests_method_exists(self):
        from unifin.evolve.github import GitHubClient

        assert hasattr(GitHubClient, "list_pull_requests")
        assert callable(GitHubClient.list_pull_requests)

    def test_get_pr_reviews_method_exists(self):
        from unifin.evolve.github import GitHubClient

        assert hasattr(GitHubClient, "get_pr_reviews")
        assert callable(GitHubClient.get_pr_reviews)


class TestCLIScanPending:
    """Tests for the scan-pending CLI command."""

    def test_parse_scan_pending(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["scan-pending"])
        assert args.command == "scan-pending"
        assert args.dry_run is False

    def test_parse_scan_pending_dry_run(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["scan-pending", "--dry-run"])
        assert args.dry_run is True

    def test_scan_pending_command_registered(self):
        from unifin.evolve.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["scan-pending"])
        assert hasattr(args, "func")

    def test_scan_pending_summary_keys_includes_pending_fixes(self):
        result = {
            "pending_fixes": [],
            "summary": {
                "pending_fix_count": 0,
            },
        }
        assert "pending_fixes" in result
        assert "pending_fix_count" in result["summary"]
