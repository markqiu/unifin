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
        """Create a pull request."""
        url = f"{self._base}/repos/{self._repo}/pulls"
        resp = httpx.post(
            url,
            headers=self._headers,
            json={"title": title, "body": body, "head": head, "base": base},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        pr = resp.json()
        logger.info("Created PR #%d: %s", pr["number"], title)
        return pr

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
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", message],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            check=True,
            capture_output=True,
        )

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
