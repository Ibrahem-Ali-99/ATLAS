# ATLAS Functional Roadmap

> Historical checkpoint. See [the product completion backlog](product-completion-backlog.md) for current status.

This roadmap is based on [`ATLAS_FUNCTIONAL_AUDIT.md`](./ATLAS_FUNCTIONAL_AUDIT.md). It prioritizes production safety and complete business workflows over additional UI work.

## Priority definitions

- **P0:** blocks a real customer-facing production pilot.
- **P1:** essential SaaS capability or major workflow gap after P0 foundations.
- **P2:** maturity, scale, collaboration, and reporting improvements.

## P0 — production blockers

### P0.1 Identity lifecycle and tenant administration

**Progress:** The first vertical slice—admin-created, single-use, expiring staff invitations—has been implemented in migration `20261124_0019`. Static migration generation and test collection pass. The audit host could not reach `127.0.0.1:5434` (`10035`), so `scripts/verify-invitations.ps1` is provided for the authorized Windows environment. It is not production-complete because the token is not delivered by a transactional email provider and runtime security tests remain pending.

**Dependencies:** identity/API design, email delivery, token storage, audit events.

**Remaining implementation:** invitation delivery and acceptance UX, password reset/change, admin deprovisioning, session/device administration, MFA or SSO for admins, and granular permission policy.

**Acceptance:** invitation creates exactly one membership in the intended tenant; reset tokens are hashed, single-use, expiring, rate-limited and non-enumerating; deactivation revokes sessions; cross-tenant and replay tests pass; admin MFA/SSO is enforced for the pilot.

### P0.2 Durable distributed jobs and limits

**Dependencies:** queue/worker choice, shared lease/idempotency design, PostgreSQL/Redis, metrics.

**Implement:** transactional durable jobs for ingestion and automation, worker leases/heartbeats/backoff/dead-letter state, crash recovery, shared login/webhook rate limits, and replica-safe startup recovery.

**Acceptance:** two workers cannot duplicate internal effects; restart resumes safe work; uncertain external outcomes never auto-resend; two API/worker replicas pass concurrency and tenant-isolation tests.

**Current slice:** durable PostgreSQL-backed knowledge-ingestion jobs are implemented in migration `20261124_0020`, with transactional upload/reindex enqueueing, lease-based claiming, lease-owner guarded completion, bounded retry state, startup recovery, and a standalone worker command. Runtime concurrency, deletion-race, and restart verification remain pending until an isolated PostgreSQL environment is available.

### P0.3 External side-effect safety gate

**Dependencies:** P0.2, one provider contract, sender-domain evidence, recipient policy, reconciliation UI.

**Implement:** enforce live eligibility at the delivery boundary, not only in `email_delivery_policy.py`; keep sandbox fail-closed; add provider acceptance/bounce/complaint/unknown states and explicit reconciliation.

**Acceptance:** default/test cannot contact external SMTP; live send requires explicit tenant enablement, verified sender, active credential version, owned unchanged recipient snapshot and admin authorization; one separately approved pilot proves provider status handling.

**Current slice:** customer follow-up email proposals flow through immutable approvals and idempotent execution intents. The execution boundary now requires a CRM-owned contact linked to the target lead and enforces the existing live-delivery eligibility policy before any live-mode send. Sandbox remains the default. Runtime provider and PostgreSQL-backed end-to-end verification remain pending.

### P0.4 Managed secrets and key rotation

**Dependencies:** hosting provider, deployment identity, backup design.

**Implement:** KMS/Vault-backed secrets, dual-key/re-encryption or explicit rotation window, backup secret separation and restore drill.

**Acceptance:** no provider/database/session/webhook secret appears in logs, traces, API/browser responses or unencrypted backups; rotation and recovery are automated and evidenced.

### P0.5 Production deployment, backup, observability

**Dependencies:** P0.2/P0.4, hosting and storage.

**Implement:** immutable scanned images, separate migration job, liveness/readiness probes, encrypted scheduled backups, automated isolated restore, centralized logs/metrics/traces, alerts, SLOs, retention and incident runbooks.

**Acceptance:** clean-commit deploy, single migration execution, restore verification, dependency health checks, alert test, and documented RPO/RTO all pass.

### P0.6 Tenant governance

**Dependencies:** tenant admin lifecycle, object storage, audit and plan model.

**Implement:** tenant export/deletion, retention/legal hold, document/storage/vector/checkpoint cleanup, support access approval and audit.

**Acceptance:** export and deletion are complete, organization-scoped, repeatable and audited; support access is time-bound and visible.

## P1 — essential product capabilities

### P1.1 Unified CRM activity and data operations

Add a general customer timeline, imports with dry-run/dedupe/rollback, bulk audited operations, saved views, owner queues, and paginated relationships.

**Acceptance:** controlled CSV import, duplicate resolution, complete company/contact/lead/inquiry/activity timeline, and audited bulk changes work without unbounded loads.

### P1.2 Real workflow product

Persist versioned workflow definitions, triggers, conditions, actions, schedules and enabled state. Build APIs/UI for draft, validate, publish, pause, retry, rollback and run inspection. Keep n8n as an adapter where appropriate, not the only source of truth.

**Acceptance:** admin creates and publishes a workflow, triggers it with a fixture event, observes steps, safely retries/fails it, and rolls back a version.

### P1.3 Production communication integrations

After P0 gates, implement one provider end-to-end: sender verification, approved send, status webhooks, bounce/complaint/suppression, inbound threading, CRM association, OAuth/token refresh where applicable, and communication history.

**Acceptance:** provider revocation/domain invalidation prevents sends; status is accurate; replayed webhooks are idempotent; the customer sees the complete thread.

### P1.4 Assistant-to-agent continuity

Add an explicit conversion from grounded Assistant answer to Agent Run, preserving conversation, evidence, target record, exact diff and approval timeline. Add re-proposal after stale data and per-role tool/action policy.

**Acceptance:** ask about lead → request supported change → review evidence/diff → approve → execute once → verify CRM/activity after reload.

### P1.5 Durable knowledge pipeline

Move ingestion to durable jobs; add object storage, malware scanning, prioritized OCR/DOCX/HTML, content/version dedupe, index versioning, retrieval evaluation and evidence metrics.

**Acceptance:** upload/reindex/delete survives API/worker restarts, stale chunks are not searchable, and index/evidence versions are inspectable.

### P1.6 Usage, plans, and entitlements

Add plan/subscription/entitlement models, storage/token/embedding/run/email limits, usage aggregation, threshold alerts and idempotent billing webhook processing.

**Acceptance:** limits are organization-scoped, enforced before work, actionable at the UI/API, and billing events are replay-safe.

## P2 — maturity and scale

- **P2.1 CRM collaboration:** team ownership, queues, mentions, shared chats, custom fields, advanced search, dedupe suggestions and export.
- **P2.2 Operations:** SLO dashboards, alert routing, on-call integration, trace sampling/retention and load testing.
- **P2.3 Analytics/reporting:** saved reports, funnels/cohorts, date ranges, exports, scheduled reports and freshness labels; govern synthetic scoring separately from customer models.
- **P2.4 Integration ecosystem:** provider adapters, outbound event subscriptions, replay tools, contract tests and provider health dashboards.
- **P2.5 Accessibility/localization:** keyboard/screen reader/contrast audit, localization/time zones, virtualization and mobile approval/attention flows.

## Suggested implementation order

1. Freeze the local/demo release boundary and create a production test profile.
2. Deliver identity lifecycle and tenant governance (P0.1, P0.6).
3. Select hosting/secrets/backup/observability architecture (P0.4, P0.5).
4. Replace embedded jobs and process-local limits (P0.2).
5. Enforce real side-effect gates while sandbox remains default (P0.3).
6. Deliver CRM timeline and Assistant-to-Agent continuity (P1.1, P1.4).
7. Build versioned workflows (P1.2).
8. Add one controlled production communication provider (P1.3).
9. Harden knowledge and add entitlements (P1.5, P1.6).
10. Address collaboration, reporting, scale and accessibility (P2).

## Release gates

**Controlled pilot:** all P0 items pass security, recovery, concurrency, tenant-isolation and browser-to-API acceptance. Live email stays disabled until provider-specific approval.

**General availability:** P1.1–P1.6 have owners, migrations/backups, support procedures, usage enforcement and production-like failure/load tests.
