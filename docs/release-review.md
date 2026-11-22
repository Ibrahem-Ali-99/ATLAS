# ATLAS V2 release review

Reviewed on 23 November 2026. This is a code and release review of draft pull request [#1](https://github.com/Ibrahem-Ali-99/ATLAS/pull/1). It is not a production deployment approval, and the pull request was not merged.

## Reviewed range

| Item | Value |
|---|---|
| Base | `origin/main` `985c9a5ccd366afdff25b0ccbf820cdc95185583` |
| Head reviewed | `release/atlas-v2-candidate` `9d26b021b3dfe9c7caa643f030a9547dc2847a4d` |
| Diff | 113 files, +6269 / −1069, 24 commits |
| Merge state at review | `MERGEABLE`, `CLEAN`, draft |
| `main` protection | Not configured. GitHub returned "Branch not protected". There is no required review and no required status check. |

The working tree at review time had only untracked `.cursor/mcp.json` and `apps/web/ui-shots/`. Neither is in the pull request. Playwright rewrote `apps/web/tsconfig.json` and `docs/demo/screenshots/` during this review; those files were restored before this document was added. No `.env`, database dump, or credential file is in the diff.

The five CI jobs on the reviewed head passed in pull-request run [45078896796](https://github.com/Ibrahem-Ali-99/ATLAS/actions/runs/45078896796) and push run [45078892125](https://github.com/Ibrahem-Ali-99/ATLAS/actions/runs/45078892125): `api`, `web`, `browser`, `containers`, `secrets`.

Earlier runs [45078505440](https://github.com/Ibrahem-Ali-99/ATLAS/actions/runs/45078505440) and [45078460873](https://github.com/Ibrahem-Ali-99/ATLAS/actions/runs/45078460873) failed on `99fb29a`. `api` pytest and `browser` failed because the MCP startup probe did not receive database settings. Commit `9d26b02` fixed that. Those older runs are not the current head.

There is no separate migration job and no container smoke job. Migration coverage is inside `api` pytest. `containers` builds the API and web images and does not start them.

## Recommendation

**APPROVE FOR MERGE** by a human, after the draft is marked ready.

No Critical or Major defect was verified in the reviewed head. The remaining items are limited usability gaps, an accepted subprocess trust boundary, and product limits that are already stated in `docs/product-acceptance.md`. Merging does not make email, calendar booking, or citation checks production-complete.

## Security

Session cookies are HttpOnly. Production requires `Secure`. Logout revokes the server session. State-changing routes use the session CSRF token. Login and signed webhooks are the exceptions. A client organization id is a membership lookup. A non-member receives 404. Staff can create CRM records and start agent runs. Approve, reject, execute, webhook-key creation, and booking cancellation require an admin.

Webhook authentication uses HMAC and a constant-time compare. A timestamp outside the configured skew is rejected. A repeated idempotency key returns the stored response from `webhook_events`. A body organization id that does not match the key is rejected. The per-key rate limit is an in-process counter (`apps/api/app/domains/automation/hooks.py` around the `_limited` function). A second API process does not share it. Replay protection still holds.

Approval execution locks the row in the caller's organization. Pending execution returns 409 `invalid_transition`. A second execute returns 409 `already_executed`. Expired approvals are rejected. CRM writes use the approval's organization id.

Sandbox email refuses an SMTP host other than `127.0.0.1`, `localhost`, `mailpit`, or `::1` (`apps/api/app/integrations/email.py`). Live email also requires `email_live_enabled`. Calendar booking writes a local simulated row.

Logs for MCP status record the executable, category, exit code, and exception type. They do not record stderr or the environment. Tool errors that contain a database URL, `gsk_`, or an API-key marker are replaced with a short public message. gitleaks scanned 76 commits in this review and reported no leaks. The `gsk_` strings in the live scripts are checks that a model answer does not contain a key.

### MCP child environment (`9d26b02`)

`mcp_process_env` in `apps/api/app/integrations/mcp_runtime.py` is the environment for both the startup probe and `python -m app.mcp_server`.

Passed when present on the parent or loaded from settings:

- `ATLAS_DATABASE_URL`
- `ATLAS_SECRET_KEY`
- `ATLAS_ENVIRONMENT`
- `ATLAS_EMBEDDING_PROVIDER`
- `ATLAS_LLM_PROVIDER`
- `ATLAS_LLM_BASE_URL`
- `ATLAS_LLM_MODEL`
- `ATLAS_PUBLIC_DEMO`
- `ATLAS_EMBEDDING_API_KEY`
- `ATLAS_EMBEDDING_BASE_URL`
- `ATLAS_EMBEDDING_MODEL`
- `ATLAS_EMBEDDING_DIMENSIONS`
- `ATLAS_MAX_COSINE_DISTANCE`
- `ATLAS_LOG_LEVEL` (forced to `WARNING`)
- `ATLAS_MCP_ORGANIZATION_ID` on a real tool process
- `VIRTUAL_ENV` when the interpreter is inside a virtualenv
- A short inherited OS list (`PATH`, `HOME`, and the Windows profile variables). No `ATLAS_*` value is inherited by accident.

`ATLAS_LLM_API_KEY` is not passed. `tests/test_mcp.py` asserts that.

The database URL and embedding key are required for `search_company_knowledge`. `ATLAS_SECRET_KEY` is passed because importing the application constructs `Settings`, which requires it. The tools do not sign cookies. The live child already received this set before `9d26b02`. That commit made the startup probe use the same set, which is what CI needs when no `.env` file exists. Removing the secret from the child would need a separate settings model. That is an architectural change and was not made here.

The child is first-party code started by the API. A compromised child can use the database URL and the session secret. That is the residual trust boundary of this process model, not a new leak into Git, logs, or the UI.

The organization id comes from `ATLAS_MCP_ORGANIZATION_ID` in `apps/api/app/mcp_server.py`. Tool functions query with that id. The model cannot supply another organization.

## Database and provenance

The Alembic chain is linear: `20261122_0001` through `20261122_0010` on `origin/main`, then `20261122_0011`. `0011` creates the `record_origin` enum and adds a non-null `origin` column with server default `unknown` on the thirteen business tables. It does not `UPDATE` rows by name, organization, or date. Downgrade drops the columns, then the enum.

`tests/test_migrations.py::test_origin_migration_leaves_existing_rows_unknown` upgrades a disposable `atlas_migration_test` database to `0010`, inserts a lead with no origin column, upgrades to head, and asserts `unknown`. It then downgrades that disposable database. The development database was not reset. The full pytest run in this review included that test: 129 passed, 1 skipped.

Origin is not rewritten by an approved `update_lead`, by `complete_lead_callback` (workflow status only), or by document reindex. New user creates default to `operational` when the client omits origin. Seed inserts new demo rows and leaves existing rows unchanged. Analytics, agent-run lists, workflow lists, and failed-run diagnostics default to `operational`. Historical `unknown` rows stay readable through the Legacy and All scopes, and through CRM lists, which are organization-scoped rather than origin-scoped.

PostgreSQL 11+ applies a constant column default without rewriting every row. Each `ADD COLUMN` still takes a short exclusive lock. That is acceptable for this schema size. It is not a data-loss path.

## AI execution

The API starts one LangGraph run for an inquiry in the caller's organization. MCP tools are read-only: `find_contact`, `get_lead`, and `search_company_knowledge`. Proposals do not write CRM. An admin must approve and execute. The interpreter is the project virtualenv, or `ATLAS_MCP_PYTHON` when that file exists. Startup refuses to serve when that interpreter cannot import the MCP package, except when `ATLAS_ENVIRONMENT=test`.

Grounded assistant turns buffer the model draft, attribute it, and emit one token equal to the stored message. The client ignores tokens while the phase is `verifying`. A turn with no retrieved rows still streams tokens. If the answer states a number, code, or email that no passage contains, the stored text becomes "I could not confirm that against the company records." and no source is saved.

Citation matching is text overlap, not semantic verification. Concrete false-positive cases in `attribute_answer`:

- A sentence with no number, code, or email is cited when it shares one content word of length 4 or more with a passage, after removing the question words and a small stop list. Two passages that each share a different generic word can both be cited.
- A sentence that contains a number is cited for every passage that contains that number, even when the rest of the sentence is about something else.

An unsupported hard fact replaces the whole stored answer. A sentence with no hard fact can still attach a weak citation. The ten-case eval scores the function on a fixed passage set. It does not prove live model answers.

## Frontend

Navigation redirects an anonymous session to login. Mutations send `X-CSRF-Token`. Approve, reject, execute, and booking cancellation are admin-only in the UI, matching the API. Workflows state that create, edit, and retry are unavailable. Settings is labeled read-only. Scope controls on Overview metrics, Analytics, Monitoring diagnostics, Agent runs, and Workflows pass `operational`, `demo`, `evaluation`, `unknown`, or `all`.

Verified usability gaps, none of which bypass the API:

- Overview "Pending approvals" uses the scoped analytics count. The priority inbox calls `listApprovals` with no scope (`overview-screen.tsx`). The Approvals page is also unscoped. With demo or legacy proposals present, the number and the list can disagree. The unscoped queue is intentional so a demo proposal stays decidable. The two presentations are not labeled as different sets.
- Approvals shows "Resume agent run" for every status other than `pending` (`approvals-screen.tsx`). The API resumes only `awaiting_approval` or `running` (`agents/service.py`). Agent Runs hides the button otherwise. A finished approval returns 409.
- Analytics pipeline bars use a minimum width of 4% (`analytics-screen.tsx`), so a zero count still draws a sliver.
- A later failed knowledge upload can leave the previous "Uploaded" line on screen (`knowledge-screen.tsx`).

## Deployment

Another developer can reproduce the app from the README: copy `.env.example`, set `ATLAS_SECRET_KEY`, `docker compose up` Postgres, `uv sync`, `alembic upgrade head`, and `npm ci` plus the Next.js app. Lockfiles are `uv.lock` and `apps/web/package-lock.json`. Example and CI Postgres stay on port 5432. A local port override belongs in an uncommitted `.env`.

The API image runs `alembic upgrade head` and then one uvicorn process. Training, ingestion resume, and recovery run in that process. A second copy would recover the same rows twice. The image has no `HEALTHCHECK` instruction. Compose healthchecks cover Postgres and Mailpit, not the API or web containers. CI `containers` success means the images built. It does not mean a container was started, migrated, or probed.

n8n is an external Compose service. Email defaults to sandbox. Calendar defaults to simulation. Empty chat and embedding keys return 503 rather than a fabricated answer.

`main` has no branch protection. A merge of this pull request is a manual GitHub action. Marking the draft ready does not deploy.

## Findings

### Critical

None.

### Major

None.

### Minor

- `apps/web/src/components/screens/overview-screen.tsx` — scoped pending count beside an unscoped inbox.
- `apps/web/src/components/approvals/approvals-screen.tsx` — Resume is offered after the run can no longer resume. The API rejects it.
- `apps/web/src/components/analytics/analytics-screen.tsx` — zero counts still render a 4% bar.
- `apps/web/src/components/knowledge/knowledge-screen.tsx` — a failed retry can sit next to an older success message.
- `apps/api/app/domains/automation/hooks.py` — webhook rate limit is per process.
- `apps/api/app/domains/crm/schemas.py` and the knowledge upload form — a member can set `origin` on create. Updates cannot change it. This affects scoped reports inside the member's own organization.
- GitHub `main` is unprotected.

### Enhancement

- Give the MCP child a settings object that does not include the session secret, once the import path no longer requires `ATLAS_SECRET_KEY`.
- Scope operation traces by joining `agent_runs.origin`, and store `agent_run_id` on MCP tool traces.
- Label the approval inbox as all origins, or filter it, as an explicit product choice.
- Add API and web container smoke checks if image build is not enough for a later release.

## Fixed in this review

No application code was changed. No Critical or Major defect met the bar for a narrow fix. Stripping `ATLAS_SECRET_KEY` from the MCP child would break startup. Scoping the approval inbox would hide proposals the product currently keeps visible.

## Checks run in this review

| Check | Result |
|---|---|
| `uv run ruff check app tests` | passed |
| `uv run ruff format --check app tests` | passed, 140 files |
| `uv run mypy` | passed, 108 files |
| `uv run pytest` | 129 passed, 1 skipped, 38.86s, including migration tests on `atlas_migration_test` |
| `npm run lint` | passed |
| `npm run build` | passed, Next.js 16.4.6, 15 static routes |
| `npm run typecheck` | passed |
| `npx playwright test` | 4 passed |
| gitleaks v8.30.1 via Docker | 76 commits, no leaks |
| GitHub Actions on `9d26b021b3dfe9c7caa643f030a9547dc2847a4d` | `api`, `web`, `browser`, `containers`, `secrets` success |

The skipped test is `tests/test_live_providers.py`. It runs only when `ATLAS_LIVE_PROVIDERS=yes`, so CI does not call Groq or Ollama. The earlier live Groq and n8n checks remain the evidence in `docs/product-acceptance.md`. They were not repeated in this review.

Container runtime, a second API replica, and live SMTP were not executed.

## Outstanding limits

- Email delivery is sandbox-only unless live mode and the live-send flag are both set.
- Calendar booking is simulated.
- Workflows cannot be created, edited, or retried in the UI.
- Provider settings are read-only.
- Citation attribution is heuristic overlap, not semantic proof.
- Rows from before `20261122_0011` remain `unknown`.
- Some monitoring traces are not origin-scoped.
- MCP tool traces may omit `agent_run_id`.
- Delivery is at-least-once with reconciliation, not exactly-once.
- The MCP child holds the database URL, the session secret, and the embedding key. It does not hold the chat key.
