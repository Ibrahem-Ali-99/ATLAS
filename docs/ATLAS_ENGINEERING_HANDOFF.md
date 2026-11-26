# ATLAS engineering handoff

Checkpoint date: 2026-11-26. The permanent development workspace is `D:\ATLAS` on `feature/atlas-product-completion`. The frozen baseline remains `f0596326a966c9f55be099b6f8f23b113111ded6`, tracking `origin/feature/atlas-product-completion`. Continue from this checkout. Do not open a second worktree or restart the product from the parent revision `4cdffa824878488cb6fe6e3457ec72b42b9a6132`. Environment files, `var/` databases and uploads, and regenerated demo screenshots remain local state on top of the checkpoint.

## Release candidate

Qualification date: 2026-11-26. Portfolio acceptance is `f55c608`, and these suites ran on the tree that includes the Harbor rehearsal commit `b71d0de`. The shared API on port 8000 and the web app on port 3000 were left running. Checks used `atlas_test`, `atlas_migration_test`, and a disposable `atlas_e2e_*` database on API port 8011 and web port 3011. `ATLAS_LIVE_PROVIDERS` was unset. No message was sent and no Stripe charge was created. Repeat the commands in [release verification](release-verification.md).

| Check | Result |
| --- | --- |
| API regression | 284 passed, 1 skipped, 0 failed. The skip is the opt-in live Groq and Ollama test. `atlas_test` is truncated by the suite. `atlas_migration_test` is upgraded, downgraded, and upgraded again. |
| Frontend unit tests | `npm run test:unit` — 12 passed, 0 failed. The script includes the billing error cases that were previously outside it. |
| TypeScript | `npx tsc --noEmit` passed. |
| Production build | `next build` with `NEXT_DIST_DIR=.next-release-check` passed. Next.js 16.4.6 compiled 26 routes. The shared `.next` directory was not replaced. |
| Browser regression | 37 passed, 2 skipped, 0 failed. The skips are the design-capture run, which stays off unless `ATLAS_E2E_ARTIFACT_DIR` is set, and the Resend transport settings test, which stays off unless `ATLAS_E2E_RESEND_TRANSPORT=1`. Do not point the artifact directory at `docs/demo/screenshots`. |
| Migrations | `alembic heads` reports one head, `20261126_0055`. A disposable browser database upgraded from empty to that head. |
| Dependencies | `uv lock --check` in `apps/api` resolved 114 packages. `npm ci --ignore-scripts --dry-run` in `apps/web` reported the lockfile in sync. |
| Secrets and local state | `.env`, `apps/web/.env.local`, `infrastructure/staging/.env`, and `var/` (databases and `var/atlas-storage` uploads) are ignored. The only tracked env file from this check is `.env.example`. |

### Fixes in this qualification

- Workspace setup rendered the organization profile and the knowledge upload as siblings with the same React key, the organization id. The keys are now `profile-` and `knowledge-` plus that id. A browser walk of the workspace routes reports no duplicate-key warning.
- Provider status counted incompatible documents from a second settings lookup. A legacy 1536-width document could be omitted when the status itself was reporting a 768-width model. The count now uses the embedding settings already resolved for that response.
- A customer profile listed the open company, contact, or lead again among its related records. The table and the profile then exposed two controls with the same name. The profile keeps the open record as its subject and lists only the other linked records.

### Provider evidence that this pass did not repeat

The Stripe test-mode record in [stripe-test-mode.md](stripe-test-mode.md) still describes the billing service. No billing domain file has changed since that record. The only later Billing edit is customer-facing copy and alert contrast in `e7918d7`. Checkout still leaves the current plan in place until a signed webhook confirms payment, failed payments still fall back to Free limits, and cancellation still keeps paid access until the period ends. This pass did not open Checkout, the portal, or a test clock.

Live Groq, Ollama, email, WhatsApp, and Google Calendar were not called. The opt-in live provider test stays skipped unless `ATLAS_LIVE_PROVIDERS=yes`. Google Calendar disconnect and revocation remain open in the backlog. WhatsApp customer messaging, live Resend campaigns, and live SMTP stay gated off.

### Still outside this candidate

Interactive demo access, deployment configuration, and portfolio rehearsal are in progress in other working-tree files. This qualification does not certify those files. The process already listening on port 8000 was not reloaded, so it is not the process a public deploy would start. A deploy must load its own environment, run `alembic upgrade head`, and keep live send and live charge flags off until the provider procedure is repeated on that host.

## Architecture and repository

ATLAS is an organization-scoped B2B operations workspace. The web app uses Next.js App Router, React, TypeScript, Tailwind, Radix UI and TanStack Query. The API is a Python 3.12 FastAPI modular monolith using Pydantic, SQLAlchemy, Alembic, PostgreSQL and pgvector. LangGraph coordinates inquiry processing. A read-only MCP integration supplies scoped CRM context. Database-backed knowledge and automation workers run with the API by default. Docker Compose provides local and staging services, Caddy serves staging HTTPS, and Mailpit handles sandbox email.

| Path | Responsibility |
| --- | --- |
| `apps/api/app/api/v1`, `apps/api/app/domains` | HTTP routes, tenant identity, business rules, persistence and workers |
| `apps/api/app/integrations` | External transport and provider adapters |
| `apps/api/alembic/versions`, `apps/api/tests` | Schema history and backend tests |
| `apps/web/src/app`, `apps/web/src/components`, `apps/web/src/lib` | Routes, layouts, components and API clients |
| `apps/web/e2e` | Browser acceptance and disposable workspace fixtures |
| `infrastructure`, `scripts`, `.github/workflows` | Compose, recovery, validation and CI |
| `design-reference/ATLAS Workspace Overview.zip` | Approved design archive |

## Local setup and startup

Use PowerShell, Docker Desktop with Compose, Python 3.12 with `uv`, and Node.js 22 or newer. Open the checkpoint checkout root and run:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
if (!(Test-Path apps/web/.env.local)) { Copy-Item apps/web/.env.example apps/web/.env.local }
# Set ATLAS_SECRET_KEY in .env to a random string of at least 32 characters.
uv sync --locked --directory apps/api
npm ci --prefix apps/web
.\scripts\start-dev.ps1 -SkipSeed
```

Open `http://127.0.0.1:3000`. The launcher starts PostgreSQL on host port 5434, Mailpit, the API at `http://127.0.0.1:8000` and the web app. Mailpit is at `http://127.0.0.1:8025`. Add `-WithN8n` for optional workflow orchestration. The launcher refuses occupied application ports. Use `.\scripts\diagnose-dev.ps1` for redacted diagnostics and `.\scripts\stop-dev.ps1` to stop infrastructure while retaining volumes.

Keep `-SkipSeed` for an existing workspace. To populate a fresh, dedicated demo database, explicitly run `uv run --project apps/api python -m app.scripts.seed` from the repository root. The seed refreshes synthetic records and resets the demo passwords. For an empty operational database, use `app.scripts.bootstrap` with `organization_name`, `organization_slug`, `email`, `full_name` and `password` supplied as JSON on standard input. Follow [deployment.md](deployment.md) for invocation and secret handling.

The launcher applies Alembic migrations. For a manual upgrade, back up the target database and uploads, confirm the configured database URL, then run:

```powershell
Push-Location apps/api
uv run --locked alembic heads
uv run --locked alembic current
uv run --locked alembic upgrade head
uv run --locked alembic current
Pop-Location
```

The single head is `20261126_0055`. Revisions through `20261126_0052` add campaign dispatch and transport pinning, webhook rotation and disconnect, workflow lifecycle, Google OAuth and booking ownership, and staged embedding rebuilds. `20261126_0053` archives inbox conversations, `20261126_0054` stores assistant workspace state, and `20261126_0055` remembers document fingerprints and allows knowledge archival.

## Implemented functionality

| Area | Current behavior |
| --- | --- |
| Identity and onboarding | Argon2 passwords, HttpOnly server-backed sessions, CSRF, tenant roles, invitations, email password reset, workspace profile and persisted setup progress |
| CRM and Inbox | Company, contact, lead and inquiry lifecycles, opportunity stages and tasks, signed inbound email and WhatsApp, website chat, assignment and handoff, conversation-to-CRM intake and approval-based replies |
| Knowledge and Assistant | Durable PDF and text ingestion, hybrid retrieval, citations, conversation history and evaluation, tenant provider configuration and atomic replacement embedding indexes |
| Agents and approvals | Inquiry analysis, scoped CRM retrieval, immutable approval payloads, approval-gated CRM changes, messaging and appointments |
| Workflows | Visual canvas, all/any conditions, two ordered paths, priorities and deadlines, manual runs, human review, activation, pause and run inspection |
| Campaigns | Segments, audience previews, consent and suppression, scheduled and immediate dispatch, cancellation, pinned transport, unsubscribe and signed recipient-level delivery feedback |
| Integrations | Workspace-encrypted credentials, connection tests and disconnect, n8n signed callbacks, Google Calendar OAuth with availability, creation and cancellation |
| Billing and operations | Sandbox and Stripe billing adapters, webhook-confirmed entitlements, usage UI, activity and pipeline analytics, worker monitoring, preflight and recovery tooling |

## Configuration

Use `.env.example`, `apps/web/.env.example` and `infrastructure/staging/.env.example`. [Provider activation](provider-activation.md) documents external setup and acceptance.

| Variables | Purpose |
| --- | --- |
| `ATLAS_ENVIRONMENT`, `ATLAS_PUBLIC_DEMO`, `ATLAS_DATABASE_URL`, `ATLAS_SECRET_KEY`, `ATLAS_CREDENTIAL_ENCRYPTION_KEYS`, `ATLAS_CORS_ORIGINS`, `ATLAS_COOKIE_SECURE` | Runtime, database, session signing, credential encryption and browser security |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, `NEXT_PUBLIC_API_URL`, `ATLAS_PUBLIC_API_URL`, `ATLAS_STORAGE_DIR`, `ATLAS_MODEL_DIR` | Services, origins and persistent storage |
| `ATLAS_LLM_PROVIDER`, `ATLAS_LLM_BASE_URL`, `ATLAS_LLM_API_KEY`, `ATLAS_LLM_MODEL`, `ATLAS_EMBEDDING_PROVIDER`, `ATLAS_EMBEDDING_BASE_URL`, `ATLAS_EMBEDDING_API_KEY`, `ATLAS_EMBEDDING_MODEL`, `ATLAS_EMBEDDING_DIMENSIONS` | Model provider defaults |
| `ATLAS_EMAIL_MODE`, `ATLAS_EMAIL_LIVE_ENABLED`, `ATLAS_SMTP_HOST`, `ATLAS_SMTP_PORT`, `ATLAS_SMTP_FROM`, `ATLAS_SMTP_LIVE_HOSTS`, `ATLAS_INBOX_WEBHOOK_SECRET` | SMTP delivery mode, live relay allowlist and signed inbound gateway |
| `ATLAS_CAMPAIGN_PUBLIC_URL`, `ATLAS_CAMPAIGN_LINK_SECRET`, `ATLAS_CAMPAIGN_LIVE_ENABLED`, `ATLAS_RESEND_CAMPAIGN_WEBHOOK_SECRET` | Campaign preferences and signed delivery feedback |
| `ATLAS_N8N_LEAD_WEBHOOK_URL`, `ATLAS_HOOK_KEY_ID`, `ATLAS_HOOK_SECRET`, `N8N_ENCRYPTION_KEY` | n8n dispatch, callback authentication and n8n credential storage |
| `ATLAS_WHATSAPP_WEBHOOK_VERIFY_TOKEN`, `ATLAS_WHATSAPP_WEBHOOK_APP_SECRET`, `ATLAS_WHATSAPP_LIVE_ENABLED` | Meta callback, signature verification and outbound gate |
| `ATLAS_GOOGLE_CALENDAR_CLIENT_ID`, `ATLAS_GOOGLE_CALENDAR_CLIENT_SECRET`, `ATLAS_GOOGLE_CALENDAR_REDIRECT_URI`, `ATLAS_GOOGLE_CALENDAR_WEB_ORIGIN` | Google OAuth client, callback and browser destination |
| `ATLAS_BILLING_PROVIDER`, `ATLAS_STRIPE_SECRET_KEY`, `ATLAS_STRIPE_WEBHOOK_SECRET`, `ATLAS_STRIPE_PRICE_IDS`, `ATLAS_BILLING_PUBLIC_URL` | Billing, Stripe webhook and return configuration |
| `ATLAS_LANGFUSE_PUBLIC_KEY`, `ATLAS_LANGFUSE_SECRET_KEY`, `ATLAS_LANGFUSE_HOST` | Optional tracing export |

## Verification and release prerequisites

See the checkpoint verification record below for checks against the frozen source. The [backlog](product-completion-backlog.md) is authoritative for remaining requirements and labels older acceptance as historical. Local logs under `var/` remain outside Git. Scripts and fixtures are versioned.

Production requires operator-managed secrets and a credential keyring, TLS and a single browser origin, persistent PostgreSQL/pgvector and uploads, worker monitoring, verified off-host backup and restore, and dependency and image advisory checks. Docker daemon access and GitHub DNS were unavailable during the checkpoint. Local Compose rendering verifies interpolation and syntax. Webhook and login throttling currently operate per API process. Multiple replicas require separate qualification.

Start with the matched-state CRM and Inbox acceptance using a disposable workspace. Then qualify approved provider test accounts using the activation procedure. Google Calendar creates and cancels ATLAS events on the connected primary calendar. Direct Google edits are not imported.

The approved archive is tracked byte-for-byte at `design-reference/ATLAS Workspace Overview.zip`. Its SHA-256 is `D3E97C7AB3A659694472091FE3E251121B9402AD610F30E6CC3EA8E9632E5760`. Extract it into an ignored directory. [Interface reconciliation](UI1_INTERFACE_RECONCILIATION.md) records the reference and visual review history.

## Frozen-source verification

- Frontend ESLint, TypeScript and unit tests passed. The npm manifest and lockfile passed an offline clean-install dry run.
- Backend Ruff lint and format checks and mypy passed across the configured project. The Python lock passed `uv lock --check --offline`.
- Alembic reported a single head at `20261126_0052`. A disposable PostgreSQL 18 run passed eight migration, production startup, Google Calendar, embedding rebuild and campaign tests. See `var/native-acceptance-0ea817de9d0f467d81c5226fa9e42e41/api.log`.
- Both Compose configurations rendered with their example files. The Windows native command wrapper regression passed.
- The checkpoint tree and archive entries passed a redacted local scan for known token formats, high-entropy credential assignments, and exact matches to locally configured secrets. Gitleaks and independent advisory verification remain pending because the scanner binary was unavailable, registry DNS failed, and Docker daemon access was denied. The repository retains its connected scan job.
- Browser production builds and acceptance runs are historical evidence for the corresponding modules. The latest focused browser run recorded four Inbox and Workflows passes, and the earlier full baseline recorded 213 API passes, one opt-in provider skip, and 32 browser passes. Neither run is a full suite against the final commit. Live provider accounts and staging HTTPS were outside frozen-source verification.

The checkpoint excludes regenerated demo screenshots, local reviews, runtime artifacts and connector configuration. Baseline tracked demo images remain in Git. This workspace keeps the regenerated screenshots, environment files, and `var/` databases and uploads as local state.
