"""unifin self-evolution module — Issue-driven auto-discover and code generation.

Workflow (GitHub Issue-driven):
1. User opens a GitHub Issue describing a data need (label: data-request).
2. GitHub Actions triggers the evolve CLI.
3. Stage 1 — Analyzer parses the issue into a DataNeed.
4. Stage 2 — Discoverer searches known provider APIs for matching sources.
5. Stage 3 — Post findings as issue comment, wait for user approval.
6. Stage 4 — Generator produces model + fetcher + test code.
7. Stage 5 — Run generated tests.
8. Stage 6 — Create PR with all changes.
9. Stage 7 — After merge, close the issue.
"""
