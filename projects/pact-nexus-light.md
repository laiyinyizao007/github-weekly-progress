# 🔗 Pact Nexus Light

**Lightweight contract testing framework**

`TypeScript` · `PostgreSQL` · `Testing`

---

## Overview

Pact Nexus Light is a lightweight contract testing framework that enables consumer-driven contract testing across microservices. It provides a self-hosted broker for storing and verifying pacts, reducing the overhead of adopting contract testing in existing CI pipelines.

## Key Features

- Consumer-driven contract definition and verification
- Self-hosted pact broker with PostgreSQL persistence
- CI/CD integration via CLI and GitHub Actions
- Support for REST and event-driven (message) contracts
- Lightweight deployment — runs on a single server or container

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Core | TypeScript, Node.js |
| Storage | PostgreSQL |
| CLI | Commander.js |
| Infra | Docker, GitHub Actions |
