# Release verification

The automated command is `.\scripts\verify-release.ps1`. Run it from the repository root on `codex/atlas-phase1-foundation` only after `git status --porcelain` is empty. It refuses a dirty tree, uses disposable databases, writes the production builds to `.next-release-check`, and does not restart the API on port 8000 or the web app on port 3000. It does not send a message, create a charge, or create a tag.

The steps below are what that command runs. The counts in [release-checklist.md](release-checklist.md) were accepted on a dirty working tree and are not a substitute for this command.

Leave `ATLAS_LIVE_PROVIDERS` unset. Do not set `ATLAS_E2E_ARTIFACT_DIR` or `ATLAS_FIGMA_SCREENSHOT_DIR` to `docs/demo/screenshots`. Those captures are opt-in and belong to the portfolio rehearsal.

## 1. Confirm the tree and the ignored local state

```powershell
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git check-ignore -v .env apps/web/.env.local infrastructure/staging/.env var
git ls-files -- "*.env" ".env" ".env.*" "**/.env" "**/.env.local"
```

The branch is `codex/atlas-phase1-foundation`. `.env`, either frontend's local env, the staging env, and `var/` must be ignored. `git ls-files` may list `.env.example`. It must not list a filled env file, a database, or an upload.

## 2. Check dependency locks

```powershell
uv lock --check --directory apps/api
npm ci --ignore-scripts --dry-run --prefix apps/web
npm ci --ignore-scripts --dry-run --prefix apps/web-rebuild
```

Each command must exit 0. Do not refresh a lockfile unless a dependency declaration changed. The deployed client is `apps/web-rebuild`. `apps/web` remains in the check because its unit and browser suites still exercise the API.

## 3. Check the migration head

```powershell
uv run --directory apps/api alembic heads
```

The command must print one line ending in `(head)`. The current head is `20261127_0057`. The API suite then upgrades `atlas_test` and upgrades, downgrades, and re-upgrades `atlas_migration_test`. The browser setup upgrades a new `atlas_e2e_*` database to the same head and drops it afterward.

## 4. Run the API suite

```powershell
$env:ATLAS_LIVE_PROVIDERS = $null
uv run --directory apps/api pytest --tb=line
```

Pytest refuses to truncate any database other than `atlas_test`. The live Groq and Ollama test is skipped. Record the passed, failed, and skipped counts from the summary line.

## 5. Run the web checks

Use a dist directory other than `.next` and `.next-e2e-phase2d` so a running dev server is left in place.

```powershell
npm run test:unit --prefix apps/web
Push-Location apps/web
npx tsc --noEmit
Pop-Location
Push-Location apps/web-rebuild
npx tsc --noEmit
Pop-Location
$env:NEXT_DIST_DIR = ".next-release-check"
Push-Location apps/web
npx next build
Pop-Location
Remove-Item Env:NEXT_DIST_DIR
$env:NEXT_DIST_DIR = ".next-release-check"
Push-Location apps/web-rebuild
npx next build
Pop-Location
Remove-Item Env:NEXT_DIST_DIR
```

`npx --prefix` on this npm does not pass the compiler arguments through, so each command runs inside its package directory. The dist directory stays `.next-release-check`, not the directory a dev server is using.

`npm run test:unit` covers API base URLs, billing errors, document origins, and the public catalog. TypeScript must pass with no errors for both clients. Each production build must finish, including its own type check and static page generation. The release browser suite is `apps/web-rebuild`. The older client in `apps/web` is not the image this deployment builds.

## 6. Run the replacement browser suite

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $env:LOCALAPPDATA "ms-playwright"
Push-Location apps/web-rebuild
npx playwright test --reporter=line
Pop-Location
```

Playwright starts a disposable API on port 8012 and the replacement client on port 3012. The database name is `atlas_e2e_` plus 32 hex characters, seeded with the example identity, and dropped after the run. The API process forces the deterministic providers and leaves public inference unauthorized. The suite signs in, opens every module, creates one company, asks the Assistant, uploads and searches a note, approves a workflow step, exports opportunities, opens Settings, repeats a module at 390px, and launches a visitor who cannot see that company. It does not use ports 3040 or 8014.

## 7. Recorded failures of the retired client

On 27 November 2026 the `apps/web` Playwright suite, against its own disposable API, finished 23 passed, 15 failed, and 3 skipped. That client is not the portfolio image. These tests were not repaired:

- `e2e/automations-integrations-acceptance.spec.ts` — admin can inspect persisted integrations and automation activity. The screen no longer exposes a heading named Language model.
- `e2e/crm-acceptance.spec.ts` — CRM lifecycle persists relationships and recoverable archives. The company control after Create is not the button the test clicks.
- `e2e/crm-follow-up-acceptance.spec.ts` — grounded knowledge, CRM follow-up, approval and sandbox delivery work together.
- `e2e/email-activity.spec.ts` — approved email is delivered once and visible in Email Activity.
- `e2e/figma-acceptance-capture.spec.ts` — capture populated Overview, CRM, and Assistant screens.
- `e2e/harbor-demonstration.spec.ts` — Harbor demonstration supports the main workspace actions. The company control for Harbor & Co. did not appear within the timeout.
- `e2e/inbox-acceptance.spec.ts` — website chat settings persist and staff can reply to a visitor on mobile. The handoff control was not found.
- `e2e/knowledge-acceptance.spec.ts` — Knowledge upload, indexing, search, inspection, and removal. The uploaded row did not become ready for the assertion.
- `e2e/overview-analytics-acceptance.spec.ts` — Overview and Analytics follow CRM changes. The page has no heading named Pipeline overview.
- `e2e/populated-workspace-acceptance.spec.ts` — populated workspace supports connected CRM operations.
- `e2e/settings-integrations.spec.ts` — organization selection switches and persists the workspace. The organization control is not the selector the test uses.
- `e2e/workspace-navigation.spec.ts` — Overview creates an opportunity from the mobile workspace.
- `e2e/workspace.spec.ts` — workspace flow uses the browser and deterministic providers. The Assistant screen has two headings, and the profile control is named Open profile menu.
- `e2e/workspace.spec.ts` — staff can use CRM and another organization cannot see Harbor records.

`e2e/workspace.spec.ts` — narrow viewport opens every page without a missing chunk — failed in that same run because the Inbox count was part of the accessible name. The count is now hidden from the name. That one test was run again and passed. The other fourteen were left as recorded failures of the retired client.

`scripts/verify-release.ps1` runs the replacement suite. It does not run this retired suite.

## 8. Retired browser command

The older suite remains available for inspection. It is not a release gate.

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $env:LOCALAPPDATA "ms-playwright"
Remove-Item Env:ATLAS_E2E_ARTIFACT_DIR -ErrorAction SilentlyContinue
Remove-Item Env:ATLAS_FIGMA_SCREENSHOT_DIR -ErrorAction SilentlyContinue
Remove-Item Env:ATLAS_E2E_PRODUCTION -ErrorAction SilentlyContinue
Push-Location apps/web
npx playwright test --reporter=line
Pop-Location
```

Playwright starts its own API on port 8011 and web app on port 3011, with sandbox billing and sandbox mail. `e2e/duplicate-key.spec.ts` fails if any workspace route logs a duplicate React key. Record passed, failed, and skipped counts.

## 9. Read the provider record against the diff

```powershell
git log --oneline 52c6b17..HEAD -- apps/api/app/domains/billing apps/api/app/api/v1/billing.py
```

[stripe-test-mode.md](stripe-test-mode.md) records the 2026-11-26 Stripe test-mode checkout, portal, upgrade, downgrade, cancellation, decline, and failed-renewal checks. If the command above prints no billing-domain commit, that record still describes the service and this procedure does not repeat it. Copy changes on the Billing screen do not replace that record. Live email, WhatsApp, and Google Calendar stay on the procedure in [provider-activation.md](provider-activation.md) and are not part of this run.

## What a passing run does not prove

- The process already bound to port 8000 has reloaded its environment. A public deploy starts a new process, runs `alembic upgrade head`, and reads its own secrets.
- Live provider accounts were contacted. Groq, Ollama, SMTP, Resend, WhatsApp, and Google Calendar stay unverified by this procedure.
- Files still being edited for demo access, deployment configuration, or portfolio rehearsal are part of the candidate. Review those separately before publishing them.
