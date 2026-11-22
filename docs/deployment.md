# Deployment

ATLAS is one API process and one Next.js app. Training, document ingestion, workflow recovery, and LangGraph checkpoint setup run inside the API process. Do not start a second copy of the API as a worker. Both processes would recover the same rows.

No public host was created for this release. The commands below are the deployment configuration. They do not provision paid accounts.

## Local Windows workflow

Postgres, Mailpit, and n8n come from Compose. The API and web stay on the host so they can use the existing checkout.

```powershell
docker compose up -d postgres mailpit n8n
```

`POSTGRES_PORT` in `.env` overrides the host port. This machine uses 5434 because another Postgres already owns 5432. Leave that override in place.

Run the API from `apps/api` with `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`. Run the web from `apps/web` with `npm run dev` or `npm run start`. Do not also start the Compose `api` or `web` services while those host processes are running. They publish the same ports.

`docker compose --profile demo up` builds the API and web containers. Use it when you want the container path, not alongside the host processes.

Migrations run when the API container starts (`alembic upgrade head`). On the host, run `uv run alembic upgrade head` from `apps/api` before serving traffic. The dev database URL comes from `.env` and is not printed by the seed script.

## Cookies and split hosting

The session cookie is HttpOnly and SameSite=Lax. A browser will not send it from a Vercel site to an API on another registrable domain. CSRF also expects the browser to call the API that issued the token.

Host the web and API behind one origin. A reverse proxy can forward `/api/` to the API and everything else to Next.js. Set `ATLAS_COOKIE_SECURE=true` only for HTTPS. Production refuses a placeholder `ATLAS_SECRET_KEY` and refuses `ATLAS_LLM_PROVIDER=double`.

`NEXT_PUBLIC_API_URL` is fixed when the web image is built. The Compose web service passes it as a build argument. For a single-origin proxy, build the web with that public origin. The image sets `NEXT_STANDALONE=1` so Next emits a standalone server. A host checkout leaves that unset, so `npm run start` keeps working.

The agent reads company documents through a short-lived process. That process receives the configured embedding provider, so `double` and a real key are not split between the API and the tool. A public demo should leave provider keys empty and leave the n8n URL empty. Empty keys fail closed. Do not give the seeded admin password to visitors if n8n, live email, or a paid model key is configured.

## Suggested hosts, without creating them

| Piece | Practical host | Notes |
| --- | --- | --- |
| Next.js | Vercel or the web container | Build with the public API origin. Hobby quotas are enough for a demo. |
| API | Render, Railway, or any container host | One web service from `apps/api/Dockerfile`. Persistent disk for `/var/lib/atlas/storage` and `/var/lib/atlas/models`. |
| Postgres | Neon, Supabase, or RDS with pgvector | The image in Compose is `pgvector/pgvector:pg17`. A database without `vector` will fail migration. |
| n8n | The same private network as the API | Do not publish the editor on the public internet. Copy the webhook key into n8n after creating it. The secret is shown once. |
| Langfuse | Optional | Leave both keys empty. Export stays unverified until a project exists. |

Render and Railway container services are typically a few dollars a month after free credits. A small managed Postgres with pgvector is a separate bill. n8n's hosted product is a separate bill; the Compose image avoids that. Do not turn on live email or a paid model key for a public demo. Empty provider keys fail closed. `double` is only for local tests and is rejected in production.

## Health

`GET /api/v1/health` answers without the database. `GET /api/v1/ready` checks the database. The API container health check uses `/ready`, so Compose waits until migrations and the database are usable.

## Live model status

`ATLAS_LLM_API_KEY` and `ATLAS_EMBEDDING_API_KEY` are empty in this checkout. Live embedding, grounded chat, and agent classification are blocked. Langfuse keys are empty, so remote traces are unverified. Deterministic providers (`ATLAS_LLM_PROVIDER=double` and `ATLAS_EMBEDDING_PROVIDER=double`) cover local browser tests and are not live accuracy.
