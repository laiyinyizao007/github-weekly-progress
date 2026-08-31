# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-03-06

### Added
- Initial implementation of GitHub Agent RAG system
- GitHub API client for fetching private repositories (`src/github_client.py`)
- Privacy protection with automatic sensitive information detection and sanitization (`src/sanitizer.py`, `src/patterns.py`)
- Repository analysis with technology stack detection (`src/repo_analyzer.py`)
- Vector knowledge base using ChromaDB (`src/knowledge_base.py`)
- RAG (Retrieval-Augmented Generation) engine for Q&A (`src/rag_engine.py`)
- LLM client supporting OpenAI and Anthropic (`src/llm_client.py`)
- Interactive CLI interface with rich formatting (`src/cli.py`)
- Report generation in Markdown format (`src/report_generator.py`)
- Configuration management via environment variables (`src/config.py`)
- Document chunking for code files (`src/chunker.py`)
- Text embedding with local and cloud options (`src/embedder.py`)
- Comprehensive test suite for sanitizer and GitHub client

### Security
- Implemented privacy-first design with pre-storage sanitization
- Multiple redaction styles: mask, hash, remove
- Detection of API keys, passwords, tokens, secrets, and emails

## Notes

- This is an MVP (Minimum Viable Product) release
- Future versions will include web interface and multi-repository support
