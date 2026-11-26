# ATLAS UI.1 Interface Reconciliation

Date: 2026-11-25
Reference: `design-reference/ATLAS Workspace Overview.zip`
Authoritative implementation: `apps/web` (Next.js)

## Delivery status

The [product completion backlog](product-completion-backlog.md) is authoritative for open work. This document records interface decisions and historical verification.

### Rendered reference comparison — 2026-11-26

The approved archive was rendered using the installed frontend packages and a local font fallback. The archive and application each produced 38 screenshots across 19 routes and account states, using matched 1440×960 and 390×844 viewports. Chromium reported no application overflow. Reference captures and side-by-side contact sheets are in `var/ui-reference/rendered/screenshots/`. Application captures and viewport measurements are in `var/native-acceptance-fd8e09a9e91445a7bd928c46dee652d6/screenshots/design-comparison/`.

The Billing usage panel was added after this capture pass. Its updated viewport captures are in `var/native-acceptance-9cfdcaee8cbb4b809e776a65aa70cc08/screenshots/`.

| Surface | Reconciled in this pass | Remaining comparison |
| --- | --- | --- |
| Workspace shell and Overview | Navigation follows the archive order and grouping. The top bar has a route breadcrumb and keyboard-accessible search. Overview shows the pipeline and approvals above recent activity and creates a real opportunity from the header. | Compare populated approval cards, activity detail, and filter states against equivalent data. |
| Billing and Settings | Billing has a first-class route, an explicit test or sandbox banner, subscription actions, and real usage and entitlement limits. Settings has a desktop section rail and horizontally scrollable section navigation on mobile. Forms reset when the organization changes. | Review the external test portal, expired billing states, and settings states around member roles and privileges. |
| CRM, Inbox, Assistant, Knowledge, and Campaigns | The shared shell was verified across all modules. Campaigns now renders scheduling, cancellation, and recorded sandbox results using persisted data. | The reference pairs contain different records, including a populated prototype Inbox against an empty application Inbox. Compare matching selected records and failure states before closing parity. |
| Approvals, Agent Runs, Workflows, Analytics, and Monitoring | The shared shell and responsive viewport bounds were verified. The current workflow canvas supports alternate paths and ordered steps. | Compare equivalent operational lists, selected records, and status conditions against the reference. |
| Account pages and Setup | Sign-in, request reset, reset, invitation entry, and workspace setup rendered at both widths. | Separately compare valid and expired token states. The reference organization-creation screen and application organization onboarding have different entry conditions. |

### Production browser checkpoint · 2026-11-26

Current implementation uses the archived interaction patterns and live organization data. The following details have been added since the original route inventory.

| Surface | Implemented detail |
| --- | --- |
| Inbox and website chat | Conversation queue, message thread, responsive customer context, persistent assignment and CRM links, administrator chat settings, and a working website embed. |
| Campaigns | Searchable draft library, saved content review, audience counts using current consent, and organization-level suppression. The CRM contact inspector records consent and withdrawal. |
| Analytics | Customer activity chart with accessible daily counts, lead distribution, and separate opportunity values for each currency. |
| Workflows | Filterable definition library, trigger and action inspector, responsive editor, activation and pause, and persisted task status. |
| Agent Runs, Approvals, Monitoring | Shareable record URLs, tenant-scoped detail requests, closeable inspectors, approval state polling, and searchable historical failures with worker heartbeats. |
| Settings, Integrations, Setup | Administrator configuration and read-only staff views. Organization and assistant setup save in one transaction. Knowledge upload reports real indexing progress and links to Assistant. |
| Authentication | Branded sign-in, invitation, and password recovery. The browser verifies single-use invitations and receives reset links through a disposable SMTP sink. |

The final local run under `var/native-acceptance-9cff1e4c8f8d4585aa74ae7dee5c0e97/` passed all 32 browser tests and restored its populated database and uploads. It captured 14 routes at desktop and mobile widths. Acceptance evidence and remaining production gates are tracked in `docs/product-completion-backlog.md`.

The sections below record the original route inventory and intermediate checkpoints. Consult the engineering handoff for current behavior.

Frontend verification includes ESLint, TypeScript, seven unit tests, a production build, and discovery of 27 Playwright tests. Signed-in browser checks exercised the marketplace, CRM opportunity navigation and keyboard tabs, Campaigns, Setup, Inbox, and Monitoring. The invitation missing-token state rendered with submission disabled. At 390 px, the shell controls and email dialog fit without horizontal overflow. These browser checks did not exercise writes.

| Priority | Milestone | Implementation and evidence | Next executable work |
| --- | --- | --- | --- |
| P0 | Workspace shell, Overview, CRM | Signed-in Overview and CRM loaded real organization records. The opportunity board now has its own CRM tab, and Overview links to it. The Overview lead count is labeled as leads. | CRM tabs and record selection now derive from the URL. Chromium with intercepted API responses verified direct Leads navigation, keyboard focus and tab selection, and URL transitions through Opportunities and Companies at 1440 px and 390 px. ESLint and TypeScript passed. Verify CRM detail forms and task persistence with fresh disposable data. |
| P0 | Authentication and invitations | Shared branded access frame, theme control, form validation, and missing-token state. Local admin sign-in and both sign-in themes were verified in the browser. | Verify invitation acceptance end to end with disposable accounts. |
| P0 | Integrations | Discover and Connected views, provider search, categories, recorded status, and contextual settings dialogs use existing organization-scoped queries and mutations. Browser verified email settings, sandbox disclosure, and zero horizontal overflow at 390 px. | Verify staff permissions and real persisted configuration via disposable Playwright. |
| P0 | Setup, Settings, Billing | Setup retains its existing forms alongside a readiness checklist. Billing reads the current plan and interval, distinguishes sandbox response from Stripe checkout, and reports portal unavailability. | Verify the setup and settings forms at each breakpoint. Stripe portal access requires a test account. Entitlement changes wait for a verified provider event. |
| P0 | Inbox, Assistant, Campaigns | Inbox has tenant-keyed UI state and visible query or mutation errors. Assistant excludes evaluation history from normal conversation navigation without modifying records. Campaigns presents draft and audience workflows with independent operational states. | Complete visual parity for Inbox and Assistant. Verify conversation switching, source drawers, handoff, and campaign forms. |
| P0 | Knowledge, Approvals, Agent Runs, Workflows, Analytics, Monitoring | Monitoring shows operational information first. Service checks remain available under Advanced diagnostics and no longer gate the main view. Other screens retain prior implementation. | Finish reference reconciliation of tables, detail views, dialogs, and operational states. |
| P1 | Flagship journey | Existing acceptance specs cover constituent flows. | Execute and reconcile the inquiry, retrieval, CRM, approval, sandbox delivery, analytics, and audit sequence on disposable data. |
| P2 | Production readiness | Local browser access and production compilation are available. Next.js development tooling reports an instant-navigation validation insight on signed-in routes. | Verify release deployment, tenant isolation, failure recovery, worker behavior, security checks, backup restoration, and performance after functional acceptance. |

### Windows verification follow-up

The local Windows checkout was verified under an exclusive implementation lock. PostgreSQL accepted a loopback TCP connection on port 5434. The existing Playwright bootstrap truncates the fixed `atlas_e2e` database, so mutation acceptance requires a fresh isolated database and a bootstrap that preserves existing databases. That checkpoint did not verify unattended Windows execution. The native runner below now isolates verification in a fresh PostgreSQL instance.

### Disposable verification on Windows

The native runner creates a fresh loopback PostgreSQL instance and uses ephemeral browser and API ports. It requires a PostgreSQL installation with pgvector and the Chromium binaries for the installed Playwright version.

```powershell
Set-Location D:\ATLAS
.\scripts\verify-native-acceptance.ps1 -PostgresBin 'C:/Program Files/PostgreSQL/18/bin' -RestoreCheck
```

Use `-BrowserCache` when the Chromium cache is outside the default profile directory. The runner prints the evidence directory for the API tests, production build, browser suite, and restore check.

## Decision

The reference archive is a visual and interaction reference only. ATLAS keeps the Next.js App Router, production session/authentication flow, API client, React Query data sources, validation, authorization boundaries, and persistence. Reference-only hardcoded records and simulated mutations are not imported into production screens.

The first migration slice establishes semantic visual tokens, light/dark theme persistence, responsive workspace navigation, accessible active states, real organization/user identity, and a reusable shell direction. Screen-level migrations follow after the parity inventory below.

## Reconciliation matrix

| Route / operation | Current implementation and data contract | Reference surface | Status | Migration / acceptance |
|---|---|---|---|---|
| `/login`: sign in | `login-screen.tsx`, `login()` → `/auth/login` | `auth.tsx` | Existing and functional | Preserve cookie/CSRF flow; verify error and loading states. |
| `/invite/accept`: accept invite | `invitation-accept-screen.tsx`, invitation API | `auth.tsx` | Existing and functional | Retain token validation and membership creation; adopt shared auth styling. |
| Workspace session gate | `workspace-shell.tsx`, `/auth/me`, React Query | `App.tsx` shell | Existing and runtime-unverified | Preserve redirect/error distinction; verify refresh and expired-session behavior. |
| Sidebar navigation | `sidebar-nav.tsx`, `navigation.ts` | `App.tsx`, `components.tsx` | Existing and functional | UI.1 shell migrated: semantic colors, icons, active deep links, collapse, mobile drawer. |
| Organization switching | `use-workspace.ts`, membership data | `App.tsx` org switcher | Existing and functional | Keep query invalidation and membership authorization; no fabricated orgs. |
| Theme preference | Previously absent | `index.css`, shell controls | Existing after UI.1 | Persist `atlas.theme`; support light/dark and system initial preference. |
| Account menu / logout | `workspace-shell.tsx`, `sign-out-dialog.tsx`, `/auth/logout` | `App.tsx` profile menu | Existing and functional | Preserve confirmation and CSRF logout; use real identity. |
| `/overview` | `overview-screen.tsx`, analytics/CRM/approvals queries | `App.tsx` overview | Existing and functional | Reconcile cards, pipeline, activity, empty/error states using real metrics only. |
| `/crm` companies | `companies-panel.tsx`, CRM endpoints | `crm.tsx` | Existing and functional | Preserve CRUD, archive/restore, paging and tenant scope. |
| `/crm` contacts | `contacts-panel.tsx`, CRM endpoints | `crm.tsx` | Existing and functional | Preserve relationship validation and accessible dialogs. |
| `/crm` leads/inquiries | `leads-panel.tsx`, `inquiries-panel.tsx` | `crm.tsx` | Existing and functional | Preserve filters, status, interactions, archive/restore and confirmation states. |
| `/crm` opportunities/pipeline | `opportunity-pipeline.tsx`, opportunity/task endpoints | `crm.tsx` | Existing and functional | Reconcile stage controls and permission-aware mutations. |
| `/knowledge` documents | `knowledge-screen.tsx`, upload/search/reindex APIs | `knowledge.tsx` | Existing and functional | Preserve upload validation, job states, retry, delete and retrieval evidence. |
| `/assistant` conversations | `assistant-screen.tsx`, conversation/SSE APIs | `assistant.tsx` | Existing and runtime-unverified | Preserve grounded answers, citations, stream errors and read-only boundary. |
| `/agent-runs` | `agent-runs-screen.tsx`, agent APIs | `agentRuns.tsx` | Existing and functional | Reconcile filters/details without changing execution semantics. |
| `/approvals` | `approvals-screen.tsx`, approve/reject APIs | `approvals.tsx` | Existing and functional | Preserve admin-only actions, stale protection and confirmation UI. |
| `/workflows` | `workflows-screen.tsx`, definitions/runs/tasks APIs | `workflows.tsx` | Partially implemented | Migrate presentation first; retain honest unavailable states for unsupported editor behavior. |
| `/automations` | `automations/page.tsx` snapshot surface | `workflows.tsx` | Existing and functional | Keep route compatibility; avoid duplicate workflow product surfaces. |
| `/inbox` | `inbox-screen.tsx`, conversations/draft/takeover APIs | `inbox.tsx` | Existing and runtime-unverified | Preserve staff takeover, assignment, drafts, resolve and error states. |
| `/campaigns` | `campaigns-screen.tsx`, segments/campaigns/consent APIs | `campaigns.tsx` | Existing and functional | Use real campaign status and consent; no simulated delivery claims. |
| `/analytics` | `analytics-screen.tsx`, analytics API | `analytics.tsx` | Existing and functional | Preserve filters, charts, empty states and data scope. |
| `/monitoring` | `monitoring-screen.tsx`, diagnostics/heartbeats API | `monitoring.tsx` | Existing and runtime-unverified | Preserve operational warnings and data-scope restrictions. |
| `/integrations` | `settings-screen.tsx integrationsOnly`, integration APIs | `integrations.tsx` | Partially implemented | Next slice: Connected/Discover marketplace; only advertise supported provider contracts. |
| `/settings` members | `settings-screen.tsx`, org/invitation APIs | `settings.tsx` | Existing and functional | Reconcile form hierarchy, role restrictions and confirmation states. |
| `/settings` integrations | `settings-screen.tsx`, credential/domain APIs | `settings.tsx` | Existing and functional | Keep sensitive actions contextual; preserve encrypted credential and verification boundaries. |
| `/settings` billing | billing API/client foundations | `billing.tsx` | Partially implemented | Present real provider availability and subscription state; do not invent pricing or entitlements. |
| `/setup` onboarding | `setup-screen.tsx`, onboarding APIs | `settings.tsx` / `App.tsx` | Existing and functional | Preserve setup state and permission checks. |
| Shared dialogs/drawers | Radix UI primitives, `confirm-button`, `dialog`, `sheet` | `components.tsx` | Existing and functional | Unify tokens, focus, escape, labels and mobile sizing. |
| Shared tables/forms/badges | `ui/*`, page-local patterns | `components.tsx` | Partially implemented | Extend existing primitives; no parallel component library. |

## Reference-only interactions not imported

The reference contains hardcoded Harbor & Co./Olivia Martin records, simulated notification counts, local-only search, fake integration success, and local state mutations. These remain excluded. ATLAS will show real data, honest unavailable/permission/provider states, and existing backend errors instead.

## Dependency-aware migration plan

1. **Foundation (completed in UI.1):** semantic tokens, Inter typography, light/dark persistence, accessible focus/contrast baseline, shell spacing, responsive navigation, real identity/org data, icon-based active navigation, and no horizontal overflow in the shell.
2. **Screen framing:** migrate `PageHeader`, cards, tables, badges, empty/error/loading states, then align Overview, CRM, Knowledge, Assistant, Approvals, and Inbox without changing API calls.
3. **Operational surfaces:** reconcile Agent Runs, Workflows, Analytics, Monitoring, Campaigns, and Setup; preserve unavailable provider and permission warnings.
4. **Administration and integrations:** create Connected/Discover integration views from existing metadata, move advanced configuration into contextual settings, and present billing only from real billing responses.
5. **Acceptance:** run typecheck, lint, unit tests, focused Playwright flows, responsive checks, theme persistence, org switching, permission restrictions, and keyboard navigation from a live environment.

## UI.1 acceptance

- The workspace uses actual session identity and organization memberships.
- Sidebar routes are real Next.js links and remain deep-linkable.
- Active navigation works for nested paths and is keyboard accessible.
- Sidebar collapse and mobile navigation do not alter authorization or data loading.
- Light/dark preference persists in local storage and updates semantic tokens without changing API behavior.
- No reference fixture names, fake metrics, fake notifications, or simulated mutation success was introduced.
- Existing API clients, React Query hooks, forms, validation, and permissions remain authoritative.

## Remaining acceptance

Review the latest desktop and mobile captures against the archive, including detail, empty, and error states. The product-completion backlog tracks checks that require deployment infrastructure or provider credentials.
