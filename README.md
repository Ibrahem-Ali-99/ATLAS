# ATLAS AI

Day 1 foundation for the ATLAS business operations command center: a Next.js dashboard, a FastAPI modular monolith, and PostgreSQL with pgvector.

This release implements authentication, organizations, memberships, session authorization, and dashboard navigation. CRM, AI assistant, agent runs, workflows, analytics, and approvals are visible as labeled empty states. They are not implemented.

## Stack

- Next.js 16, React 19, TypeScript, Tailwind CSS 4, shadcn-style UI, TanStack Query
- FastAPI, Pydantic v2, SQLAlchemy 2, Alembic
- PostgreSQL with pgvector
- Password hashing: `pwdlib` with Argon2
- Session cookies: `itsdangerous` signed HttpOnly cookies plus server-side session rows

## Prerequisites

- Docker with Docker Compose
- [uv](https://docs.astral.sh/uv/) and Python 3.12
- Node.js 22 or newer

## Setup

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
# Replace ATLAS_SECRET_KEY in .env with a random string of at least 32 characters.

docker compose up -d postgres
cd apps\api
uv sync
uv run alembic upgrade head
uv run python -m app.scripts.seed
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd apps\web
Copy-Item .env.example .env.local
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open http://127.0.0.1:3000. The page and `NEXT_PUBLIC_API_URL` must use the same loopback host (`127.0.0.1` or `localhost`); browsers treat those names as different sites, and the API only listens on IPv4 `127.0.0.1`. CORS allows both `http://127.0.0.1:3000` and `http://localhost:3000`. API docs are at http://127.0.0.1:8000/docs when `ATLAS_ENVIRONMENT` is not `production`.

If another Postgres instance already owns host port 5432, set `POSTGRES_PORT` and the port in `ATLAS_DATABASE_URL` to a free port, then run `docker compose up -d postgres` again. The API container still reaches Postgres on the internal port 5432.

The API container can be started with `docker compose up --build api` after `.env` exists. It runs migrations on startup. The seed command stays manual because it resets the three synthetic passwords.

## Synthetic local accounts

The seed is idempotent. Running it again updates the same rows and resets those passwords to the values in `.env`. It refuses to run when `ATLAS_ENVIRONMENT=production`.

| Email | Organization | Role |
| --- | --- | --- |
| `admin@example.com` | Atlas Demo | admin |
| `staff@example.com` | Atlas Demo | staff |
| `outsider@example.org` | Northwind | admin |

Passwords come from `SEED_*_PASSWORD` in `.env`. The checked-in example uses `change-me-admin`, `change-me-staff`, and `change-me-outsider`. Change them before any shared environment. The admin account is not a member of Northwind.

## Tests and quality checks

Start Postgres first. The suite uses databases `atlas_test` and `atlas_migration_test`, created automatically. It truncates only `atlas_test`.

From the repository root, `.\scripts\check.ps1` runs the API and web checks. It also runs gitleaks, through a local install or Docker. GitHub Actions runs the same checks on push and pull request. Install the local hooks once with `uvx pre-commit install` (requires `uv` and Node.js).

```powershell
cd apps\api
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy
uv run pytest
```

Frontend checks, from `apps\web`. `next build` must run before `tsc` on a clean checkout because Next generates `next-env.d.ts` and `.next/types`.

```powershell
npm run lint
npm run build
npm run typecheck
```

## Security boundaries in this release

- Passwords are hashed with Argon2. The API does not return password hashes.
- The session cookie is HttpOnly and SameSite=Lax. `ATLAS_COOKIE_SECURE` must be true in production, and a placeholder secret is rejected there.
- Logout revokes the server session. A signed cookie whose session row is missing or revoked is rejected.
- State-changing requests other than login require the CSRF token returned by login and `/api/v1/auth/me`.
- Organization routes load the membership for the authenticated user. They do not treat a client-supplied organization id or role as authorization.

Rate limiting, a production penetration test, and browser-level cookie checks are not part of this release. Do not treat the items above as a completed security audit.

## Layout

```text
apps/api          FastAPI application, migrations, and tests
apps/web          Next.js dashboard
infrastructure    Compose services and Postgres init SQL
scripts           Seed wrapper and local quality checks
.cursor           Engineering rules and the review skill
.github           CI
automation        Reserved
evaluation        Reserved
docs              Short architecture note
```
