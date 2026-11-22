# Architecture

ATLAS is a modular monolith. Day 1 is the platform shell. Day 2 adds CRM, document retrieval, and a read-only assistant.

## Backend

`apps/api` is a FastAPI application. HTTP routes live under `/api/v1`. Domain code lives in `app/domains/identity`, `app/domains/crm`, `app/domains/knowledge`, and `app/domains/assistant`. Shared configuration, database sessions, logging, errors, and session cookies live in `app/core`. OpenAI-compatible chat and embedding clients live in `app/integrations`.

Agents, automation, approvals, ML, analytics, and monitoring are still reserved.

## Authorization

A session cookie identifies the user. Organization access is loaded from `memberships` for that user. A path organization id is only a lookup key. Roles are `admin` and `staff` on the membership row. CRM, knowledge, and assistant routes require that membership. Mutations also require the CSRF token. Conversations are limited to the user who created them. The assistant can read CRM records and cannot change them.

## Data

PostgreSQL is provided by the `pgvector/pgvector` image. Migration `0001` enables `vector` and creates the identity tables. `0002` adds companies, contacts, leads, inquiries, and interactions. `0003` adds documents and chunks, including a `vector(1536)` embedding and a full-text `search_vector`. `0004` adds conversations, messages, and message sources.

Document files are stored on disk under `ATLAS_STORAGE_DIR`, or `var/atlas-storage` when that setting is empty. Ingestion runs after the upload response, extracts PDF or text content, chunks it with page numbers when the extractor provides them, and writes embeddings. Retrieval mixes cosine distance and Postgres full-text rank, and it only returns chunks from the caller's organization.

## Models

Chat and embeddings use configurable OpenAI-compatible HTTP endpoints (`ATLAS_LLM_*` and `ATLAS_EMBEDDING_*`). The embedding width is fixed at 1536. An empty API key returns `llm_unconfigured` or `embedding_unconfigured`. The assistant stores citations from retrieved rows. It does not parse citations out of model text. If neither documents nor CRM records match, it stores a refusal and does not call the model.

## Frontend

`apps/web` is a Next.js App Router client of the API. Authenticated pages call `/api/v1/auth/me`. CRM, knowledge, and the assistant call the organization routes with the session cookie. Agent runs, workflows, analytics, and approvals still render an explicit empty state.

## Engineering standards

Cursor rules in `.cursor/rules` record the boundaries above. The review procedure is `.cursor/skills/engineering-review/SKILL.md`. Ruff, mypy, pytest, ESLint, the Next.js build, TypeScript, and gitleaks run in `.github/workflows/ci.yml` and `scripts/check.ps1`.
