# ATLAS Functional and Production-Readiness Audit

**Audit basis:** repository inspection at `9dac4dd`, including current working-tree files as evidence only. No application or data changes were made for this audit.

## Executive verdict

ATLAS is a coherent local/demo modular monolith with real PostgreSQL persistence, organization-scoped CRM, grounded read-only Assistant behavior, approval-gated agent actions, sandbox email, simulated calendar, n8n webhook integration, document ingestion, pgvector retrieval, and a substantial regression suite.

It is not production-ready as a hosted multi-tenant SaaS. The main blockers are missing identity lifecycle, billing/usage, durable distributed jobs, a real workflow-definition product, OAuth/inbox integrations, production communication delivery, centralized operations, and tenant governance.

## Classification legend

- **Fully implemented and tested:** code exists and has direct regression coverage.
- **Implemented but insufficiently tested:** code exists, but important production/failure paths are unverified.
- **Partially implemented:** a useful subset exists, but the product capability is incomplete or simulated.
- **Missing:** no implementation found.
- **Broken:** current behavior is unsafe, incorrect, or unusable for the stated capability.

## Capability matrix

### Identity, organizations, roles, and isolation

| Capability | Classification | Evidence |
|---|---|---|
| Login/logout/session | Fully implemented and tested | `apps/api/app/api/v1/auth.py`, `app/core/security.py`, `tests/test_auth.py`. Argon2 (`pwdlib`), signed HttpOnly cookie, server session, expiry/revocation. |
| Login throttling | Implemented but insufficiently tested | `domains/identity/login_limit.py`; counters are process-local and not shared between replicas. |
| Organizations/memberships | Partially implemented | `domains/identity/models.py`, `api/v1/organizations.py`. Membership lookup is server-side; no user-facing organization create/rename/archive lifecycle. |
| Roles | Fully implemented and tested for current scope | Only `admin` and `staff` exist; `require_member`/`require_admin` in `domains/identity/dependencies.py`; `tests/test_authorization.py`. Granular permissions are absent. |
| CSRF | Fully implemented and tested | `require_csrf`, `CsrfMember`, `CsrfAdmin`; mutation routes require `X-CSRF-Token`. |
| Tenant isolation | Fully implemented for tested routes | Organization membership is derived from authenticated user and services filter `organization_id`; covered by auth/CRM/knowledge/assistant tests. Non-HTTP worker review remains necessary for every new path. |
| Invitations | Implemented but insufficiently tested | New `domains/identity/invitation_models.py`, `invitation_service.py`, `api/v1/invitations.py`, migration `20261124_0019`, and admin Settings card provide single-use, seven-day, staff invitations. The token is hashed at rest and returned once because outbound email is not enabled. Static migration generation and test collection pass; a direct TCP probe still fails from Codex with Windows error `10035`. Operator-side verification is prepared in `scripts/verify-invitations.ps1`; runtime security tests have not passed here. |
| Password reset/recovery | Missing | No reset-token model, route, email flow, or UI; seed/reset scripts are operator-only. |
| MFA/SSO/profile/session administration | Missing | No MFA, SAML/OIDC, profile/password-change, device/session UI, or admin deprovisioning flow. |

### CRM

| Capability | Classification | Evidence |
|---|---|---|
| Companies/contacts/leads/inquiries CRUD | Fully implemented and tested | `api/v1/crm.py`, `domains/crm/service.py`, `domains/crm/models.py`, `tests/test_crm.py`, `apps/web/e2e/crm-acceptance.spec.ts`. |
| Relationships and validation | Fully implemented and tested | Company/contact references and lead owner/company/contact checks are organization-scoped in `crm/service.py`. |
| Pipeline stages | Fully implemented and tested | `LeadStatus`, lead update route/service, analytics grouping, and browser coverage. |
| Interactions | Partially implemented | Lead-scoped list/create exists; no general activity search, pagination, edit, or unified company/contact timeline. |
| Search/filter/pagination | Fully implemented for current list contract | Query/page bounds in `crm.py/service.py`; UI supports search, archive filter and lead status. Saved views, compound filters, imports and dedupe are absent. |
| Archive/restore | Fully implemented and tested | `20261123_0018`, archive timestamps, `include_archived`, restore routes and E2E tests. Cross-entity history policy is not comprehensive. |
| CRM scale/collaboration | Partially implemented | UI/API broad-load related collections (up to 100); no bulk actions, imports, dedupe, assignment queues, custom fields, export, or detailed audit timeline. |

### Assistant

| Capability | Classification | Evidence |
|---|---|---|
| Persistent conversations/messages | Fully implemented and tested | `domains/assistant/models.py`, `api/v1/assistant.py`, `domains/assistant/service.py`, `tests/test_assistant.py`. |
| CRM/document grounding | Fully implemented and tested for current contract | `knowledge/retrieval.py`, assistant service, MCP `BusinessTools`, retrieval/citation tests. |
| Streaming | Fully implemented and tested for current protocol | `/conversations/{id}/messages/stream`, language client and frontend SSE handling. Still request-bound and provider-timeout dependent. |
| Routing/capability answers/refusal | Fully implemented and tested | `domains/assistant/routing.py`, `tests/test_assistant_routing.py`. |
| Citation quality | Implemented but insufficiently tested | `_cited_context`/attribution preserve cited rows; lexical evidence allows one shared term and documented thresholds are heuristics, not enterprise grounding guarantees (`docs/architecture.md`). |
| Model/provider selection | Partially implemented | `integrations/resolver.py` supports org config and OpenAI-compatible chat/Groq; no quotas, fallback policy, budget enforcement, or provider-health routing. |
| Chat mutations/tool calling | Partially implemented by design | Assistant is read-only; actions require Agent Runs. Safe, but not a unified natural-language-to-action flow. |
| Collaboration/cost controls | Missing/partial | No conversation sharing/retention/export; costs are optional trace metadata and no tenant spend limit exists. |

### Agents and approvals

| Capability | Classification | Evidence |
|---|---|---|
| Inquiry-to-agent orchestration | Fully implemented for supported graph | `domains/agents/service.py`, `workflow.py`, `api/v1/agents.py`, LangGraph checkpoints, `tests/test_agents.py`. |
| Read-only organization-bound tools | Fully implemented and tested | MCP tools do not accept a caller organization id; tools are bound to the run organization. |
| Proposal hash/stale protection | Fully implemented and tested | `domains/approvals/service.py::create_approval/_reject_if_stale`, approval tests. |
| Admin approve/reject | Fully implemented and tested | `api/v1/approvals.py` uses `CsrfAdmin`; staff and tenant rejection tests exist. |
| Internal idempotent CRM execution | Fully implemented and tested | Row locking, state transitions, payload hash and duplicate rejection in `approvals/service.py`. This is not exactly-once external delivery. |
| Email/calendar execution | Partially implemented | `ExecutionIntent`, `ExecutionAttempt`, `EmailMessage`; email is sandbox-only and calendar is simulation-only. |
| Worker/recovery | Implemented but insufficiently tested | `domains/automation/worker.py`, `intents.py`, FastAPI lifespan. Daemon-thread polling is not a durable distributed queue, lease, backoff or dead-letter system. |
| Auditability | Partially implemented | Agent events, approvals, attempts, traces and audit events exist; no unified immutable export/retention/operator timeline. |

### Workflows and automation

| Capability | Classification | Evidence |
|---|---|---|
| Fixed lead-to-n8n trigger/callback | Partially implemented | `domains/automation/workflows.py`, `hooks.py`, `api/v1/hooks.py`; signed HMAC/idempotency contract exists. |
| Callback replay protection | Fully implemented for supported callbacks | HMAC, timestamp, key id, idempotency, body cap and per-process rate limit; `tests/test_automation.py`, `test_n8n_contract.py`. |
| Workflow definitions/editor | Missing | `WorkflowRun` stores execution state only; no definition CRUD, conditions, versioning, graph persistence or authoring API/UI. |
| Scheduling | Partially implemented externally | n8n-imported schedules are documented; ATLAS has no scheduler or persisted schedule model. |
| Workflow UI | Partially implemented | `/automations` and `/workflows` expose snapshots/runs/approvals/email activity; no publish/edit/disable/version lifecycle. |

### Knowledge and RAG

| Capability | Classification | Evidence |
|---|---|---|
| PDF/TXT upload, parsing, chunking | Fully implemented and tested | `api/v1/knowledge.py`, `knowledge/service.py`, `extract.py`, `chunking.py`, `tests/test_knowledge.py`. |
| Embeddings/model compatibility | Fully implemented and tested | `knowledge/vectors.py`, migrations `0010+`, embedding-width tests; 768/1536 columns and model identity are enforced. |
| Retrieval/citations | Implemented but insufficiently tested | pgvector + PostgreSQL FTS fusion and tenant filter in `retrieval.py`; quality thresholds are tuned heuristics. |
| Status/reindex/restart recovery | Implemented but runtime verification pending | `pending/processing/ready/failed`, reindex route, durable job enqueueing, lease recovery, bounded retries and chunk replacement are implemented; isolated PostgreSQL concurrency/restart verification is still pending. |
| Delete/search visibility | Fully implemented and tested | DB cascade plus contained file deletion; retrieval requires ready document in same organization. |
| Ingestion operations | Implemented but insufficiently tested | Migration `20261124_0020`, `IngestionJob`, PostgreSQL `SKIP LOCKED` claiming, lease-owner guarded completion, bounded retry state and standalone `app.scripts.knowledge_worker` replace request-bound execution. Static stale-worker tests pass; PostgreSQL concurrency, restart and deletion-race evidence remain outstanding. |

### Integrations and communication

| Capability | Classification | Evidence |
|---|---|---|
| Org integration config/encryption/versioning | Fully implemented and tested for current types | `IntegrationConfig`, integration service/schemas, encrypted credential helpers, admin/CSRF routes, audit events, integration tests. |
| SMTP config/verification | Partially implemented | Admin APIs/UI store metadata and verify without sending; actual delivery remains global sandbox transport. Org SMTP credentials do not activate live delivery. |
| Email delivery/activity | Partially implemented, sandbox-only | `integrations/email.py`, durable intent/attempt/message records, Mailpit tests and activity API. No production provider, bounce/complaint webhook, inbox, unsubscribe, or real delivery evidence. |
| Resend domains | Partially implemented | `domain_verification.py`, `domain_service.py`, lifecycle endpoints and mocked tests. Direct HTTP provider, single provider, no webhook-driven DNS evidence. |
| OAuth/Gmail/Graph/inbox | Missing | No OAuth state/token/refresh/callback, inbox sync, threading, or inbound CRM communication. |
| Calendar | Partially implemented/simulated | `integrations/calendar.py` stores local bookings; no real provider connection. |
| General webhooks | Partially implemented | n8n-specific signed callbacks only; no customer-configurable outbound subscriptions/event catalog. |

### Analytics, monitoring, SaaS operations

| Capability | Classification | Evidence |
|---|---|---|
| Org analytics | Fully implemented and tested for current aggregates | `domains/analytics/service.py`, `/analytics`, `tests/test_intelligence.py`; stages, conversion, 30-day trend, approvals, automation/email aggregates. |
| Lead scoring | Partially implemented | `domains/ml/*`; advisory model trained on documented synthetic data, not a customer conversion model. |
| Monitoring/diagnostics | Partially implemented | `domains/monitoring/service.py`, traces and diagnostics endpoints; no centralized metrics/logs/alerts/SLOs/retention. |
| Notifications | Missing | No notification model, delivery, preferences, escalation or acknowledgement. |
| Reporting/export | Missing | No reports, CSV/export, scheduled reports or BI integration. |
| Billing/usage/limits | Missing | No plan, subscription, invoice, entitlement, token/storage/seat/run quota or billing webhook. |
| Onboarding | Partially implemented | `setup-screen.pyx` equivalent frontend plus seed/bootstrap scripts; no signup/invite/provisioning lifecycle. |
| Deployment/recovery | Partially implemented | Compose, migrations, health/readiness and backup tooling exist. CI builds but does not fully start/migrate/probe a production-like stack; backup recovery is operational/manual. |
| Horizontal scale | Broken for production scale | Login/webhook limits and worker/recovery are process-local/embedded. Multiple replicas need a shared queue, rate limit store and lease/recovery design. |

### Automated tests

| Area | Classification | Evidence |
|---|---|---|
| Backend | Implemented but insufficiently tested operationally | 180 test declarations in `apps/api/tests`, covering auth, authorization, CRM, assistant, agents, approvals, automation, email, integrations, knowledge, retrieval, migrations and intelligence. Disposable PostgreSQL is required. |
| Browser | Implemented but insufficiently tested operationally | 25 Playwright declarations in `apps/web/e2e`, including CRM, workspace, populated workspace, knowledge, email, integrations and Overview/Analytics. Setup depends on Docker/PostgreSQL and build-time API URL. |
| Production security/load | Partially implemented | CSRF/tenant/redaction/gitleaks tests exist; no penetration test, fuzzing, load, multi-replica, dependency/SCA evidence or production smoke deployment. |

## End-to-end workflow verdicts

1. **CRM lifecycle:** passes for local organization-scoped create/edit/stage/archive/restore and relationships (`api/v1/crm.py`, `crm/service.py`, CRM E2E). Missing imports, dedupe, bulk operations, team ownership and unified activity timeline.
2. **Knowledge to grounded answer:** passes with local/deterministic provider fixtures (`knowledge`, `retrieval`, Assistant E2E). Unsupported formats, durable ingestion, per-tenant quotas and stronger semantic grounding remain.
3. **Inquiry → agent → approval → CRM:** passes for supported lead create/update actions (`agents`, `approvals`, workspace E2E). It is not a unified Assistant action workflow and depends on provider/MCP runtime availability.
4. **Approved email:** passes only through Mailpit sandbox (`automation/intents.py`, `worker.py`, `email.py`, email E2E). No production transport, provider status, bounce/complaint or distributed worker semantics.
5. **Lead → n8n → callback:** passes for the fixed signed contract; it is not a customer-configurable workflow product.
6. **Email configuration/domain:** secure foundation and mocked lifecycle, but live eligibility is not connected to delivery: `live_delivery_eligibility()` is a policy evaluator and is not called by `send_email()`.

## Primary risks

- Process-local rate limits and in-process background worker/recovery are unsafe for horizontal production scale.
- Master-key-only secret handling lacks KMS/Vault and a rotation/re-encryption workflow.
- No invite, reset, MFA/SSO, deprovisioning, tenant export/deletion, retention or support-access controls.
- Sandbox email, simulated calendar and manually provisioned n8n are deliberate demo boundaries.
- Retrieval citation rules are tested heuristics, not complete enterprise grounding guarantees.
- Local filesystem uploads remain non-elastic; durable ingestion now exists but lacks runtime multi-worker evidence.
- Observability is local and lacks alerting, SLOs, retention and incident operations.

## Audit verdict

ATLAS can credibly demonstrate a local organization-scoped AI CRM with human approval and sandbox automation. It should not be marketed or operated as a production multi-tenant SaaS until the P0 roadmap in `ATLAS_FUNCTIONAL_ROADMAP.md` is addressed.
