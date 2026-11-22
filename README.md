# ATLAS AI

ATLAS is a business operations command center: a Next.js dashboard, a FastAPI modular monolith, and PostgreSQL with pgvector.

Day 1 covers authentication, organizations, memberships, and the dashboard shell. Day 2 adds organization-scoped CRM, document ingestion with hybrid retrieval, and a read-only assistant. Day 3 adds an inquiry agent. It proposes CRM changes and waits for an admin to approve them. Workflows and analytics remain empty states. The assistant still does not create or change CRM records.

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

The API container can be started with `docker compose up --build api` after `.env` exists. It runs migrations on startup and stores uploads in the `atlas_uploads` volume. The seed command stays manual because it resets the three synthetic passwords. It also inserts clearly synthetic CRM rows for Atlas Demo and Northwind.

## Documents and the assistant

Uploads accept PDF and UTF-8 text files up to `ATLAS_MAX_UPLOAD_BYTES` (10 MiB by default). Chat and embeddings are OpenAI-compatible HTTP calls. The defaults are `gpt-4o-mini` and `text-embedding-3-small` at `https://api.openai.com/v1`, with embeddings fixed at 1536 dimensions. Leave `ATLAS_LLM_API_KEY` and `ATLAS_EMBEDDING_API_KEY` empty until you have a provider. Put real keys only in the gitignored `.env`, then restart the API process. Do not commit them or paste them into chat. Empty keys return an error. The API does not invent a successful answer or a citation.

`ATLAS_MAX_COSINE_DISTANCE` defaults to `0.55`. That value is pgvector cosine distance, equal to 1 - cosine similarity. Distant vector neighbors are dropped. A shared keyword can still cite a passage through full-text search, and a paraphrase with no shared words is cited only inside the distance limit.

If the API stops while a document is pending or processing, the next startup indexes it again. A second run replaces the same chunks instead of appending them. A failed reindex keeps the earlier chunks when they already exist.

The assistant answers from retrieved document excerpts and from CRM records it is allowed to read. Citations are the retrieved rows, shown separately as company documents or CRM records. A question with no matching records gets an explicit refusal and does not call the model.

## Agent runs and approvals

From Agent Runs, choose an inquiry and start a run. The agent classifies it, searches company documents, and looks up the contact through a read-only MCP server bound to the current organization. It then stores proposed actions and pauses. An admin approves or rejects each one in Approvals. Resume the run to apply the approved payload. Rejected actions do not write. The customer response and the appointment request are saved as CRM interactions. They are not emailed and they do not book a calendar.

`ATLAS_APPROVAL_TTL_HOURS` defaults to 24. Changing the stored payload after it was proposed invalidates that approval. An empty `ATLAS_LLM_API_KEY` fails the run with `llm_unconfigured` instead of inventing a classification.

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
