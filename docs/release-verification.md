# Release verification

The automated command is `.\scripts\verify-release.ps1`. Run it from the repository root on `feature/atlas-product-completion` only after `git status --porcelain` is empty. It refuses a dirty tree, uses disposable databases, writes the production build to `.next-release-check`, and does not restart the API on port 8000 or the web app on port 3000. It does not send a message, create a charge, or create a tag.

The steps below are what that command runs. The counts in [release-checklist.md](release-checklist.md) were accepted on a dirty working tree and are not a substitute for this command.

Leave `ATLAS_LIVE_PROVIDERS` unset. Do not set `ATLAS_E2E_ARTIFACT_DIR` or `ATLAS_FIGMA_SCREENSHOT_DIR` to `docs/demo/screenshots`. Those captures are opt-in and belong to the portfolio rehearsal.

## 1. Confirm the tree and the ignored local state

```powershell
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git check-ignore -v .env apps/web/.env.local infrastructure/staging/.env var
git ls-files -- "*.env" ".env" ".env.*" "**/.env" "**/.env.local"
```

The branch is `feature/atlas-product-completion`. `.env`, the web local env, the staging env, and `var/` must be ignored. `git ls-files` may list `.env.example`. It must not list a filled env file, a database, or an upload.

## 2. Check dependency locks

```powershell
uv lock --check --directory apps/api
npm ci --ignore-scripts --dry-run --prefix apps/web
```

Both commands must exit 0. Do not refresh either lockfile unless a dependency declaration changed.

## 3. Check the migration head

```powershell
uv run --directory apps/api alembic heads
```

The command must print one line: `20261126_0055 (head)`. The API suite then upgrades `atlas_test` and upgrades, downgrades, and re-upgrades `atlas_migration_test`. The browser setup upgrades a new `atlas_e2e_*` database to the same head and drops it afterward.

## 4. Run the API suite

```powershell
$env:ATLAS_LIVE_PROVIDERS = $null
uv run --directory apps/api pytest -q --tb=line
```

Pytest refuses to truncate any database other than `atlas_test`. The live Groq and Ollama test is skipped. Record the passed, failed, and skipped counts from the summary line.

## 5. Run the web checks

Use a dist directory other than `.next` and `.next-e2e-phase2d` so a running dev server is left in place.

```powershell
npm run test:unit --prefix apps/web
npx --prefix apps/web tsc --noEmit
$env:NEXT_DIST_DIR = ".next-release-check"
npx --prefix apps/web next build
Remove-Item Env:NEXT_DIST_DIR
```

`npm run test:unit` covers API base URLs, billing errors, document origins, and the public catalog. TypeScript must pass with no errors. The production build must finish, including its own type check and static page generation.

## 6. Run the browser suite

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $env:LOCALAPPDATA "ms-playwright"
Remove-Item Env:ATLAS_E2E_ARTIFACT_DIR -ErrorAction SilentlyContinue
Remove-Item Env:ATLAS_FIGMA_SCREENSHOT_DIR -ErrorAction SilentlyContinue
Remove-Item Env:ATLAS_E2E_PRODUCTION -ErrorAction SilentlyContinue
npx --prefix apps/web playwright test --reporter=line
```

Playwright starts its own API on port 8011 and web app on port 3011, with sandbox billing and sandbox mail. `e2e/duplicate-key.spec.ts` fails if any workspace route logs a duplicate React key. Record passed, failed, and skipped counts.

## 7. Read the provider record against the diff

```powershell
git log --oneline 52c6b17..HEAD -- apps/api/app/domains/billing apps/api/app/api/v1/billing.py
```

[stripe-test-mode.md](stripe-test-mode.md) records the 2026-11-26 Stripe test-mode checkout, portal, upgrade, downgrade, cancellation, decline, and failed-renewal checks. If the command above prints no billing-domain commit, that record still describes the service and this procedure does not repeat it. Copy changes on the Billing screen do not replace that record. Live email, WhatsApp, and Google Calendar stay on the procedure in [provider-activation.md](provider-activation.md) and are not part of this run.

## What a passing run does not prove

- The process already bound to port 8000 has reloaded its environment. A public deploy starts a new process, runs `alembic upgrade head`, and reads its own secrets.
- Live provider accounts were contacted. Groq, Ollama, SMTP, Resend, WhatsApp, and Google Calendar stay unverified by this procedure.
- Files still being edited for demo access, deployment configuration, or portfolio rehearsal are part of the candidate. Review those separately before publishing them.
