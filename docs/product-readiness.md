# ATLAS product readiness — Phase 1

Status date: 2026-11-28  
Phase: Engineering foundation and canonical product baseline  
Branch: `codex/atlas-phase1-foundation`

## Decision record

`apps/web-rebuild` is the canonical frontend for local development, staging, production, and the portfolio deployment. `apps/web` remains in the repository as a legacy client and source of useful API/browser coverage while that coverage is migrated. The architecture remains a modular monolith with PostgreSQL and pgvector. No microservices, Kubernetes, Kafka, additional vector database, paid inference, or public deployment is introduced by this phase.

## Phase 1 delivery

- Canonical frontend linting, unit testing, typechecking, production build, and Playwright gates are defined in the frontend package and CI.
- Focused unit tests cover request construction and error normalization, CSRF/session behavior, assistant SSE token/phase/done handling, billing and provider-status contracts, permission mutation contracts, and conversation mapping.
- Development, staging, production, and portfolio deployment references are aligned to the canonical frontend. The legacy frontend remains covered by a separate non-canonical CI job.
- Portfolio media and first-cut backups remain preserved locally and are ignored by Git; they are not deleted or silently replaced.
- The release verification script now checks the dedicated Phase 1 branch and canonical frontend gates while retaining legacy unit/type/build coverage.

## Evidence and remaining blockers

| Check | Result | Notes |
| --- | --- | --- |
| Canonical frontend unit tests | Passing | Focused data-layer tests pass. |
| Canonical frontend typecheck | Passing | `npm run typecheck --prefix apps/web-rebuild`. |
| Canonical frontend lint/build | Pending final run | Must be run after the final documentation/config changes. |
| API collection | Collected | 368 tests were collected in the existing API environment. |
| API execution | Blocked locally | The isolated PostgreSQL endpoint expected by the suite was unavailable at `127.0.0.1:5434`. |
| Compose/container proof | Blocked locally | Docker Desktop Linux engine was unavailable. Compose files and static contract tests remain inspectable. |
| Browser acceptance | Blocked locally | The replacement suite requires the disposable API/Postgres path; CI remains the authoritative runnable gate. |

## Acceptance boundary

Phase 1 is complete when the canonical frontend gates, backend checks, deploy-contract checks, secret scan, and dependency audit pass in CI, and the disposable browser suite completes against isolated data. This phase does not claim live provider qualification, external billing, HTTPS deployment, backup restoration, or production traffic readiness.

The next phase may address product acceptance and provider/staging qualification. It must not silently restore the legacy frontend as a deployment target or change assistant/RAG algorithms without a separately scoped decision.
