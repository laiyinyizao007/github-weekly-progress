# 🤖 GitHub RAG Agent

**RAG agent for private repo Q&A with automatic sensitive-data sanitization**

`Python` · `RAG` · `LLM`

---

## Overview

GitHub RAG Agent is a retrieval-augmented generation system that lets you query your private GitHub repositories in natural language. It automatically sanitizes sensitive data (keys, tokens, internal hostnames) before indexing, so you can share the agent with teammates without exposing secrets.

## Key Features

- Natural language Q&A over private GitHub repositories
- Automatic sensitive-data detection and redaction before indexing
- Incremental index updates on new commits
- Claude-powered retrieval and answer synthesis
- CLI and web interface

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Core | Python |
| Embeddings | OpenAI / local model |
| Vector store | ChromaDB |
| LLM | Claude API |
| GitHub | PyGithub, gh CLI |
