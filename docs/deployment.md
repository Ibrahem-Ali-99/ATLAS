# Deployment

ATLAS is one API process and one Next.js app. Training, document ingestion, workflow recovery, and LangGraph checkpoint setup run inside the API process. Do not start a second copy of the API as a worker. Both processes would recover the same rows.

No public host was created for this release. The commands below are the deployment configuration. They do not provision paid accounts. The production host, backup, and recovery procedure is in [production.md](production.md). The public portfolio demonstration is in [portfolio-deployment.md](portfolio-deployment.md).

## Local Windows workflow

Postgres, Mailpit, and n8n come from Compose. The API and web stay on the host so they can use the existing checkout.

```powershell
docker compose up -d postgres mailpit n8n
```

Normal development reserves host port 5434 and keeps the same port in `ATLAS_DATABASE_URL`. The Compose network still uses PostgreSQL’s internal port 5432. If a different local port is intentionally required, change both values in the uncommitted `.env` and use the diagnostic output to confirm the selected owner.

For normal local development, use `.\scripts\start-dev.ps1`. It starts PostgreSQL on host port 5434, the host API on 8000, and the host web server on 3000 with the canonical browser origin `http://127.0.0.1:3000`. The redacted diagnostic report is written under `var/dev`. `next start` records the static files that exist when the process starts. After `npm run build`, restart that process. A page can otherwise ask for a new chunk and receive 404. The browser test uses isolated ports 8011/3011 and its own `NEXT_DIST_DIR`; it must not share the normal browser profile or database. Do not also start the Compose `api` or `web` services while host processes are running. They publish the same ports.

`docker compose --profile demo up` builds the API and web containers. Use it when you want the container path, not alongside the host processes.

Migrations run when the API container starts (`alembic upgrade head`). On the host, run `uv run alembic upgrade head` from `apps/api` before serving traffic. The dev database URL comes from `.env` and is not printed by the seed script.

## Cookies and split hosting

The session cookie is HttpOnly and SameSite=Lax. A browser will not send it from a Vercel site to an API on another registrable domain. CSRF also expects the browser to call the API that issued the token.

Host the web and API behind one origin. A reverse proxy can forward `/api/` to the API and everything else to Next.js. Set `ATLAS_COOKIE_SECURE=true` only for HTTPS. Production refuses a placeholder `ATLAS_SECRET_KEY` and refuses `ATLAS_LLM_PROVIDER=double`.

`NEXT_PUBLIC_API_URL=same-origin` builds a web image that calls `/api/v1` on the page's own host, so a new HTTPS hostname does not require a rebuild. The staging Compose file passes that value. An explicit URL is still baked at build time. Local development and the demo profile keep `http://127.0.0.1:8000`. The image sets `NEXT_STANDALONE=1` so Next emits a standalone server. A host checkout leaves that unset, so `npm run start` keeps working. Staging routing is `infrastructure/compose.staging.yaml`.

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

## Public demo, rate limits, and key rotation

Set `ATLAS_PUBLIC_DEMO=true` for a shared demo. The process then refuses to start with a paid model key, a live email mode, or an n8n webhook URL. Anonymous requests still need a session for CRM, documents, the assistant, and agents. The seed command resets the three development passwords and exits when the environment is production or the public-demo flag is set.

Login failures are counted in memory for the email and for the direct client address. The default is 8 failures per email and 40 per address inside 15 minutes. A second API process has its own counters. The address is the TCP peer, not `X-Forwarded-For`. Behind one reverse proxy, the address limit is shared by everyone who reaches that process.

`ATLAS_SECRET_KEY` signs session cookies and seals webhook secrets. Replacing it signs everyone out. Previously sealed webhook secrets cannot be opened with the new key. Create a new webhook key after a rotation. There is no second active key.

Webhook request limits are also per process. They are not a shared store.

## Live models

Chat can use Groq's OpenAI-compatible API. In the gitignored `.env`, set `ATLAS_LLM_PROVIDER=groq`, `ATLAS_LLM_BASE_URL=https://api.groq.com/openai/v1`, `ATLAS_LLM_MODEL` to a chat model the account can call, and `ATLAS_LLM_API_KEY` to the key. `.env.example` keeps the key empty. Do not commit it. `ATLAS_PUBLIC_DEMO=true` refuses to start when that key is set, and refuses the Groq client even if the key is later injected.

Embeddings can use a local Ollama server. Install it from https://ollama.com/download, then run `ollama serve` and `ollama pull nomic-embed-text`. On the host, set `ATLAS_EMBEDDING_PROVIDER=ollama`, `ATLAS_EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1`, `ATLAS_EMBEDDING_MODEL=nomic-embed-text`, and `ATLAS_EMBEDDING_DIMENSIONS=768`. A container cannot use `127.0.0.1` to reach Ollama on the host. Use `http://host.docker.internal:11434/v1` there. Ollama does not take an API key. A stopped server returns `embedding_unavailable`. The API does not fall back to hash embeddings.

`nomic-embed-text` returns 768 values. Those are stored in `chunks.embedding_768` with `chunks.embedding_model`. The original `chunks.embedding` column stays `vector(1536)`, so existing rows are not dropped or padded. Search uses only the column and model name that match the current settings. A 1536 row with a null model is the legacy index and is not compared with a 768 query. Build a replacement index in Integrations when changing the model. The worker activates the staged vectors and settings together.

OpenAI remains available by setting the provider back to `openai` and a 1536-wide embedding model. Deterministic providers (`double`) cover tests and are not live accuracy. Langfuse stays optional. Cost is stored only when both token prices are set.
