# ATLAS Engineering Handoff

Date: 2026-11-25
Branch: `codex/product-completion-phase1`

## Repository state

This checkpoint preserves the ATLAS development work currently present in the working tree. The branch is ahead of the repository's release branches but did not previously have an upstream tracking branch. Existing local changes were not reset or discarded.

## Architecture

- `apps/api`: FastAPI application, SQLAlchemy models/services, Alembic migrations, workers, integrations, and backend tests.
- `apps/web`: Next.js frontend, shared workspace shell, CRM, Assistant, Knowledge, Inbox, workflows, analytics, settings, and Playwright tests.
- `infrastructure`: Docker Compose and staging backup/recovery configuration.
- `scripts`: disposable E2E configuration and verification launchers.

## Preserved implementation areas

The checkpoint includes the accumulated work for:

- Organization invitations, onboarding, password reset, team management, and tenant-scoped authorization.
- Durable knowledge ingestion jobs, worker processing, lease/retry handling, retrieval, and evaluation support.
- AI assistant, approvals, execution intents, sandbox email delivery, and CRM follow-up acceptance coverage.
- Inbox, website chat, handoff, staff takeover, and WhatsApp integration foundations.
- Billing models, plans, usage periods, webhook handling, and entitlement foundations.
- Workflow definitions, scheduling, durable runs, tasks, pipeline stages, opportunities, and CRM integration.
- Analytics aggregation and dashboard filtering/visualization work.
- E2E database/bootstrap scripts, Playwright authentication helpers, CRM lifecycle tests, and populated-workspace fixtures.
- Ollama/Docker host connectivity configuration and operational documentation.

## Confirmed verification

- Static frontend TypeScript and ESLint checks passed for the latest E2E/authentication and analytics changes.
- Ruff and mypy passed for the analytics service and related regression test.
- Backend verification previously reached 66 passing tests in the authorized Windows environment.
- The CRM follow-up workflow previously reached sandbox `EXECUTED` with a persisted sandbox email result.
- Analytics previously returned real metrics (`Companies: 1`, `Leads: 5`, `Open inquiries: 3`) after the SQL grouping defect was corrected.
- The analytics SQL defect was fixed by reusing one labeled `date_trunc` expression across SELECT, GROUP BY, and ORDER BY.

## Unverified or blocked

- Codex execution cannot reliably reach Windows/Docker PostgreSQL at `127.0.0.1:5434`; recent focused Playwright runs stopped during disposable `atlas_e2e` setup with a connection timeout.
- The complete browser acceptance suite has not been claimed as passing from this environment.
- Live external email, WhatsApp, payment, and provider delivery were intentionally not exercised.
- Staging and production data were not modified or deployed by this handoff.

## Current known issues

- Browser tests may legitimately observe a pre-login `GET /api/v1/auth/me` 401 and an optional missing lead prediction 404. The CRM follow-up test now classifies only those exact responses as expected and reports all other failures.
- Runtime verification should be performed from authorized Windows PowerShell with PostgreSQL/Docker access, using the existing disposable E2E scripts.

## Important files

- Backend entrypoint/router: `apps/api/app/main.py`, `apps/api/app/api/v1/router.py`
- Analytics API/service: `apps/api/app/api/v1/intelligence.py`, `apps/api/app/domains/analytics/service.py`
- E2E setup: `apps/api/app/scripts/e2e_database.py`, `apps/api/app/scripts/prepare_populated_e2e.py`, `apps/web/e2e/global-setup.ts`
- Shared browser auth: `apps/web/e2e/auth.ts`
- Focused analytics test: `apps/web/e2e/overview-analytics-acceptance.spec.ts`
- CRM follow-up test: `apps/web/e2e/crm-follow-up-acceptance.spec.ts`
- Verification launchers: `scripts/verify-mvp.ps1`, `scripts/verify-invitations.ps1`, `scripts/e2e-config.ps1`

## Recommended next steps

1. From authorized Windows PowerShell, prepare only disposable `atlas_e2e` and run the focused analytics and CRM follow-up specs.
2. Review the resulting API diagnostics and Playwright traces before running broader scenarios.
3. Reconcile any migration or fixture failures against the committed migration chain through `20261125_0045`.
4. Keep staging/production credentials and databases out of local verification.
5. Continue the authentication/session investigation separately; it is not resolved by this handoff.
