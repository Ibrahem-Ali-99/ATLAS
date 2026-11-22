# Architecture

ATLAS is a modular monolith. Day 1 implements the platform shell only.

## Backend

`apps/api` is a FastAPI application. HTTP routes live under `/api/v1`. Domain code for identity lives in `app/domains/identity`. Shared configuration, database sessions, logging, errors, and session cookies live in `app/core`.

Later domains (CRM, knowledge retrieval, agents, automation, approvals, ML, analytics, monitoring) should be added as new packages under `app/domains` with their own models, services, and routers. They are not stubbed in this release.

## Authorization

A session cookie identifies the user. Organization access is loaded from `memberships` for that user. A path or header organization id is only a lookup key. Roles are `admin` and `staff` on the membership row.

## Data

PostgreSQL is provided by the `pgvector/pgvector` image. The first migration enables the `vector` extension and creates users, organizations, memberships, and sessions. No vector columns exist yet.

## Frontend

`apps/web` is a Next.js App Router client of the API. Authenticated pages call `/api/v1/auth/me`. Pages for later modules render an explicit empty state and do not invent records.

## Engineering standards

Cursor rules in `.cursor/rules` record the boundaries above. The review procedure is `.cursor/skills/engineering-review/SKILL.md`. Ruff, mypy, pytest, ESLint, the Next.js build, TypeScript, and gitleaks run in `.github/workflows/ci.yml` and `scripts/check.ps1`.
