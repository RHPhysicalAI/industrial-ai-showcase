# This project was developed with assistance from AI tools.
"""
GitHub API client for creating PRs from agentic orchestrator.
Enables agent-opens-PR pattern: agent never calls cluster API directly,
all state changes flow through Git.
"""
import os
import httpx
from typing import Optional
from dataclasses import dataclass
import re
from datetime import datetime


@dataclass
class PRResult:
    """Result of PR creation."""
    pr_number: int
    pr_url: str
    branch_name: str
    commit_sha: str


class GitHubClient:
    """GitHub API client for PR operations with fork support."""

    def __init__(self, token: str, repo: str, fork_repo: Optional[str] = None):
        """
        Initialize GitHub client.

        Args:
            token: GitHub Personal Access Token
            repo: Target repository in format "owner/repo" (where PRs will be created)
            fork_repo: Fork repository in format "owner/repo" (where branches are pushed).
                      If None, branches are pushed to the same repo as PRs.
        """
        self.token = token
        self.repo = repo  # Target repo for PRs (e.g., RHPhysicalAI/industrial-ai-showcase)
        self.fork_repo = fork_repo or repo  # Fork repo for branches (e.g., redhatHameed/industrial-ai-showcase)
        self.api_base = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.client = httpx.Client(timeout=30.0, headers=self.headers)

    def create_pr(
        self,
        title: str,
        body: str,
        file_changes: dict[str, str],
        base_branch: str = "main"
    ) -> PRResult:
        """
        Create a PR with specified file changes.

        Args:
            title: PR title
            body: PR description (markdown)
            file_changes: Dict of {file_path: new_content}
            base_branch: Base branch (default: main)

        Returns:
            PRResult with PR details

        Example:
            >>> client = GitHubClient(token="ghp_xxx", repo="owner/repo")
            >>> file_changes = {
            ...     "infrastructure/gitops/apps/workloads/factory-a/patch.yaml": "apiVersion: v1..."
            ... }
            >>> pr = client.create_pr(
            ...     title="Promote model v1.4 to Factory A",
            ...     body="Automated model promotion from agent",
            ...     file_changes=file_changes
            ... )
            >>> print(pr.pr_url)
        """
        # 1. Get base branch SHA
        base_sha = self._get_branch_sha(base_branch)

        # 2. Create new branch
        branch_name = self._generate_branch_name(title)
        self._create_branch(branch_name, base_sha)

        # 3. Get base tree SHA
        base_tree_sha = self._get_tree_sha(base_sha)

        # 4. Create new tree with file changes
        new_tree_sha = self._create_tree(base_tree_sha, file_changes)

        # 5. Create commit
        commit_message = self._format_commit_message(title, body)
        commit_sha = self._create_commit(commit_message, new_tree_sha, base_sha)

        # 6. Update branch to point to new commit
        self._update_branch(branch_name, commit_sha)

        # 7. Create PR
        pr_data = self._create_pull_request(title, body, branch_name, base_branch)

        return PRResult(
            pr_number=pr_data["number"],
            pr_url=pr_data["html_url"],
            branch_name=branch_name,
            commit_sha=commit_sha
        )

    def _get_branch_sha(self, branch: str) -> str:
        """Get SHA of latest commit on branch from upstream repo."""
        resp = self.client.get(f"{self.api_base}/repos/{self.repo}/git/refs/heads/{branch}")
        resp.raise_for_status()
        return resp.json()["object"]["sha"]

    def _create_branch(self, branch_name: str, sha: str) -> None:
        """Create new branch from SHA in fork repo."""
        resp = self.client.post(
            f"{self.api_base}/repos/{self.fork_repo}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": sha}
        )
        resp.raise_for_status()

    def _get_tree_sha(self, commit_sha: str) -> str:
        """Get tree SHA from commit SHA from upstream repo."""
        resp = self.client.get(f"{self.api_base}/repos/{self.repo}/git/commits/{commit_sha}")
        resp.raise_for_status()
        return resp.json()["tree"]["sha"]

    def _create_tree(self, base_tree_sha: str, file_changes: dict[str, str]) -> str:
        """
        Create new tree with file changes in fork repo.

        For each file, creates a blob and adds to tree.
        """
        tree_items = []
        for path, content in file_changes.items():
            # Create blob for file content in fork
            blob_resp = self.client.post(
                f"{self.api_base}/repos/{self.fork_repo}/git/blobs",
                json={"content": content, "encoding": "utf-8"}
            )
            blob_resp.raise_for_status()
            blob_sha = blob_resp.json()["sha"]

            tree_items.append({
                "path": path,
                "mode": "100644",  # regular file
                "type": "blob",
                "sha": blob_sha
            })

        # Create tree in fork
        tree_resp = self.client.post(
            f"{self.api_base}/repos/{self.fork_repo}/git/trees",
            json={"base_tree": base_tree_sha, "tree": tree_items}
        )
        tree_resp.raise_for_status()
        return tree_resp.json()["sha"]

    def _create_commit(self, message: str, tree_sha: str, parent_sha: str) -> str:
        """Create commit in fork repo."""
        resp = self.client.post(
            f"{self.api_base}/repos/{self.fork_repo}/git/commits",
            json={
                "message": message,
                "tree": tree_sha,
                "parents": [parent_sha]
            }
        )
        resp.raise_for_status()
        return resp.json()["sha"]

    def _update_branch(self, branch_name: str, commit_sha: str) -> None:
        """Update branch to point to commit in fork repo."""
        resp = self.client.patch(
            f"{self.api_base}/repos/{self.fork_repo}/git/refs/heads/{branch_name}",
            json={"sha": commit_sha}
        )
        resp.raise_for_status()

    def _create_pull_request(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str
    ) -> dict:
        """
        Create pull request in target repo.

        If using a fork, head_branch will be prefixed with fork owner
        (e.g., "redhatHameed:agent/branch-name").
        """
        # If fork is different from target repo, prefix head with fork owner
        if self.fork_repo != self.repo:
            fork_owner = self.fork_repo.split("/")[0]
            head = f"{fork_owner}:{head_branch}"
        else:
            head = head_branch

        resp = self.client.post(
            f"{self.api_base}/repos/{self.repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base_branch
            }
        )
        resp.raise_for_status()
        return resp.json()

    def _generate_branch_name(self, title: str) -> str:
        """
        Generate branch name from PR title.

        Format: agent/slugified-title-YYYYMMDD-HHMMSS

        Example:
            "Promote model v1.4 to Factory A"
            → "agent/promote-model-v1-4-to-factory-a-20260709-143022"
        """
        # Slugify title
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        # Truncate to 50 chars
        slug = slug[:50].rstrip('-')
        # Add timestamp to ensure uniqueness
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"agent/{slug}-{timestamp}"

    def _format_commit_message(self, title: str, body: str) -> str:
        """
        Format commit message with Co-Authored-by trailer.

        Follows conventional commits + Red Hat AI compliance.
        """
        return f"""{title}

{body}

Co-Authored-by: Claude Sonnet 4.5 <noreply@anthropic.com>"""

    def merge_pr(self, pr_number: int, merge_method: str = "squash") -> dict:
        """
        Merge a pull request.

        Args:
            pr_number: PR number to merge
            merge_method: Merge method ("merge", "squash", or "rebase"). Default: "squash"

        Returns:
            Merge result with SHA

        Raises:
            httpx.HTTPStatusError: If merge fails (e.g., conflicts, checks not passed)

        Example:
            >>> client.merge_pr(pr_number=42, merge_method="squash")
            {'sha': 'abc123...', 'merged': True, 'message': 'Pull Request successfully merged'}
        """
        resp = self.client.put(
            f"{self.api_base}/repos/{self.repo}/pulls/{pr_number}/merge",
            json={"merge_method": merge_method}
        )
        resp.raise_for_status()
        return resp.json()

    def close(self):
        """Close HTTP client."""
        self.client.close()


# Singleton instance (loaded from environment)
_github_client: Optional[GitHubClient] = None


def get_github_client() -> GitHubClient:
    """
    Get GitHub client from environment.

    Reads:
        GITHUB_TOKEN: Personal Access Token with repo scope
        GITHUB_REPO: Repository in format "owner/repo" (default: RHPhysicalAI/industrial-ai-showcase)

    Returns:
        GitHubClient instance (singleton)

    Raises:
        ValueError: If GITHUB_TOKEN not set
    """
    global _github_client

    if _github_client is None:
        token = os.getenv("GITHUB_TOKEN")
        repo = os.getenv("GITHUB_REPO", "RHPhysicalAI/industrial-ai-showcase")

        if not token:
            raise ValueError(
                "GITHUB_TOKEN environment variable not set. "
                "Set this to a GitHub Personal Access Token with 'repo' scope."
            )

        _github_client = GitHubClient(token=token, repo=repo)

    return _github_client
