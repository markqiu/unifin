"""GitHub Issue interaction — read, comment, label, and manage issues.

Uses the GitHub REST API (via httpx) to drive the issue-based workflow.
Requires a ``GITHUB_TOKEN`` environment variable with ``issues`` and
``pull-requests`` write permissions.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

import httpx

logger = logging.getLogger("unifin")

_TIMEOUT = 30.0


class GitHubClient:
    """Interact with GitHub Issues and Pull Requests via the REST API."""

    def __init__(
        self,
        *,
        token: str | None = None,
        repo: str | None = None,
    ):
        self._token = token or os.environ.get("GITHUB_TOKEN", "")
        # repo format: "owner/repo"
        self._repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
        self._base = "https://api.github.com"

    @property
    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    # ── Issue read ──

    def get_issue(self, issue_number: int) -> dict[str, Any]:
        """Fetch an issue by number."""
        url = f"{self._base}/repos/{self._repo}/issues/{issue_number}"
        resp = httpx.get(url, headers=self._headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def get_issue_comments(self, issue_number: int) -> list[dict[str, Any]]:
        """Fetch all comments on an issue."""
        url = f"{self._base}/repos/{self._repo}/issues/{issue_number}/comments"
        resp = httpx.get(url, headers=self._headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def list_issues(
        self,
        *,
        state: str = "open",
        labels: str | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """List issues with optional filters.

        Parameters
        ----------
        state : str
            "open", "closed", or "all".
        labels : str | None
            Comma-separated list of label names to filter by.
        per_page : int
            Results per page (max 100).

        Returns
        -------
        list of issue dicts.
        """
        url = f"{self._base}/repos/{self._repo}/issues"
        params: dict[str, Any] = {"state": state, "per_page": per_page}
        if labels:
            params["labels"] = labels
        resp = httpx.get(url, headers=self._headers, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    # ── Issue write ──

    def post_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        """Post a comment on an issue."""
        url = f"{self._base}/repos/{self._repo}/issues/{issue_number}/comments"
        resp = httpx.post(
            url,
            headers=self._headers,
            json={"body": body},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        logger.info("Posted comment on issue #%d", issue_number)
        return resp.json()

    def add_labels(self, issue_number: int, labels: list[str]) -> None:
        """Add labels to an issue."""
        url = f"{self._base}/repos/{self._repo}/issues/{issue_number}/labels"
        httpx.post(
            url,
            headers=self._headers,
            json={"labels": labels},
            timeout=_TIMEOUT,
        ).raise_for_status()

    def remove_label(self, issue_number: int, label: str) -> None:
        """Remove a label from an issue (ignores 404)."""
        url = f"{self._base}/repos/{self._repo}/issues/{issue_number}/labels/{label}"
        resp = httpx.delete(url, headers=self._headers, timeout=_TIMEOUT)
        if resp.status_code != 404:
            resp.raise_for_status()

    def close_issue(self, issue_number: int) -> None:
        """Close an issue."""
        url = f"{self._base}/repos/{self._repo}/issues/{issue_number}"
        httpx.patch(
            url,
            headers=self._headers,
            json={"state": "closed"},
            timeout=_TIMEOUT,
        ).raise_for_status()
        logger.info("Closed issue #%d", issue_number)

    # ── Pull Request ──

    def create_pull_request(
        self,
        *,
        title: str,
        body: str,
        head: str,
        base: str = "main",
    ) -> dict[str, Any]:
        """Create a pull request.

        Tries the REST API first; if that returns 403 (common when the
        repository has "Allow GitHub Actions to create PRs" disabled),
        falls back to the ``gh`` CLI which handles token scopes differently.
        """
        url = f"{self._base}/repos/{self._repo}/pulls"
        resp = httpx.post(
            url,
            headers=self._headers,
            json={"title": title, "body": body, "head": head, "base": base},
            timeout=_TIMEOUT,
        )

        if resp.status_code == 403:
            logger.warning("REST API returned 403 for PR creation, trying gh CLI fallback")
            return self._create_pr_via_cli(title=title, body=body, head=head, base=base)

        resp.raise_for_status()
        pr = resp.json()
        logger.info("Created PR #%d: %s", pr["number"], title)
        return pr

    @staticmethod
    def _create_pr_via_cli(
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict[str, Any]:
        """Create a PR using the ``gh`` CLI (requires GITHUB_TOKEN env var)."""
        result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--head",
                head,
                "--base",
                base,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        pr_url = result.stdout.strip()
        # Extract PR number from URL like https://github.com/owner/repo/pull/7
        pr_number = int(pr_url.rstrip("/").split("/")[-1]) if pr_url else 0
        logger.info("Created PR #%d via gh CLI: %s", pr_number, pr_url)
        return {"number": pr_number, "html_url": pr_url}

    # ── Git operations (local) ──

    @staticmethod
    def git_create_branch(branch_name: str) -> None:
        """Create and checkout a new git branch."""
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            check=True,
            capture_output=True,
        )

    @staticmethod
    def git_add_commit_push(branch_name: str, message: str) -> None:
        """Stage all changes, commit, and push to remote."""
        # Ensure git user is configured (required in CI environments)
        subprocess.run(
            ["git", "config", "user.name", "unifin-bot"],
            check=False,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "unifin-bot@users.noreply.github.com"],
            check=False,
            capture_output=True,
        )

        # Configure auth for push (actions/checkout cleans up extraheader)
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            repo = os.environ.get("GITHUB_REPOSITORY", "")
            if repo:
                # Set authenticated remote URL directly
                subprocess.run(
                    [
                        "git",
                        "remote",
                        "set-url",
                        "origin",
                        f"https://x-access-token:{token}@github.com/{repo}.git",
                    ],
                    check=False,
                    capture_output=True,
                )

        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", message],
            check=True,
            capture_output=True,
        )

        # Delete remote branch if it exists (from previous failed attempts)
        subprocess.run(
            ["git", "push", "origin", "--delete", branch_name],
            check=False,
            capture_output=True,
        )

        result = subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("git push failed: %s", result.stderr.strip())
            raise subprocess.CalledProcessError(
                result.returncode, result.args, result.stdout, result.stderr
            )

    @staticmethod
    def git_add_commit_push_fix(branch_name: str, message: str) -> None:
        """Stage all changes, commit, and push fixes to an existing PR branch.

        Unlike ``git_add_commit_push``, this does NOT delete the remote branch
        first — it simply pushes additional commits onto the existing branch.
        """
        # Ensure git user is configured
        subprocess.run(
            ["git", "config", "user.name", "unifin-bot"],
            check=False,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "unifin-bot@users.noreply.github.com"],
            check=False,
            capture_output=True,
        )

        # Configure auth for push
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            repo = os.environ.get("GITHUB_REPOSITORY", "")
            if repo:
                subprocess.run(
                    [
                        "git",
                        "remote",
                        "set-url",
                        "origin",
                        f"https://x-access-token:{token}@github.com/{repo}.git",
                    ],
                    check=False,
                    capture_output=True,
                )

        # Ensure we are on the correct branch
        current = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
        )
        if current.returncode == 0 and current.stdout.strip() != branch_name:
            # Fetch and checkout the target branch
            subprocess.run(
                ["git", "fetch", "origin", branch_name],
                check=False,
                capture_output=True,
            )
            result_co = subprocess.run(
                ["git", "checkout", branch_name],
                capture_output=True,
                text=True,
            )
            if result_co.returncode != 0:
                subprocess.run(
                    ["git", "checkout", "-b", branch_name, f"origin/{branch_name}"],
                    check=True,
                    capture_output=True,
                )

        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)

        # Check if there are staged changes
        diff_result = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            capture_output=True,
            text=True,
        )
        if not diff_result.stdout.strip():
            logger.info("No staged changes to commit for fix.")
            return

        subprocess.run(
            ["git", "commit", "-m", message],
            check=True,
            capture_output=True,
        )

        result = subprocess.run(
            ["git", "push", "origin", branch_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("git push fix failed: %s", result.stderr.strip())
            raise subprocess.CalledProcessError(
                result.returncode, result.args, result.stdout, result.stderr
            )
        logger.info("Pushed fix commit to %s", branch_name)

    # ── Pull Request read ──

    def get_pull_request(self, pr_number: int) -> dict[str, Any]:
        """Fetch a pull request by number."""
        url = f"{self._base}/repos/{self._repo}/pulls/{pr_number}"
        resp = httpx.get(url, headers=self._headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def list_pull_requests(
        self,
        *,
        state: str = "open",
        head: str | None = None,
        base: str | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """List pull requests with optional filters.

        Parameters
        ----------
        state : str
            "open", "closed", or "all".
        head : str | None
            Filter by head branch (format: "user:branch" or just "branch").
        base : str | None
            Filter by base branch.
        per_page : int
            Results per page (max 100).

        Returns
        -------
        list of PR dicts.
        """
        url = f"{self._base}/repos/{self._repo}/pulls"
        params: dict[str, Any] = {"state": state, "per_page": per_page}
        if head:
            params["head"] = head
        if base:
            params["base"] = base
        resp = httpx.get(url, headers=self._headers, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def get_pr_files(self, pr_number: int) -> list[dict[str, Any]]:
        """Fetch the list of files changed in a pull request."""
        url = f"{self._base}/repos/{self._repo}/pulls/{pr_number}/files"
        resp = httpx.get(url, headers=self._headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def get_pr_diff(self, pr_number: int) -> str:
        """Fetch the unified diff of a pull request."""
        url = f"{self._base}/repos/{self._repo}/pulls/{pr_number}"
        headers = {**self._headers, "Accept": "application/vnd.github.v3.diff"}
        resp = httpx.get(url, headers=headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.text

    def get_pr_reviews(self, pr_number: int) -> list[dict[str, Any]]:
        """Fetch all reviews on a pull request."""
        url = f"{self._base}/repos/{self._repo}/pulls/{pr_number}/reviews"
        resp = httpx.get(url, headers=self._headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def post_pr_comment(self, pr_number: int, body: str) -> dict[str, Any]:
        """Post a comment on a pull request (issue comment endpoint)."""
        # PRs use the issue comments endpoint for general comments
        url = f"{self._base}/repos/{self._repo}/issues/{pr_number}/comments"
        resp = httpx.post(
            url,
            headers=self._headers,
            json={"body": body},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        logger.info("Posted comment on PR #%d", pr_number)
        return resp.json()

    def post_pr_review(
        self,
        pr_number: int,
        body: str,
        event: str = "COMMENT",
    ) -> dict[str, Any]:
        """Create a pull request review.

        Parameters
        ----------
        pr_number : int
            The PR number.
        body : str
            Review body text (Markdown).
        event : str
            One of "APPROVE", "REQUEST_CHANGES", "COMMENT".
        """
        url = f"{self._base}/repos/{self._repo}/pulls/{pr_number}/reviews"
        resp = httpx.post(
            url,
            headers=self._headers,
            json={"body": body, "event": event},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        logger.info("Posted PR review on #%d (event=%s)", pr_number, event)
        return resp.json()

    # ── Helpers ──

    def has_label(self, issue: dict[str, Any], label_name: str) -> bool:
        """Check if an issue dict has a specific label."""
        return any(lb["name"] == label_name for lb in issue.get("labels", []))

    def find_bot_comment_with_stage(
        self,
        issue_number: int,
        stage_marker: str,
    ) -> dict[str, Any] | None:
        """Find the latest bot comment containing a stage marker."""
        comments = self.get_issue_comments(issue_number)
        for comment in reversed(comments):
            body = comment.get("body", "")
            if stage_marker in body:
                return comment
        return None


# Global singleton
github_client = GitHubClient()
