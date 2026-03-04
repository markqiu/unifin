"""CLI entry point for the Issue-driven self-evolution workflow.

Designed to be called from GitHub Actions:

    unifin-evolve process-issue --issue-number 42
    unifin-evolve process-approval --issue-number 42

Registered as console_scripts entry point ``unifin-evolve`` in pyproject.toml.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

logger = logging.getLogger("unifin")


def _configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_process_issue(args: argparse.Namespace) -> None:
    """Handle a newly opened data-request issue."""
    from unifin.evolve.orchestrator import orchestrator

    logger.info("Processing new issue #%d ...", args.issue_number)
    plan = orchestrator.process_new_issue(args.issue_number)
    print(
        json.dumps(
            {
                "issue_number": args.issue_number,
                "model_name": plan.model_name,
                "stage": plan.stage.value,
                "sources_found": len(plan.sources),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_process_approval(args: argparse.Namespace) -> None:
    """Handle approval of a data-request issue."""
    from unifin.evolve.orchestrator import orchestrator

    logger.info("Processing approval for issue #%d ...", args.issue_number)
    result = orchestrator.process_approval(args.issue_number)
    print(
        json.dumps(
            {
                "issue_number": args.issue_number,
                "pr_number": result.get("pr_number"),
                "pr_url": result.get("pr_url"),
                "files_written": result.get("files_written", []),
                "registered": result.get("registered", False),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_process_comment(args: argparse.Namespace) -> None:
    """Handle a comment on an issue — detect /approve, /cancel, etc."""
    from unifin.evolve.github import GitHubClient

    gh = GitHubClient()
    comments = gh.get_issue_comments(args.issue_number)
    if not comments:
        logger.info("No comments found on issue #%d", args.issue_number)
        return

    last_comment = comments[-1]
    body = (last_comment.get("body") or "").strip().lower()

    # Detect approval commands
    approve_keywords = ["/approve", "/批准", "approved", "lgtm", "👍"]
    if any(kw in body for kw in approve_keywords):
        logger.info("Approval detected in comment on issue #%d", args.issue_number)
        cmd_process_approval(args)
    else:
        logger.info("No actionable command in latest comment on issue #%d", args.issue_number)


def cmd_review_pr(args: argparse.Namespace) -> None:
    """Run automated tests and LLM review on a pull request."""
    from unifin.evolve.orchestrator import orchestrator

    logger.info("Reviewing PR #%d ...", args.pr_number)
    result = orchestrator.review_pr(args.pr_number)
    print(
        json.dumps(
            {
                "pr_number": result.get("pr_number"),
                "branch": result.get("branch"),
                "tests_passed": result.get("tests", {}).get("success"),
                "lint_passed": result.get("lint", {}).get("success"),
                "review_event": result.get("review_event"),
                "review_posted": result.get("review_posted"),
                "changed_files": result.get("changed_files", []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze a data request locally (for testing / debugging)."""
    from unifin.evolve.orchestrator import orchestrator

    plan = orchestrator.analyze(args.request, provider=args.provider)
    print(plan.summary())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unifin-evolve",
        description="unifin self-evolution CLI — Issue-driven data model generation",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # process-issue
    p_issue = subparsers.add_parser(
        "process-issue",
        help="Process a newly opened data-request issue",
    )
    p_issue.add_argument("--issue-number", type=int, required=True)
    p_issue.set_defaults(func=cmd_process_issue)

    # process-approval
    p_approve = subparsers.add_parser(
        "process-approval",
        help="Process an approved data-request issue",
    )
    p_approve.add_argument("--issue-number", type=int, required=True)
    p_approve.set_defaults(func=cmd_process_approval)

    # process-comment
    p_comment = subparsers.add_parser(
        "process-comment",
        help="Process a new comment on a data-request issue",
    )
    p_comment.add_argument("--issue-number", type=int, required=True)
    p_comment.set_defaults(func=cmd_process_comment)

    # review-pr
    p_review = subparsers.add_parser(
        "review-pr",
        help="Run automated tests and LLM code review on a pull request",
    )
    p_review.add_argument("--pr-number", type=int, required=True)
    p_review.set_defaults(func=cmd_review_pr)

    # analyze (local debug)
    p_analyze = subparsers.add_parser(
        "analyze",
        help="Analyze a data request locally (no GitHub integration)",
    )
    p_analyze.add_argument("request", help="Data request description (natural language)")
    p_analyze.add_argument("--provider", default=None, help="Preferred provider name")
    p_analyze.set_defaults(func=cmd_analyze)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    _configure_logging(args.verbose)

    try:
        args.func(args)
    except Exception as e:
        logger.error("Command failed: %s", e)
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
