# ATLAS Phase 1 Engineering Audit and Recovery Plan

> Historical checkpoint. See [the product completion backlog](product-completion-backlog.md) for current status.

Date: 2026-11-25
Checkpoint: `4cdffa824878488cb6fe6e3457ec72b42b9a6132`

## Executive assessment

ATLAS is a substantial local/demo SaaS foundation, not yet a commercially ready hosted product. The repository contains a coherent FastAPI/SQLAlchemy/PostgreSQL backend, a Next.js workspace, organization-scoped authorization, durable knowledge-ingestion records, CRM and assistant workflows, approval-gated actions, workflow-definition persistence, inbox and campaign foundations, billing models, and a broad test suite.

The principal gap is no longer a missing screen. It is operational proof and production hardening: the normal and disposable environments cannot be verified from the current host, background execution remains partly process-local, external communications remain simulated or sandboxed, and several SaaS lifecycle and governance capabilities are incomplete. The reported situation in which the shell appears signed in while Overview and Assistant report authentication errors is not proven to be an application defect by this audit. Source inspection shows a consistent session design; runtime reproduction is blocked because the expected local services are not listening.

No application code, database, commit, or remote branch was changed. This document is the persistent audit artifact.

## 1. Repository baseline

The checkpoint is clean with respect to tracked source changes, but the working tree is not clean. Existing user-owned changes include modified demo screenshots and untracked `.cursor/mcp.json`, `analytics-debug.zip`, multiple `.next-*` build directories, `apps/web/review`, `apps/web/ui-shots`, and `review`. These were preserved and must not be swept into an implementation commit without explicit review.

The repository is a monorepo with:

- `apps/api`: FastAPI application, SQLAlchemy domains, Alembic migrations, workers, integrations, and backend tests.
- `apps/web`: Next.js 16 App Router application, shared workspace shell, screens, API client, unit tests, and Playwright E2E tests.
- `infrastructure`: local and staging Compose files, n8n workflows, Caddy/recovery tooling, and smoke/restore scripts.
- `scripts`: E2E environment configuration and focused verification launchers.
- `docs`: architecture, deployment, acceptance, recovery, feature audit, roadmap, and handoff documents.

There are 45 Alembic migration files through `20261125_0045_marketing_consent.py`. The API package is Python 3.12 with FastAPI, SQLAlchemy, Alembic, PostgreSQL/pgvector, LangGraph, Stripe, Argon2 password hashing, and structlog. The web package uses Next.js 16.4.6, React 19.3, TanStack Query, Playwright, TypeScript, ESLint, and Tailwind.

## 2. Architecture findings

### Strengths

- Clear modular-monolith boundary: API routers delegate to domain services and models rather than putting all business logic in route handlers.
- Organization context is derived from the authenticated session and membership, not accepted as an arbitrary caller-controlled tenant id in the principal business paths.
- Mutating browser requests use a session-bound CSRF token. Sensitive approval and administrative routes use stronger dependency checks.
- Database changes are represented by ordered migrations and the current migration chain is broad enough to cover the present feature set.
- The web application has a single API client and a shared workspace shell. Organization switching clears non-session TanStack Query data to avoid stale tenant data.
- Local integrations fail closed toward sandbox/simulation modes, and production configuration rejects deterministic providers, insecure cookies, and placeholder session secrets.

### Weaknesses and technical debt

- API startup launches automation and knowledge workers in-process. This is suitable for local development but creates duplicate polling, coordination, and shutdown risks with multiple API replicas.
- Login and webhook throttling are process-local. A horizontally scaled deployment has no shared counter or consistent abuse protection.
- Uploads and model artifacts default to local filesystem volumes. This is not elastic or independently recoverable across replicas.
- The assistant stream is request-bound and provider-timeout dependent. There is no durable stream/job handoff or provider fallback/budget policy.
- Integration credential encryption is application-key based. The repository has key-version concepts, but no external KMS/Vault integration or demonstrated rotation/re-encryption operation.
- The frontend has a wide route/screen surface, but a number of screens are operational dashboards over backend state rather than complete product workflows. Workflow persistence exists, but the authoring experience and scheduler semantics still need validation.
- `NEXT_PUBLIC_API_URL` is a build-time frontend value unless `same-origin` is selected. This makes host/port drift easy during local development and requires an image rebuild when an explicit deployment URL changes.
- Existing documentation contains overlapping audits and older classifications. The current migration set has moved several features from “missing” to “foundation/partial”; documentation should be reconciled before implementation work is split.

## 3. Feature inventory

| Subsystem | Current state | Commercial-readiness gap |
|---|---|---|
| Authentication/session | Login, logout, signed session cookie, server session, expiry/revocation, CSRF, forgot/reset password routes | No MFA/SSO, profile/password-change UX, device/session administration, or proven multi-host runtime path |
| Organizations/roles | Memberships, admin/staff roles, org rename/admin/member APIs, invitations and acceptance | Limited role model; no full provisioning/deprovisioning lifecycle, tenant export/deletion, support access, or granular permissions |
| CRM | Companies, contacts, leads, inquiries, interactions, archive/restore, pipeline stages, opportunities/tasks | No import/dedupe/bulk operations, custom fields, unified timeline, scalable search, or mature collaboration model |
| Knowledge | Upload, extraction, chunking, embeddings, pgvector/FTS retrieval, citations, evaluations, durable ingestion records | Runtime worker/restart/concurrency evidence unavailable; quotas, object storage, semantic quality governance, and broader formats remain |
| Assistant | Persistent conversations, grounded answers, citations, streaming, routing/refusal behavior | Provider fallback, spend limits, retention/export/sharing, and action handoff are incomplete |
| Agents/approvals | Agent runs, checkpoints, approval hash/stale protection, admin approve/reject, idempotent internal execution | External side effects are sandbox/simulation; durable distributed execution and reconciliation are incomplete |
| Workflows | Definition CRUD, activate/pause/duplicate, schedules/tasks, fixed webhook integration and run views | Full editor/versioning, scheduler ownership, retries/DLQ, customer-configurable event catalog, and n8n lifecycle are incomplete |
| Inbox/widget | Conversations, drafts, AI drafts, staff takeover, assignment/status, public widget, inbound webhook foundations | Provider OAuth/sync, threading, delivery/receipt semantics, abuse controls, and full channel operations are incomplete |
| Email/calendar/WhatsApp | Encrypted integration metadata, domain verification foundation, sandbox email, simulated calendar, WhatsApp webhook foundation | No proven live delivery, bounce/complaint handling, OAuth inbox, real calendar provider, or production WhatsApp operation |
| Intelligence/analytics | Overview/analytics aggregates, diagnostics, predictions/model endpoints, evaluation records | Scoring is advisory/synthetic; no reporting/export, alerting, SLOs, or centralized retention |
| Campaigns | Segments, campaigns, recipient preview, marketing consent and suppressions | No proven outbound delivery, queueing, unsubscribe/bounce lifecycle, or campaign analytics |
| Billing | Plans, organization billing records, checkout/portal routes, Stripe webhook foundation | Entitlement enforcement, usage metering, invoice/customer lifecycle, reconciliation, and live Stripe verification remain |
| Monitoring/deployment | Health/readiness, traces/heartbeats, Compose, migrations, backup/restore and staging smoke tooling | No production-like CI acceptance, centralized logs/metrics/alerts, SLOs, tested restore evidence, or multi-replica proof |

## 4. Confirmed defects and risks

Severity uses P0 for a release blocker, P1 for a pilot blocker or major workflow gap, and P2 for maturity work.

### P0

1. **Runtime environment is not verifiable from this host.** Ports 3000, 3011, 8000, 8011, and 5434 were not listening during the audit. Docker/PostgreSQL-dependent claims therefore remain source/static evidence, not current runtime evidence.
2. **Distributed execution is not production-safe.** Automation and ingestion workers are launched inside API processes; login/webhook limits are process-local. Multiple replicas can duplicate polling and disagree on limits.
3. **External side effects are not production-complete.** Email is sandbox-default, calendar is simulation-only, and delivery/provider status, bounce, complaint, and unknown-outcome reconciliation are not demonstrated.
4. **Production acceptance is incomplete.** CI and local tests do not establish a production-like deployment with migrations, workers, external boundary gates, backup restore, multi-replica behavior, and browser smoke from a clean environment.

### P1

1. Identity lifecycle is incomplete despite the new invitation and reset foundations: MFA/SSO, profile/password-change UI, session/device management, deprovisioning, and granular permissions are absent.
2. Workflow definitions now exist in the backend, but the product still needs a complete authoring/version/publish/schedule/retry experience and a clear contract for execution ownership.
3. Inbox and communication integrations are foundations rather than complete customer channels. OAuth, inbound synchronization, threading, provider delivery, and status reconciliation remain.
4. Billing records and Stripe endpoints exist, but entitlements and usage enforcement are not proven at every costly operation.
5. Local filesystem storage and application-key-only secret operations are unsuitable as the final production storage/secrets posture.

### P2

1. CRM scale features: import, dedupe, bulk actions, custom fields, export, saved views, and a unified timeline.
2. Reporting, scheduled exports, notification preferences, centralized observability, retention, alerting, and incident operations.
3. Retrieval evaluation beyond heuristic lexical/vector thresholds and model-quality monitoring across tenants.

## 5. Authentication investigation

### Verified request path from source

1. `POST /api/v1/auth/login` normalizes the email, applies an in-process login limit, authenticates against the database, creates a server session, signs the session id with `itsdangerous`, and sets an HttpOnly cookie named `atlas_session` by default.
2. The login response also returns the session-bound CSRF token and organization memberships.
3. `GET /api/v1/auth/me` reads the cookie, validates signature and age, loads the session/user, and returns the same session/tenant context.
4. `apps/web/src/lib/api.ts` sends `credentials: "include"` on all requests and stores the CSRF token after login or session load. Mutations send `X-CSRF-Token`.
5. `WorkspaceShell` reads the React Query session and redirects only a confirmed 401 to `/login`; other failures are surfaced as “Workspace unavailable.” Overview and Assistant use the same workspace session boundary.
6. CORS is configured with credentials and both `http://127.0.0.1:3000` and `http://localhost:3000` by default. E2E setup uses 3011/8011 and explicitly sets both origins.

### Root-cause assessment

No source-level contradiction was found that would selectively authenticate the shell while rejecting Overview and Assistant. The likely classes of failure are environment/runtime contamination: a frontend build using a different `NEXT_PUBLIC_API_URL`, a backend launched on a different host/port or with a different database, stale Next.js build output, an expired/revoked session cookie, or a CORS/cookie site mismatch caused by switching between `localhost` and `127.0.0.1`.

This remains an unresolved runtime defect, not a confirmed code defect. The correct next check must capture browser network requests for login, `/auth/me`, Overview, and Assistant while recording the exact origins, response status, `Set-Cookie` attributes, request Cookie header, and backend request id. It must be run with normal ports 3000/8000 and separately with disposable ports 3011/8011; the two configurations must not share a browser profile or database.

### Next.js navigation warnings

Several client screens use `useSearchParams`. The current route pages for CRM, Assistant, Approvals, Agent Runs, and Monitoring wrap the relevant screens in `Suspense`; invitation acceptance does as well. The pattern is intentional, but a clean production build and browser capture are still required to confirm that no remaining route emits a build-time CSR bailout warning.

## 6. Development infrastructure findings

- Normal development is documented as web 3000 and API 8000; disposable E2E is 3011/8011 with `atlas_e2e` and PostgreSQL host port 5434.
- The current host had no listeners on any of those application/database ports, so no normal or E2E server lifecycle could be verified.
- Compose uses a required API secret, PostgreSQL health dependency, API readiness healthcheck, persistent named volumes, Mailpit, and optional demo web profile. This is appropriate for local work but not proof of production recovery.
- The API `.env` is loaded from the repository root when present, while process environment variables take precedence under Pydantic Settings. E2E scripts override relevant values in-process. This is a sound design only if launchers consistently clear inherited `ATLAS_*`, `NEXT_PUBLIC_*`, and port variables.
- The `uv` static-check invocation was blocked by the sandbox host’s inability to persist its interpreter cache, not by a reported lint/type error. Web unit tests passed: 7/7. Web typecheck and lint completed without reported diagnostics before the combined command’s time limit; they should be rerun independently in the authorized Windows environment.

## 7. Dependency-aware master roadmap

### Phase 1 — Development environment and authentication recovery

**Milestones:** isolate normal/E2E environment files; start and health-check PostgreSQL/API/web; reproduce the auth lifecycle with clean browser profiles; fix only proven host/config/session defects; add a diagnostic acceptance test; reconcile Next.js warnings.

**Dependencies:** Docker/PostgreSQL access and a controlled Windows PowerShell session.

**Done when:** login, refresh, `/auth/me`, Overview, Assistant, org switch, logout, expiry, CSRF, localhost/127.0.0.1, and isolated E2E all pass with captured network evidence; no production/staging data is touched.

### Phase 2 — Core business workflows

**Milestones:** complete identity administration; finish CRM collaboration; make knowledge ingestion and automation distributed/durable; complete approval-to-side-effect state machines; define workflow publish/version/schedule semantics; enforce billing entitlements at resource boundaries.

**Dependencies:** Phase 1 runtime baseline; queue/lease design; object storage and secrets decision; one approved email provider contract.

**Done when:** each critical workflow passes API, browser, tenant-isolation, retry, restart, duplicate, and unknown-outcome tests in a disposable production-like stack.

### Phase 3 — Product experience and interface quality

**Milestones:** close workflow editor gaps; improve empty/loading/error states; complete onboarding, member administration, inbox operations, analytics drill-down, accessibility, responsive behavior, and navigation consistency.

**Dependencies:** stable contracts from Phase 2; no redesign that changes unverified business semantics.

**Done when:** representative admin/staff journeys are usable on desktop/mobile, keyboard accessible, and backed by real API states rather than fixtures.

### Phase 4 — Remaining features and integrations

**Milestones:** OAuth email/calendar, inbound sync/threading, WhatsApp production integration, provider delivery webhooks, campaign delivery/consent lifecycle, reporting/export, and lead-intelligence governance.

**Dependencies:** provider contracts, tenant credential lifecycle, legal/privacy decisions, Phase 2 side-effect safety.

**Done when:** each integration has a sandbox contract test, tenant-isolation test, revocation path, webhook replay protection, observability, and documented operational runbook.

### Phase 5 — Security, performance, reliability, deployment

**Milestones:** external KMS/secrets rotation; shared rate limits; queue workers and dead-letter handling; object storage; centralized logs/metrics/traces; SLOs and alerts; dependency/SCA scans; load/multi-replica testing; backup restore and disaster-recovery rehearsal.

**Dependencies:** stable data model and side-effect contracts.

**Done when:** production-like CI can build, migrate, boot, probe, exercise critical flows, scale replicas, restore a backup, and prove no secrets or tenant data cross boundaries.

### Phase 6 — Product acceptance and release readiness

**Milestones:** freeze scope; execute the acceptance matrix; resolve all P0/P1 findings; prepare support/admin runbooks, privacy/security documentation, rollback plan, migration plan, and release sign-off.

**Done when:** every claim in the release review is backed by a reproducible command, test artifact, or runtime capture, with explicit limitations and owner/date for deferred P2 work.

## 8. Acceptance criteria and verification strategy

The release matrix must cover:

- identity: login, refresh, expiry, logout, reset, invitation, deactivation, CSRF, MFA/SSO policy;
- tenant safety: cross-tenant reads/writes, worker claims, webhook replay, file/object access, exports;
- CRM: complete lifecycle, pagination/search, relationships, archive/restore, concurrency;
- knowledge: upload, extraction, retry, delete race, reindex, worker restart, retrieval/citations;
- assistant/agents: grounding, refusal, stream failure, approval staleness, duplicate execution, provider timeout;
- communications: sandbox fail-closed, live eligibility, provider status, bounce/complaint, unknown outcome;
- workflows/inbox/campaigns: publish/version/schedule, assignment/takeover, consent/suppression, retries;
- billing: checkout/webhook replay, entitlement boundaries, usage accounting;
- operations: readiness, migrations, logs/traces, alerts, backup/restore, clean deployment and rollback.

Static checks are necessary but insufficient. Runtime evidence must include command output, API status/headers, browser traces for the auth issue, database migration state, worker/restart results, and provider sandbox captures. Full-suite repetition should be deferred until the focused environment checks pass.

## 9. Documentation updates and changed files

Added this report: `docs/ATLAS_PHASE1_ENGINEERING_AUDIT.md`.

The existing handoff, functional audit, functional roadmap, architecture, deployment, acceptance, recovery, and staging-readiness documents remain in place. They should be consolidated after Phase 1 verification so that older “missing” classifications are reconciled with migrations `0021`–`0045` and no duplicate roadmap becomes authoritative.

No source code, configuration, migration, screenshot, review artifact, database, commit, or remote branch was modified by this audit.

## 10. Recommended first implementation milestone

Run a controlled Phase 1 environment-recovery slice from authorized Windows PowerShell:

1. verify Docker/PostgreSQL and the 5434 host mapping;
2. clear inherited normal/E2E port and API URL variables;
3. start the disposable `atlas_e2e` database and API on 8011, web on 3011;
4. capture login, `/auth/me`, Overview, and Assistant network requests with a clean browser profile;
5. repeat on normal 3000/8000 using the normal database;
6. compare cookie attributes, request origins, API URL, database identity, and session records;
7. fix only the demonstrated mismatch and add a regression test;
8. rerun focused auth, workspace, Overview, Assistant, and CRM acceptance tests before broader suites.

This milestone has the highest leverage because it turns the central reported blocker from an anecdote into a reproducible, evidence-backed defect or closes it as environment contamination. It also establishes the runtime baseline required for every subsequent workflow and production-readiness claim.
