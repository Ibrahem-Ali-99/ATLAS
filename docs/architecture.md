# Architecture

ATLAS is a modular monolith. Day 1 is the platform shell. Day 2 adds CRM, document retrieval, and a read-only assistant. Day 3 adds an inquiry agent that pauses for a human approval before it writes CRM records.

## Backend

`apps/api` is a FastAPI application. HTTP routes live under `/api/v1`. Domain code lives in `app/domains/identity`, `app/domains/crm`, `app/domains/knowledge`, `app/domains/assistant`, `app/domains/agents`, and `app/domains/approvals`. Shared configuration, database sessions, logging, errors, and session cookies live in `app/core`. OpenAI-compatible chat and embedding clients live in `app/integrations`. The read-only MCP server is `python -m app.mcp_server`.

Automation, ML, analytics, and monitoring are still reserved.

## Authorization

A session cookie identifies the user. Organization access is loaded from `memberships` for that user. A path organization id is only a lookup key. Roles are `admin` and `staff` on the membership row. CRM, knowledge, assistant, agent, and approval routes require that membership. Mutations also require the CSRF token. Conversations are limited to the user who created them. The assistant can read CRM records and cannot change them. Approving or rejecting an agent action requires the admin role. The agent graph has no approval tool.

## Data

PostgreSQL is provided by the `pgvector/pgvector` image. Migration `0001` enables `vector` and creates the identity tables. `0002` adds companies, contacts, leads, inquiries, and interactions. `0003` adds documents and chunks, including a `vector(1536)` embedding and a full-text `search_vector`. `0004` adds conversations, messages, and message sources. `0005` adds agent runs, agent events, and approvals. LangGraph also creates its own checkpoint tables in the same database the first time a run starts.

Document files are stored on disk under `ATLAS_STORAGE_DIR`, or `var/atlas-storage` when that setting is empty. Ingestion runs after the upload response, extracts PDF or text content, chunks it with page numbers when the extractor provides them, and writes embeddings. On startup the API indexes documents still marked pending or processing. Replacement of chunks and the ready status commit together, so a repeated run does not duplicate passages. A failed reindex keeps the previous chunks when they exist.

Retrieval mixes cosine distance and Postgres full-text rank, and it only returns chunks from the caller's organization. `ATLAS_MAX_COSINE_DISTANCE` defaults to 0.55, where distance is 1 - cosine similarity. Vector neighbors farther than that are ignored. A full-text match is still cited, so shared keywords can surface a loosely related passage. A paraphrase with no shared words is cited only when its distance is within the threshold.

## Models

Chat and embeddings use configurable OpenAI-compatible HTTP endpoints (`ATLAS_LLM_*` and `ATLAS_EMBEDDING_*`). The embedding width is fixed at 1536. Responses must contain one vector of that width per input, ordered by the provider's `index`. Token counts are logged only when the provider includes a `usage` object. They are not required and are not stored. An empty API key returns `llm_unconfigured` or `embedding_unconfigured`. The assistant stores citations from retrieved rows. It does not parse citations out of model text. If neither documents nor CRM records match, it stores a refusal and does not call the model.

## Agent

An agent run loads one inquiry for the caller's organization, asks the configured chat model for a JSON classification, and reads company knowledge and CRM through MCP. The MCP server process is bound to that organization. Its tools are `find_contact`, `get_lead`, and `search_company_knowledge`. They do not accept an organization id and they do not write. If the chat key is empty, the run is stored as failed with `llm_unconfigured` and no classification is invented.

The graph then proposes a lead create or update, a customer response, and an appointment. Those proposals are approval rows with a hash of the payload. The run pauses. An admin approves or rejects with the CSRF token. Execution writes only the stored payload, and only after the row moves from `approved` to `executing`. A rejected row writes nothing. A changed payload or an expired approval fails closed. A second execution returns `already_executed`. The response and the appointment are CRM interactions. They are not sent as email and they do not create a calendar event.

`ATLAS_APPROVAL_TTL_HOURS` defaults to 24. Tool reads retry up to three times. CRM writes are not retried.

## Frontend

`apps/web` is a Next.js App Router client of the API. Authenticated pages call `/api/v1/auth/me`. CRM, knowledge, the assistant, agent runs, and approvals call the organization routes with the session cookie. Workflows and analytics still render an explicit empty state.

## Engineering standards

Cursor rules in `.cursor/rules` record the boundaries above. The review procedure is `.cursor/skills/engineering-review/SKILL.md`. Ruff, mypy, pytest, ESLint, the Next.js build, TypeScript, and gitleaks run in `.github/workflows/ci.yml` and `scripts/check.ps1`.
