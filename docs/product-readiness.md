# ATLAS product readiness — Phase 1

Status date: 2026-11-28  
Phase: Engineering foundation and canonical product baseline  
Branch: `feature/atlas-product-readiness`  
Qualification commit: recorded after this evidence update

## Decision record

`apps/web-rebuild` is the canonical frontend for local development, staging, production, portfolio, CI, and release verification. `apps/web` remains in the repository as a legacy client and retains its own coverage. The architecture remains a modular monolith with PostgreSQL and pgvector. No microservices, Kubernetes, Kafka, additional vector database, paid inference, or public deployment is introduced by this phase.

## Qualification evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Repository baseline | Passing | Required HEAD before qualification was `50afa303e7f3f3bd0db2ad540b6f2cc1eb1c18d6`; branch renamed to `feature/atlas-product-readiness`. |
| Docker and PostgreSQL | Passing | Docker Engine 29.4.3 / Compose v5.1.3; `atlas-postgres-1` healthy on `127.0.0.1:5434`; connectivity and pgvector verified. |
| Alembic | Passing | Single migration head: `20261127_0057 (head)`; migration tests use disposable `atlas_migration_test`. |
| Backend regression | Passing | `365 passed, 3 skipped`; authoritative run used disposable `atlas_test`. The rehearsal DB run exposed one expected test-harness database-name contract and was rerun against the suite’s required disposable name. |
| Backend Ruff | Blocked | `13 errors`: 2 import-order findings and 11 existing line-length findings. |
| Backend formatting | Blocked | `37 files would be reformatted`; no mass cosmetic rewrite was applied. |
| Backend mypy | Blocked | `76 errors in 24 files`, predominantly pre-existing assistant, analytics, integration, script, and test typing debt. |
| Canonical frontend unit tests | Passing | 5 passed, 0 failed. |
| Canonical frontend lint | Passing with warnings | 0 errors, 66 warnings. Warnings are classified below. |
| Canonical frontend typecheck | Passing | `npm run typecheck --prefix apps/web-rebuild`. |
| Canonical frontend production build | Passing | Production build completed; routes `/`, `/case-study`, `/demo`, `/invite/accept`, `/login`, `/reset-password`, `/site`. |
| Canonical Playwright | Passing | 11 passed; live providers and paid inference disabled. |
| Legacy frontend safety coverage | Passing | Existing legacy unit/typecheck coverage remains; its CI job is now explicitly non-blocking for canonical releases. |
| Configuration contracts | Passing | Development, staging, production, and portfolio Compose config; staging 3 passed; production 10 passed; portfolio 12 passed. |
| Portfolio isolated deployment proof | Passing | Owned network/volumes/containers, Caddy health, public routes, document readiness, backup/restore, Harbor/demo isolation, and live-project preservation all passed. |
| Production isolated container proof | Passing | `startup_proof ok=true health=healthy`; production safety, health/readiness, migrations, non-root process, and restricted docs checks passed. |
| JavaScript dependency audit | Passing | `npm audit --audit-level=high`: 0 vulnerabilities. |
| Python dependency audit | Passing | Locked export plus strict hash-verified `pip-audit`: no known vulnerabilities. |
| Secret scan | Passing | Pinned Gitleaks scan: no leaks found. Exact synthetic test tokens are documented in `.gitleaks.toml`; no operational credentials were changed. |

## Defect corrections

- Corrected canonical workflow run state handling: the UI now polls the bounded asynchronous run transition instead of rendering a stale `pending` record after dispatch. This fixed the approval-flow browser failure and produced 11/11 Playwright passes.
- Marked the retained legacy frontend CI job non-blocking for canonical releases while preserving its tests and source.
- No Assistant or RAG algorithm was modified, and no frontend redesign was performed.

## Frontend warning classification

- Low severity: unused imports/variables and anonymous PostCSS default export.
- Medium severity: missing or unnecessary React hook dependencies; these warrant targeted lifecycle review but were not changed without a reproducing defect.
- Medium performance: two `<img>` usages and one internal `window.location.assign`; these are optimization/navigation warnings, not observed correctness failures.
- No lint errors remain. Cosmetic cleanup was intentionally deferred.

## Preservation and deployment boundary

Operational, Harbor, portfolio-media, backup, credential, and unrelated project data were preserved. Existing operational containers were inspected but not reset, truncated, or overwritten. Disposable databases and container projects were isolated and cleaned only within their own names. Live external operations, paid inference, public deployment, and merging into the default branch remain disabled.

## Acceptance verdict

Phase 1 is **conditionally qualified, not fully accepted**: runtime regression, canonical frontend, browser, migration, isolated deployment, configuration, dependency, and secret gates pass, but the repository’s required backend Ruff, formatting, and mypy gates remain red due to pre-existing static debt. Phase 2 must not begin until those explicit blockers are resolved or separately dispositioned.
