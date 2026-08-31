"""GitHub API client for fetching repository content."""

import base64
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from github import Github
from github.ContentFile import ContentFile
from github.Repository import Repository

from src.config import GitHubConfig


class GitHubClient:
    """Client for interacting with GitHub API."""

    def __init__(self, config: GitHubConfig):
        """Initialize GitHub client.

        Args:
            config: GitHub configuration with token
        """
        self.config = config
        self._client: Optional[Github] = None
        self._repo_cache: Dict[str, Repository] = {}

    @property
    def client(self) -> Github:
        """Get or create GitHub client instance."""
        if self._client is None:
            self._client = Github(self.config.token)
        return self._client

    def get_repository(self, repo_name: str) -> Repository:
        """Get a repository by name (format: owner/repo).

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            Repository object

        Raises:
            ValueError: If repository not found or not accessible
        """
        if repo_name in self._repo_cache:
            return self._repo_cache[repo_name]

        try:
            repo = self.client.get_repo(repo_name)
            self._repo_cache[repo_name] = repo
            return repo
        except Exception as e:
            raise ValueError(f"Failed to access repository '{repo_name}': {e}")

    def get_file_tree(
        self,
        repo_name: str,
        path: str = "",
        ref: str = "main",
        recursive: bool = True,
    ) -> List[Dict]:
        """Get all files in a repository recursively.

        Args:
            repo_name: Repository name in format "owner/repo"
            path: Subdirectory path to start from
            ref: Branch or commit SHA
            recursive: Whether to fetch recursively

        Returns:
            List of file info dictionaries with keys: path, type, size, sha, url
        """
        repo = self.get_repository(repo_name)

        # Try main branch first, fall back to master
        try:
            branch = repo.get_branch(ref)
        except Exception:
            try:
                branch = repo.get_branch("master")
                ref = "master"
            except Exception as e:
                raise ValueError(f"Could not find branch 'main' or 'master': {e}")

        try:
            tree = repo.get_git_tree(branch.commit.sha, recursive=recursive)
        except Exception as e:
            raise ValueError(f"Failed to get file tree: {e}")

        files = []
        for item in tree.tree:
            if item.type == "blob":  # Only files, not directories
                files.append({
                    "path": item.path,
                    "type": item.type,
                    "size": item.size,
                    "sha": item.sha,
                    "url": item.url,
                })

        return files

    def get_file_content(
        self,
        repo_name: str,
        path: str,
        ref: str = "main",
    ) -> Tuple[str, str]:
        """Get content of a specific file.

        Args:
            repo_name: Repository name in format "owner/repo"
            path: File path in repository
            ref: Branch or commit SHA

        Returns:
            Tuple of (content, encoding)

        Raises:
            ValueError: If file not found or not accessible
        """
        repo = self.get_repository(repo_name)

        try:
            content_file = repo.get_contents(path, ref=ref)
        except Exception as e:
            raise ValueError(f"Failed to get file '{path}': {e}")

        if isinstance(content_file, list):
            raise ValueError(f"'{path}' is a directory, not a file")

        if content_file.encoding == "base64":
            content = base64.b64decode(content_file.content).decode("utf-8")
        else:
            content = content_file.content

        return content, content_file.encoding

    def fetch_repository(
        self,
        repo_name: str,
        exclude_patterns: Optional[List[str]] = None,
        max_file_size_mb: int = 5,
        ref: str = "main",
    ) -> Dict[str, str]:
        """Fetch all files from a repository.

        Args:
            repo_name: Repository name in format "owner/repo"
            exclude_patterns: List of glob patterns to exclude
            max_file_size_mb: Maximum file size to fetch in MB
            ref: Branch or commit SHA

        Returns:
            Dictionary mapping file paths to file contents
        """
        exclude_patterns = exclude_patterns or []
        max_file_size_bytes = max_file_size_mb * 1024 * 1024

        files = self.get_file_tree(repo_name, ref=ref)
        contents: Dict[str, str] = {}

        for file_info in files:
            path = file_info["path"]

            # Skip files matching exclude patterns
            if self._should_exclude(path, exclude_patterns):
                continue

            # Skip files that are too large
            if file_info.get("size", 0) > max_file_size_bytes:
                continue

            try:
                content, _ = self.get_file_content(repo_name, path, ref=ref)
                contents[path] = content
            except Exception:
                # Skip files that can't be decoded (e.g., binary files)
                continue

        return contents

    def _should_exclude(self, path: str, patterns: List[str]) -> bool:
        """Check if a path should be excluded based on patterns.

        Args:
            path: File path to check
            patterns: List of exclude patterns

        Returns:
            True if path should be excluded
        """
        import fnmatch

        path_parts = path.split("/")

        for pattern in patterns:
            # Check if any path component matches
            for part in path_parts:
                if fnmatch.fnmatch(part, pattern.rstrip("/")):
                    return True
            # Check full path
            if fnmatch.fnmatch(path, pattern):
                return True

        return False

    def get_repo_info(self, repo_name: str) -> Dict:
        """Get repository metadata.

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            Dictionary with repository information
        """
        repo = self.get_repository(repo_name)

        return {
            "name": repo.name,
            "full_name": repo.full_name,
            "description": repo.description or "",
            "url": repo.html_url,
            "default_branch": repo.default_branch,
            "language": repo.language,
            "stars": repo.stargazers_count,
            "forks": repo.forks_count,
            "open_issues": repo.open_issues_count,
            "created_at": repo.created_at.isoformat() if repo.created_at else None,
            "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
            "topics": repo.topics or [],
        }
