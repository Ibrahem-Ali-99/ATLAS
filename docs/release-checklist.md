# Release checklist

The public portfolio gate is [portfolio-release-checklist.md](portfolio-release-checklist.md). This file remains the product regression record.

Prepared 26 November 2026 on `feature/atlas-product-completion`. The accepted regression predates the Harbor demo commits `3bc9684`, `e77d5a1`, and `bb7d10a`. This checklist does not create a tag. Deployment configuration may still be uncommitted and is not certified here.

## Commits on the branch

These completed engineering commits are ancestors of `44631e1`:

| Commit | Work |
| --- | --- |
| `f059632` | Product checkpoint and engineering handoff |
| `d5f16c1`, `9422677`, `52c6b17` | Stripe test-mode entitlements, catalog, and price reuse |
| `8554e4f`, `8d5ee4d` | Workspace model connections and Calendar OAuth |
| `9234a55`, `f7b3b7a`, `13e7cba` | Restricted WhatsApp test reply and Resend administrator test |
| `3473ef8`, `ecd1330` | Inbox archive and assistant proposals |
| `0f311bd`, `1a296aa` | Customer profile and period comparisons |
| `e7918d7` | Workspace typography and customer-facing copy |
| `e22a9df` | Knowledge replacement and workflow preview |
| `0a1343c` | Production Compose and backup restore |
| `eb635e6`, `eaa7aba`, `b71d0de` | Harbor walkthrough, public site, and rehearsal |
| `f55c608` | Portfolio journey acceptance |
| `44631e1` | Release qualification fixes |
| `3bc9684`, `e77d5a1`, `bb7d10a` | Short-lived Harbor demo and rehearsal corrections |

The branch tracks `origin/feature/atlas-product-completion` and is ahead of that remote. Do not push or tag from this preparation. The three Harbor commits above are present. They are not covered by the regression counts below.

## Accepted regression

These counts are accepted for the working tree that included `b71d0de` and the qualification fixes. The shared API on port 8000 and the web app on port 3000 stayed up. No message was sent and no charge was created.

| Check | Result |
| --- | --- |
| API | 284 passed, 1 skipped, 0 failed |
| Browser | 37 passed, 2 skipped, 0 failed |
| Frontend unit tests | 12 passed, 0 failed |
| TypeScript | passed |
| Production build | passed, Next.js 16.4.6, 26 routes, directory `.next-release-check` |
| Alembic | one head, `20261126_0055` |
| Locks | `uv lock --check` resolved 114 packages; `npm ci --ignore-scripts --dry-run` matched |

The API skip is the opt-in live Groq and Ollama test. The browser skips are design capture and the Resend transport settings test. The run used `atlas_test`, `atlas_migration_test`, and a disposable `atlas_e2e_*` database. It also loaded uncommitted demo and deployment files, so it is not a clean checkout of `44631e1`.

## Clean checkout

Stay in `D:\ATLAS`. Do not create a second worktree. Do not stash, reset, or clean another session's files to force an empty status.

1. Wait until `git status --porcelain` prints nothing.
2. Confirm `feature/atlas-product-completion` and record `git rev-parse HEAD`.
3. Run `.\scripts\verify-release.ps1` from the repository root.
4. The command refuses a dirty tree. It clears `ATLAS_LIVE_PROVIDERS`, writes the production build to `.next-release-check`, and leaves Playwright on `.next-e2e-phase2d`, API port 8011, and web port 3011. Pytest truncates only `atlas_test`.
5. Record the new counts. They replace the working-tree counts above only after this clean run passes.
6. Leave the processes on ports 8000 and 3000 running. The script does not tag or push.

## Before publishing

- [ ] Demo access, portfolio rehearsal, and deployment configuration are committed.
- [ ] `git status --porcelain` is empty.
- [ ] `.\scripts\verify-release.ps1` exits 0 on that commit.
- [ ] Alembic reports one head.
- [ ] The public host loads its own environment, runs `alembic upgrade head`, and keeps live send and live charge flags off.
- [ ] `.env`, local databases, and uploads remain untracked.

## Hygiene

Checked at `44631e1` without staging the dirty tree:

- `.env`, `apps/web/.env.local`, `infrastructure/staging/.env`, and `var/` are ignored.
- The only tracked environment files are `.env.example`, `apps/web/.env.example`, `infrastructure/staging/.env.example`, and `infrastructure/production/.env.example`.
- Uploads belong under `var/atlas-storage`.

## Deployment prerequisites

A public host is one API process and the replacement Next.js app behind one browser origin. PostgreSQL with pgvector and the upload disk persist. Migrations run before traffic. Session cookies stay HttpOnly. A shared demo sets the public-demo flag and must refuse a paid model key, live email, and an n8n URL. The portfolio procedure and its remaining prerequisites are in [portfolio-release-checklist.md](portfolio-release-checklist.md). Do not publish until that list is accepted.

## Deployment-blocking defects

No deployment-blocking defect was found in the committed product. The clean verification has not been run because the working tree is still dirty. That is a gate for the next commit, not a defect in `44631e1`.
