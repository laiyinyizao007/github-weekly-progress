"""Tests for the GitHub client module."""

import pytest
from unittest.mock import Mock, patch

from src.github_client import GitHubClient
from src.config import GitHubConfig


class TestGitHubClient:
    """Test GitHub client functionality."""

    @pytest.fixture
    def mock_github(self):
        """Create mock GitHub client."""
        with patch("src.github_client.Github") as mock:
            yield mock

    @pytest.fixture
    def client(self):
        """Create test client."""
        config = GitHubConfig(token="test-token")
        return GitHubClient(config)

    def test_initialization(self, client):
        """Test client initialization."""
        assert client.config.token == "test-token"
        assert client._client is None

    def test_should_exclude(self, client):
        """Test exclude pattern matching."""
        patterns = ["node_modules", "__pycache__", "*.pyc"]

        assert client._should_exclude("node_modules/package.json", patterns)
        assert client._should_exclude("src/__pycache__/cache.pyc", patterns)
        assert client._should_exclude("test.pyc", patterns)
        assert not client._should_exclude("src/main.py", patterns)
        assert not client._should_exclude("README.md", patterns)


class TestExcludePatterns:
    """Test various exclude patterns."""

    @pytest.fixture
    def client(self):
        config = GitHubConfig(token="test-token")
        return GitHubClient(config)

    def test_node_modules_excluded(self, client):
        """Test node_modules exclusion."""
        patterns = ["node_modules/"]
        assert client._should_exclude("node_modules/lodash/index.js", patterns)

    def test_git_excluded(self, client):
        """Test .git exclusion."""
        patterns = [".git/"]
        assert client._should_exclude(".git/config", patterns)

    def test_pycache_excluded(self, client):
        """Test __pycache__ exclusion."""
        patterns = ["__pycache__/"]
        assert client._should_exclude("__pycache__/module.cpython-39.pyc", patterns)

    def test_normal_files_not_excluded(self, client):
        """Test that normal files pass through."""
        patterns = ["node_modules/", "__pycache__/"]
        assert not client._should_exclude("src/main.py", patterns)
        assert not client._should_exclude("package.json", patterns)
        assert not client._should_exclude("README.md", patterns)
