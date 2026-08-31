"""Configuration management module for GitHub Agent RAG system."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv


@dataclass
class GitHubConfig:
    """GitHub API configuration."""

    token: str


@dataclass
class LLMConfig:
    """LLM API configuration."""

    provider: str = "openai"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-3-haiku-20240307"
    anthropic_base_url: Optional[str] = None


@dataclass
class EmbeddingConfig:
    """Embedding model configuration."""

    provider: str = "sentence-transformers"
    model: str = "all-MiniLM-L6-v2"
    openai_api_key: Optional[str] = None


@dataclass
class ChromaConfig:
    """ChromaDB configuration."""

    db_path: str = "./chroma_db"
    collection_name: str = "github_repo_collection"


@dataclass
class AppConfig:
    """Application configuration."""

    log_level: str = "INFO"
    cache_dir: str = "./cache"
    max_file_size_mb: int = 5
    exclude_patterns: List[str] = field(default_factory=list)


@dataclass
class PrivacyConfig:
    """Privacy/sanitization configuration."""

    sanitize_api_keys: bool = True
    sanitize_passwords: bool = True
    sanitize_tokens: bool = True
    sanitize_emails: bool = True
    sanitize_secrets: bool = True
    redaction_style: str = "mask"  # hash, mask, or remove


@dataclass
class Config:
    """Main configuration class aggregating all sub-configs."""

    github: GitHubConfig
    llm: LLMConfig
    embedding: EmbeddingConfig
    chroma: ChromaConfig
    app: AppConfig
    privacy: PrivacyConfig


def load_config(env_file: Optional[str] = None) -> Config:
    """Load configuration from environment variables and .env file.

    Args:
        env_file: Optional path to .env file. If None, uses default .env

    Returns:
        Config object with all settings loaded

    Raises:
        ValueError: If required configuration is missing
    """
    # Load .env file (override existing env vars to use .env values)
    if env_file:
        load_dotenv(env_file, override=True)
    else:
        load_dotenv(override=True)

    # GitHub configuration
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        raise ValueError(
            "GITHUB_TOKEN is required. Please set it in your .env file or environment."
            "\nGenerate a token at: https://github.com/settings/tokens"
            "\nRequired scopes: repo (for private repositories)"
        )

    github_config = GitHubConfig(token=github_token)

    # LLM configuration
    openai_api_key = os.getenv("OPENAI_API_KEY")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    llm_config = LLMConfig(
        provider=os.getenv("LLM_PROVIDER", "openai"),
        openai_api_key=openai_api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        anthropic_api_key=anthropic_api_key,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
        anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL"),
    )

    # Embedding configuration
    embedding_config = EmbeddingConfig(
        provider=os.getenv("EMBEDDING_PROVIDER", "sentence-transformers"),
        model=os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        openai_api_key=openai_api_key,
    )

    # ChromaDB configuration
    chroma_config = ChromaConfig(
        db_path=os.getenv("CHROMA_DB_PATH", "./chroma_db"),
        collection_name=os.getenv("CHROMA_COLLECTION_NAME", "github_repo_collection"),
    )

    # Application configuration
    exclude_patterns_str = os.getenv(
        "EXCLUDE_PATTERNS",
        "node_modules/,__pycache__/,*.pyc,.git/,dist/,build/,*.min.js,*.min.css",
    )
    exclude_patterns = [p.strip() for p in exclude_patterns_str.split(",") if p.strip()]

    app_config = AppConfig(
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        cache_dir=os.getenv("CACHE_DIR", "./cache"),
        max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "5")),
        exclude_patterns=exclude_patterns,
    )

    # Privacy configuration
    privacy_config = PrivacyConfig(
        sanitize_api_keys=os.getenv("SANITIZE_API_KEYS", "true").lower() == "true",
        sanitize_passwords=os.getenv("SANITIZE_PASSWORDS", "true").lower() == "true",
        sanitize_tokens=os.getenv("SANITIZE_TOKENS", "true").lower() == "true",
        sanitize_emails=os.getenv("SANITIZE_EMAILS", "true").lower() == "true",
        sanitize_secrets=os.getenv("SANITIZE_SECRETS", "true").lower() == "true",
        redaction_style=os.getenv("REDACTION_STYLE", "mask"),
    )

    return Config(
        github=github_config,
        llm=llm_config,
        embedding=embedding_config,
        chroma=chroma_config,
        app=app_config,
        privacy=privacy_config,
    )


def ensure_directories(config: Config) -> None:
    """Create necessary directories if they don't exist.

    Args:
        config: Configuration object containing directory paths
    """
    Path(config.app.cache_dir).mkdir(parents=True, exist_ok=True)
    Path(config.chroma.db_path).mkdir(parents=True, exist_ok=True)
