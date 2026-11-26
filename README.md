# ATLAS AI

ATLAS is an operations workspace for a consulting team that should not let a model change customer records on its own.

A salesperson receives an inquiry. ATLAS keeps the company, the documents, and the proposed next step in one organization. The assistant answers from retrieved passages and CRM rows. An agent can draft a lead update, an email, and a calendar hold, then stop. An admin approves the exact payload before anything is written. Customer replies and calendar requests execute only after administrator approval. External transports require configuration. A lead score is advisory and is trained on synthetic data.

The implementation is one Next.js app and one FastAPI process, with PostgreSQL and pgvector. It is a portfolio system with a local demo, not a hosted production service. Live model calls and Langfuse export stay off until keys are configured. See `docs/deployment.md` for hosting, `docs/architecture.md` for the data flow, and `docs/demo.md` for the walkthrough.

[Engineering handoff](docs/ATLAS_ENGINEERING_HANDOFF.md) · [Product backlog](docs/product-completion-backlog.md) · [Provider activation](docs/provider-activation.md)

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

## Local development

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
# Replace ATLAS_SECRET_KEY in .env with a random string of at least 32 characters.
uv sync --directory apps\api
npm ci --prefix apps\web
.\scripts\start-dev.ps1
```

Open http://127.0.0.1:3000. This is the canonical local browser origin. The host API uses http://127.0.0.1:8000 and PostgreSQL is published on 127.0.0.1:5434. Use `.\scripts\diagnose-dev.ps1` for redacted port, Docker, Compose, and readiness diagnostics. Use `.\scripts\stop-dev.ps1` to stop only the ATLAS infrastructure services; it preserves volumes and databases. API docs are at http://127.0.0.1:8000/docs when `ATLAS_ENVIRONMENT` is not `production`.

Container startup, health checks, and a single-origin hosting layout are in `docs/deployment.md`. Do not start the Compose `api` or `web` services while the host processes above are using ports 8000 and 3000.

Normal development intentionally reserves host port 5434 to keep the application database separate from the default PostgreSQL port. Do not change only one of `POSTGRES_PORT` and `ATLAS_DATABASE_URL`; the startup script rejects a mismatch. The API container still reaches Postgres on the internal Docker port 5432.

Mailpit accepts sandbox SMTP on port 1025 and shows the mailbox at `http://127.0.0.1:8025`. n8n listens on port 5678. An API process on the host dispatches lead events to `http://127.0.0.1:5678/webhook/atlas-lead`. The Compose API service uses `http://n8n:5678/webhook/atlas-lead` on the Docker network. n8n calls the host API at `http://host.docker.internal:8000`. Import `infrastructure/n8n/lead-processing.json` and `infrastructure/n8n/follow-up.json`, then copy the ATLAS webhook key into `ATLAS_HOOK_KEY_ID` and `ATLAS_HOOK_SECRET` for the scheduled follow-up. The daily schedule and the manual trigger both enter the same signer. This n8n release starts `n8n execute` from a manual trigger, not from the schedule node. The webhook rate limit is counted inside each API process and is not shared across instances. Leave `ATLAS_EMAIL_MODE` as `sandbox` unless live delivery is explicitly enabled. ATLAS reserves appointments locally until a workspace connects Google Calendar. Approved Google appointments check availability and create a private event.

The API container can be started with `docker compose up --build api` after `.env` exists. It runs migrations on startup and stores uploads in the `atlas_uploads` volume. The seed command stays manual because it resets the three synthetic passwords. It also inserts clearly synthetic CRM rows for Atlas Demo and Northwind.

## Documents and the assistant

Uploads accept PDF and UTF-8 text files up to `ATLAS_MAX_UPLOAD_BYTES` (10 MiB by default). Chat and embeddings are OpenAI-compatible HTTP calls. OpenAI remains available with `gpt-4o-mini` and `text-embedding-3-small` at `https://api.openai.com/v1`. That embedding model returns 1536 values and uses `chunks.embedding`.

Groq can serve chat without an OpenAI key. In the gitignored `.env`, set `ATLAS_LLM_PROVIDER=groq`, `ATLAS_LLM_BASE_URL=https://api.groq.com/openai/v1`, `ATLAS_LLM_MODEL` to a chat model the account can call, and `ATLAS_LLM_API_KEY` to the key. `.env.example` leaves the key empty. Do not commit it or paste it into chat. `ATLAS_PUBLIC_DEMO=true` refuses to start when a model key is set, and it refuses the Groq client.

Ollama can serve embeddings locally. Install it from https://ollama.com/download, then run `ollama serve` and `ollama pull nomic-embed-text`. On the host, set `ATLAS_EMBEDDING_PROVIDER=ollama`, `ATLAS_EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1`, `ATLAS_EMBEDDING_MODEL=nomic-embed-text`, and `ATLAS_EMBEDDING_DIMENSIONS=768`. A container reaches Ollama on the host at `http://host.docker.internal:11434/v1`. Ollama does not use an API key. A stopped server returns `embedding_unavailable`. The API does not fall back to hash embeddings.

`nomic-embed-text` returns 768 values. Those are stored in `chunks.embedding_768` with the model name. The 1536 column is left in place, so existing rows are not dropped or padded. Search compares a query only with chunks from the configured model and width. A 1536 row with no model name is the legacy index and is not compared with a 768 query. Switching models does not reindex on startup. Build a replacement index in Integrations > Embeddings to switch the active model. The existing index stays searchable during the build. Pending or processing documents are still resumed on startup, and a failed reindex keeps the earlier chunks when they exist.

`ATLAS_MAX_COSINE_DISTANCE` defaults to `0.55`. That value is pgvector cosine distance, equal to 1 - cosine similarity. Neighbors farther than that are dropped before ranking. A passage is cited when it shares a content word with the question, or when it shares no words and its distance is at or below 0.45. One shared word is enough, so an ambiguous question such as "public code" can still cite a brochure that contains those words. The 0.45 line was measured with `nomic-embed-text`: relevant paraphrases landed around 0.37–0.43, an exact code with no other wording around 0.47, and an unsupported home-address question around 0.48. It is not a universal boundary for every document or for 1536-wide OpenAI vectors. A weak paraphrase inside 0.45 can still be cited, and the model may answer from that passage. A question with no evidence is refused and does not call the model.

Leave provider keys empty until a provider is configured. Put real keys only in the gitignored `.env`, then restart the API process. Empty keys return an error. The API does not invent a successful answer or a citation. Deterministic providers (`double`) cover tests and are not live accuracy. More setup detail is in `docs/deployment.md`.

The assistant answers from retrieved document excerpts and from CRM records it is allowed to read. Citations are the retrieved rows, shown separately as company documents or CRM records. A question with no matching records gets an explicit refusal and does not call the model.

## Agent runs and approvals

From Agent Runs, choose an inquiry and start a run. The agent classifies it, searches company documents, and looks up the contact through a read-only MCP server bound to the current organization. It then stores proposed actions and pauses. An admin approves or rejects each one in Approvals. Resume the run to apply the approved payload. Rejected actions do not write. An approved customer response is sent through the configured email mode, which is sandbox SMTP unless live delivery is turned on, and stored as an email interaction. An approved appointment becomes an ATLAS reservation or a private Google Calendar event, and a CRM call interaction. Neither one runs before approval.

`ATLAS_APPROVAL_TTL_HOURS` defaults to 24. Changing the stored payload after it was proposed invalidates that approval. An empty `ATLAS_LLM_API_KEY` fails the run with `llm_unconfigured` instead of inventing a classification.

## Synthetic local accounts

The seed is idempotent. Running it again updates the same rows and resets those passwords to the values in `.env`. It refuses to run when `ATLAS_ENVIRONMENT=production` or `ATLAS_PUBLIC_DEMO=true`.

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
npm run e2e
```

`npm run e2e` starts an API on port 8010 against the `atlas_e2e` database and the web dev server on port 3010. It does not call a paid model.

## Demonstration

`uv run python -m app.scripts.seed` from `apps/api` creates Atlas Demo and Northwind and resets the three development passwords. It is idempotent. It refuses `ATLAS_ENVIRONMENT=production` and `ATLAS_PUBLIC_DEMO=true`. The walkthrough, including what is deterministic, sandbox, or simulated, is `docs/demo.md`.

## Security boundaries in this release

- Passwords are hashed with Argon2. The API does not return password hashes. Unknown, wrong, and inactive accounts share one login error.
- Failed logins are limited per email and per direct client address inside this process. A second process does not share the counters.
- The session cookie is HttpOnly and SameSite=Lax. `ATLAS_COOKIE_SECURE` must be true in production, and a placeholder secret is rejected there.
- Logout revokes the server session. A signed cookie whose session row is missing or revoked is rejected.
- State-changing requests other than login require the CSRF token returned by login and `/api/v1/auth/me`.
- Organization routes load the membership for the authenticated user. They do not treat a client-supplied organization id or role as authorization.
- `ATLAS_PUBLIC_DEMO=true` refuses paid model keys, live email, an n8n URL, and the development seed.
- Uploaded files must be PDF or TXT. Model artifacts are loaded only from the model directory, not from uploads.

Webhook callbacks are rate limited inside each API process. The seeded passwords in `.env.example` are for local development. Playwright covers the signed-in workspace in `apps/web/e2e` with deterministic providers. That is not a penetration test. `docs/case-study.md` records the engineering limits.

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
docs              Architecture and deployment notes
```
