# Architecture

ATLAS is a modular monolith. Day 1 is the platform shell. Day 2 adds CRM, document retrieval, and a read-only assistant. Day 3 adds an inquiry agent that pauses for a human approval before it writes CRM records. Day 4 adds n8n-triggered automation, signed webhooks, sandbox email, and a simulated calendar.

## Backend

`apps/api` is a FastAPI application. HTTP routes live under `/api/v1`. Domain code lives in `app/domains/identity`, `app/domains/crm`, `app/domains/knowledge`, `app/domains/assistant`, `app/domains/agents`, `app/domains/approvals`, and `app/domains/automation`. Shared configuration, database sessions, logging, errors, and session cookies live in `app/core`. OpenAI-compatible chat and embedding clients, the SMTP transport, the simulated calendar, and the n8n client live in `app/integrations`. The read-only MCP server is `python -m app.mcp_server`.

n8n is an external workflow runner. It receives lead events and calls ATLAS webhooks. n8n answers that delivery before it calls back, so a restart marks an accepted lead run `needs_attention` until the matching callback completes it. The scheduled follow-up lists organization-scoped leads and opens a pending approval. It does not send email. LangGraph still owns inquiry reasoning and the approval pause. Lead scores, analytics, and local traces are stored for the caller's organization. Success and failure of an external action are stored on the execution record.

Webhook signing secrets are sealed with a key derived from `ATLAS_SECRET_KEY` before they are stored. The create response returns the secret once. Later reads, including the automations snapshot, do not include it. Rotating `ATLAS_SECRET_KEY` makes an existing sealed secret unreadable until the integration key is created again. A value stored before sealing still verifies, and it should be replaced.

The webhook rate limit counts requests in the API process that received them. The default is 30 requests per minute for each integration key. Failed logins are counted the same way: 8 per email and 40 per direct client address inside 15 minutes. Neither counter is shared with another process. The login address is the TCP peer, not `X-Forwarded-For`.

`ATLAS_PUBLIC_DEMO=true` refuses a paid model key, live email, an n8n URL, and the development seed. The seed also refuses `ATLAS_ENVIRONMENT=production` because it resets the example passwords.

## Authorization

A session cookie identifies the user. Organization access is loaded from `memberships` for that user. A path organization id is only a lookup key. Roles are `admin` and `staff` on the membership row. CRM, knowledge, assistant, agent, and approval routes require that membership. Mutations also require the CSRF token. Conversations are limited to the user who created them. The assistant can read CRM records and cannot change them. Approving or rejecting an agent action requires the admin role. The agent graph has no approval tool.

## Data

PostgreSQL is provided by the `pgvector/pgvector` image. Migration `0001` enables `vector` and creates the identity tables. `0002` adds companies, contacts, leads, inquiries, and interactions. `0003` adds documents and chunks, including a `vector(1536)` embedding and a full-text `search_vector`. `0004` adds conversations, messages, and message sources. `0005` adds agent runs, agent events, and approvals. `0006` adds the `needs_attention` approval status. `0007` adds webhook keys, workflow runs, execution intents, email deliveries, and simulated calendar bookings. LangGraph also creates its own checkpoint tables in the same database the first time a run starts.

Document files are stored on disk under `ATLAS_STORAGE_DIR`, or `var/atlas-storage` when that setting is empty. Ingestion runs after the upload response, extracts PDF or text content, chunks it with page numbers when the extractor provides them, and writes embeddings. On startup the API indexes documents still marked pending or processing. Replacement of chunks and the ready status commit together, so a repeated run does not duplicate passages. A failed reindex keeps the previous chunks when they exist.

Retrieval mixes cosine distance and Postgres full-text rank, and it only returns chunks from the caller's organization. `ATLAS_MAX_COSINE_DISTANCE` defaults to 0.55, where distance is 1 - cosine similarity. Vector neighbors farther than that are ignored. A full-text match is still cited, so shared keywords can surface a loosely related passage. A paraphrase with no shared words is cited only when its distance is within the threshold.

## Models

Chat and embeddings use configurable OpenAI-compatible HTTP endpoints (`ATLAS_LLM_*` and `ATLAS_EMBEDDING_*`). The embedding width is fixed at 1536. Responses must contain one vector of that width per input, ordered by the provider's `index`. Token counts are logged only when the provider includes a `usage` object. They are not required and are not stored. An empty API key returns `llm_unconfigured` or `embedding_unconfigured`. The assistant stores citations from retrieved rows. It does not parse citations out of model text. If neither documents nor CRM records match, it stores a refusal and does not call the model.

## Agent

An agent run loads one inquiry for the caller's organization, asks the configured chat model for a JSON classification, and reads company knowledge and CRM through MCP. The MCP server process is bound to that organization. Its tools are `find_contact`, `get_lead`, and `search_company_knowledge`. They do not accept an organization id and they do not write. If the chat key is empty, the run is stored as failed with `llm_unconfigured` and no classification is invented.

The graph then proposes a lead create or update, a customer response, and an appointment. Those proposals are approval rows with a hash of the payload. The run pauses. An admin approves or rejects with the CSRF token. A lead create or update commits the CRM row and the `executed` approval in one transaction. A crash before that commit leaves the approval `approved` and writes nothing. A row already stuck in `executing` from an older process is marked `needs_attention` and is not applied again.

A customer response or appointment is an external action. Approval first stores an execution intent with the payload and a stable idempotency key. One worker claims it. SMTP delivery uses Mailpit or another local server while email mode is `sandbox`. A timeout is `needs_attention` and is not sent again. A refused connection can be tried twice. The calendar adapter in this release is `simulation`: bookings are rows in ATLAS, with no provider event id, and can be cancelled. A rejected or expired approval creates no intent and sends nothing. This is at-least-once delivery with reconciliation. It is not an exactly-once guarantee.

`ATLAS_APPROVAL_TTL_HOURS` defaults to 24. Tool reads retry up to three times. CRM writes are not retried.

## Lead scores, analytics, and diagnostics

Lead scoring trains on a documented synthetic dataset (`lead-synthetic-1`). The label uses a hidden budget band that is not a model feature, and lead status is not a feature. Logistic regression and a shallow decision tree are compared with a referral rule on a held-out fold. The served probability is sigmoid-calibrated on the training fold when that fit succeeds. The artifact lives under `var/atlas-models`, outside the upload directory, and the API does not return its path. A stored prediction is advisory. It does not change the lead, create an approval, or authorize an external action. The score is a synthetic-data demonstration, not a measurement of real conversion. The explanation describes the model that produced the label. A decision tree contributes the splits on the served path. Logistic coefficients are shown only when that model is the one being served. Uploaded documents are not loaded as model artifacts.

Analytics reads the caller's organization. Conversion is won divided by won plus lost. Open leads are excluded, and the rate is absent when that denominator is zero. The lead trend is the last 30 UTC days, including days with zero. There is no revenue metric.

Operation traces are stored locally. Langfuse export runs only when both keys are set, and a Langfuse failure leaves the local row in place with status `unavailable`. Token cost is stored only when the provider reported usage and both prices are configured. Traces omit prompt text, document text, and credential fields. The evaluation suite is a versioned set of deterministic checks. Its results are not live-model accuracy.

## Frontend

`apps/web` is a Next.js App Router client of the API. Authenticated pages call `/api/v1/auth/me`. CRM, knowledge, the assistant, agent runs, approvals, workflows, analytics, and monitoring call the organization routes with the session cookie. Workflows shows automation status, recent runs, sandbox email, and simulated bookings. It does not embed the n8n editor. Analytics and overview counts come from the analytics endpoint. An organization with no leads or inquiries sees an empty state.

## Engineering standards

Cursor rules in `.cursor/rules` record the boundaries above. The review procedure is `.cursor/skills/engineering-review/SKILL.md`. Ruff, mypy, pytest, ESLint, the Next.js build, TypeScript, and gitleaks run in `.github/workflows/ci.yml` and `scripts/check.ps1`. The browser walkthrough is `npm run e2e` in `apps/web`. Deployment, the demo script, and the case study are in `docs/deployment.md`, `docs/demo.md`, and `docs/case-study.md`.

## Diagrams

```mermaid
flowchart LR
  browser[Browser]
  web[Next.js]
  api[FastAPI]
  db[(PostgreSQL)]
  n8n[n8n]
  mail[Sandbox SMTP]
  browser --> web
  browser --> api
  api --> db
  api --> n8n
  api --> mail
```

```mermaid
flowchart TD
  inquiry[Inquiry]
  agent[LangGraph agent]
  mcp[MCP read tools]
  approval[Stored proposal]
  admin[Admin decision]
  crm[CRM write]
  workflow[n8n and sandbox email]
  inquiry --> agent
  agent --> mcp
  agent --> approval
  approval --> admin
  admin --> crm
  crm --> workflow
```
