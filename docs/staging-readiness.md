# Staging readiness

Audit date: 2026-11-23. Repository `main` was `d336d1a` when this audit was written. Phase 1, below, is the first implementation cut. Nothing has been deployed to a VPS.

## Phase 1 — single HTTPS origin

Caddy is the only published service in `infrastructure/compose.staging.yaml`. It forwards `/api/` and `/api` to FastAPI without stripping the prefix, because the application routes are already `/api/v1/...`. Every other path goes to Next.js. Postgres, n8n, Mailpit, and Ollama are on the `private` network and have no host ports.

The web image used by that file is built with `NEXT_PUBLIC_API_URL=same-origin`. The browser then calls `/api/v1` on the host that served the page. Changing the staging hostname does not require another web build. Local `next dev` and the demo Compose profile still use `http://127.0.0.1:8000` when the variable is unset or set to that URL.

The API entrypoint starts as root, gives `/var/lib/atlas/storage` and `/var/lib/atlas/models` to uid 10001, and runs migrations and uvicorn as `atlas`. The session cookie stays HttpOnly, `SameSite=Lax`, and `Secure` because staging sets `ATLAS_COOKIE_SECURE=true`. Production mode still refuses a placeholder secret and a `Secure=false` cookie.

Local proof, from the repository root:

```powershell
py -3 infrastructure\staging\smoke_https.py
```

The script writes `infrastructure/staging/.env` when that file is missing, starts the stack, seeds only the staging database while the API is in `development`, then recreates the API in `production`. The site is `https://atlas.localhost:8443` with Caddy's local CA. On a VPS, set `STAGING_HOST` to the public name and set `STAGING_HTTP_PORT=80` and `STAGING_HTTPS_PORT=443`. Caddy uses Let's Encrypt for a public name.

Manual start, after `infrastructure/staging/.env` exists:

```powershell
docker compose --project-name atlas-staging --project-directory infrastructure -f infrastructure/compose.staging.yaml --env-file infrastructure/staging/.env up -d --build
```

The development Compose file is unchanged. `docker compose up` from the repository root still publishes the local ports.

Verified on 2026-11-23 from a clean browser context against `https://atlas.localhost:8443`. The smoke script trusted Caddy's local CA in the Windows Current User root store, then both the HTTPS client and Microsoft Edge completed the checks below. `ignoreHTTPSErrors` stayed false, and no browser request went to `127.0.0.1:8000`.

- Next.js served `/login` through Caddy. `GET /api/v1/health` reached FastAPI, so `/api` was forwarded intact.
- The session cookie was HttpOnly, Secure, and `SameSite=Lax`, with no `Domain`.
- `/api/v1/auth/me` kept the session. A company create without `X-CSRF-Token` returned `403 csrf_failed`. The same request with the token returned `201`.
- Staff could read that company and received `403 forbidden` for an approval. An outsider received `404 not_found` for the other organization and `200` for their own.
- Logout without the CSRF token returned `403`. Logout with the token cleared the cookie, and the old cookie then received `401 unauthenticated`.
- Edge signed in, opened Overview, CRM, Knowledge, and Assistant, signed out, and was returned to Sign in.
- The API process was uid 10001 and could write both data volumes. Postgres, the API, Mailpit, n8n, and Ollama published no host ports.

The product constraint that decides the architecture is in `docs/deployment.md`: the session cookie is HttpOnly and `SameSite=Lax`, and the browser must call the API that issued the CSRF token. The web app and the API have to share one HTTPS origin. Splitting them across Vercel and a separate API host breaks login.

## Proposed architecture

Run the whole staging stack on one small Linux VPS with Docker Compose. Put Caddy in front as the only public listener. Caddy terminates Let's Encrypt HTTPS and sends one hostname to the two app containers:

- `https://staging.example.com/api/` to the FastAPI container
- every other path to the Next.js container

Keep PostgreSQL, n8n, and Mailpit on the Compose network. Do not publish their ports. Reach the n8n editor and the Mailpit UI through an SSH tunnel when an operator needs them.

Use Groq only for chat. Use a 768-dimension embedding model for retrieval, so new chunks land in the existing `chunks.embedding_768` column and match the distance threshold measured for this product. The preferred way to do that without a schema change is Ollama on the same VPS, serving `nomic-embed-text`. A remote OpenAI-compatible embedding API is possible instead, and it also needs no column change, but only when the response is exactly 768 or 1536 floats. See [Embeddings](#embeddings).

Keep exactly one API container. Training, document ingestion, workflow recovery, and LangGraph checkpoint setup run in that process. A second copy would recover the same rows.

```text
Browser
  |
  |  HTTPS :443
  v
Caddy (Let's Encrypt, one hostname)
  |-- /api/*  --> api:8000     (one replica, migrations on start)
  |-- /*      --> web:3000
                     |
                     v
              postgres:5432    pgvector/pgvector:pg17
              n8n:5678         private, workflows imported by hand
              mailpit:1025     sandbox SMTP only
              ollama:11434     nomic-embed-text, 768 dimensions

Outbound only: https://api.groq.com  (chat)
```

Leave `ATLAS_PUBLIC_DEMO` false. That flag refuses a model key, live email, and n8n, so it cannot describe this staging environment. Leave email in sandbox mode and the calendar in simulation. Do not point staging at a real mailbox or a real calendar.

This is simpler and cheaper than a managed split, and it is the only layout that satisfies the cookie rule without new application code. Managed Postgres or a managed app host can replace pieces later. They should not be the first staging cut.

## Service dependencies

| Service | Required in staging | How it runs today | Staging requirement |
| --- | --- | --- | --- |
| Next.js 16 | Yes | `apps/web/Dockerfile`. The development service `web` is behind profile `demo`. | The staging service builds with `NEXT_PUBLIC_API_URL=same-origin` and starts on every staging boot. |
| FastAPI | Yes | `apps/api/Dockerfile`. The entrypoint runs `alembic upgrade head` and then uvicorn on `0.0.0.0:8000` as uid 10001. | One replica. Persistent disk for uploads and model artifacts. |
| PostgreSQL 17 + pgvector | Yes | `pgvector/pgvector:pg17` in `infrastructure/compose.yaml`. Named volume `atlas_postgres_data`. | Private. Migration `0001` runs `CREATE EXTENSION vector`. A server without that extension crash-loops the API. |
| n8n 1.70.3 | Yes for lead processing and follow-up | Image is pinned. Workflow JSON is mounted read-only at `/workflows`. n8n does not import that directory. | Private. Create the owner, import both workflow files, and activate them. Set the encryption key before the first start. |
| Mailpit 1.21 | Yes while email stays in sandbox | `axllent/mailpit:v1.21`. SMTP 1025, UI 8025. | Private. Sandbox mode refuses every SMTP host except `127.0.0.1`, `localhost`, `mailpit`, and `::1`. An external sandbox such as Mailtrap will not start. |
| Embedding provider | Yes for upload, search, and grounded answers | OpenAI-compatible `POST /embeddings`. Width must be 768 or 1536. | Ollama `nomic-embed-text` at 768 on the staging host, unless a remote 768 or 1536 endpoint is chosen deliberately. |
| Groq | Yes for live chat and agent classification | `ATLAS_LLM_PROVIDER=groq` and `https://api.groq.com/openai/v1`. | Outbound HTTPS and an API key stored only on the server. Groq is not the embedding provider. |
| Langfuse | No | Empty keys keep traces in Postgres. | Leave both keys empty until a project exists. |
| Redis, queue, object storage | No | Not in the stack. | Do not add them for staging. |

Startup order that Compose already encodes: Postgres healthy, Mailpit started, then the API. The web container waits for API `/api/v1/ready`. n8n has no health check and does not wait for the API.

`GET /api/v1/health` does not touch the database. `GET /api/v1/ready` runs a database query and nothing else. A green ready check does not mean Groq, Ollama, disk permissions, n8n, or Mailpit are usable.

## Embeddings

Ollama does not have to run on the staging host. The schema already has both widths, and settings reject every other width:

- `chunks.embedding` is `vector(1536)`
- `chunks.embedding_768` is `vector(768)`, added by migration `20261122_0010`
- `ATLAS_EMBEDDING_DIMENSIONS` must be 768 or 1536

Search reads only the column that matches the configured width, and only rows whose `embedding_model` matches the configured model. A 1536 row is not compared with a 768 query. Nothing reindexes on startup. Switching model or width on a database that already has chunks hides those chunks until each document is reindexed.

The local acceptance run used Ollama `nomic-embed-text` at 768. The citation cutoff of 0.45 was measured on that model. Staging should keep that pair if the goal is to reproduce the product:

```text
ATLAS_EMBEDDING_PROVIDER=ollama
ATLAS_EMBEDDING_BASE_URL=http://host.docker.internal:11434/v1
ATLAS_EMBEDDING_MODEL=nomic-embed-text
ATLAS_EMBEDDING_DIMENSIONS=768
ATLAS_EMBEDDING_API_KEY=
```

`127.0.0.1` inside the API container is the container, not the VPS. The API service does not set `host.docker.internal` today. Only the n8n service does. Add the same `extra_hosts` entry for the API, or run Ollama as a Compose service named `ollama` and use `http://ollama:11434/v1`. The `ollama` provider omits the API key and omits the `dimensions` field. A stopped server returns `embedding_unavailable`. The API does not fall back to hash embeddings.

A remote embedding service can be used without a migration when it speaks `POST /v1/embeddings` and returns one float vector per input at exactly 768 or 1536:

| Remote choice | Settings | Column | Fits current client |
| --- | --- | --- | --- |
| OpenAI `text-embedding-3-small` at 1536 | `embedding_provider=openai`, dimensions `1536` | `chunks.embedding` | Yes. The client sends `dimensions`. Cost is about $0.02 per million tokens. |
| OpenAI `text-embedding-3-small` reduced to 768 | `embedding_provider=openai`, dimensions `768` | `chunks.embedding_768` | Yes. Different model from `nomic-embed-text`, so do not mix the rows, and expect the 0.45 cutoff to move. |
| Groq embeddings | Not a supported setting | — | Do not plan on this. Chat settings cannot be reused. The `openai` provider always sends `dimensions`. The `ollama` provider never sends a bearer token. Groq's public API reference does not document an embeddings endpoint that matches either request. |

A model that returns 384, 1024, or 3072 values cannot be configured. The process refuses the setting, or ingestion fails with `embedding_dimension_mismatch`.

For a fresh staging database, either supported width is valid. Prefer 768 and `nomic-embed-text` so retrieval matches the measured threshold. Prefer OpenAI at 1536 only when avoiding a model process matters more than matching that threshold. Do not restore a dump taken under one model and then query it with the other.

## Required infrastructure

One amd64 VPS. GitHub Actions builds on `ubuntu-latest`, so the first staging host should be amd64 as well.

| Piece | Staging choice | Why |
| --- | --- | --- |
| Compute | 4 vCPU, 8 GB RAM, 80 GB disk | Postgres, one API process (NumPy and scikit-learn are in the image), Next.js, n8n, Mailpit, and Ollama. A 4 GB box is tight once images are built on the host. |
| Architecture | x86-64 | Matches CI. Avoid an ARM plan for the first cut. |
| OS | Ubuntu LTS | Docker Engine and the Compose plugin from Docker's repository. |
| Network | Public IPv4, firewall allows 22, 80, and 443 only | 80 exists so Caddy can complete the HTTP-01 challenge and redirect to HTTPS. |
| DNS | One A record for the staging hostname | The web image and the cookie share this name. |
| TLS | Caddy | `infrastructure/caddy/Caddyfile`. Local names use Caddy's CA. A public hostname uses Let's Encrypt when ports 80 and 443 are published. |
| Volumes | `atlas_postgres_data`, `atlas_uploads`, `atlas_models`, `atlas_n8n_data` | Mailpit mail can be discarded. The other four cannot. |
| Clock | NTP enabled | Webhook signatures expire outside 300 seconds of skew. |
| Backups | Nightly `pg_dump` plus a copy of the upload and model volumes, stored off the VPS | Also store `ATLAS_SECRET_KEY` and `N8N_ENCRYPTION_KEY` in a password manager. A database backup cannot unseal webhook secrets after the API key is lost. |
| Registry | Not required for the first boot | CI builds images and does not push them. The VPS builds from the git checkout. Add a registry later so the server does not compile on every deploy. |
| Observability | Container logs and `/api/v1/ready` | Langfuse stays off. |

Disk budget, roughly: API image 1–2 GB, web image under 300 MB, Postgres and n8n images, Ollama's `nomic-embed-text` around 300 MB, and headroom for builds. 80 GB is enough. 40 GB is acceptable only if images are built elsewhere.

Memory budget, roughly: Postgres 1 GB, API 1.5 GB with spikes during a model fit, Next.js 512 MB, n8n 512 MB–1 GB, Ollama under 1 GB for this embedding model, Caddy and Mailpit small. 8 GB leaves room for the build. Do not run a second API replica to "use the extra RAM".

## Environment variables

Compose reads `.env` from the directory where `docker compose` is run. The API image does not contain that file. `.env.example` is a local development template. Do not copy it onto the server unchanged.

The API container interpolates `ATLAS_PUBLIC_API_URL` from `.env` when it is set. The example file sets `http://host.docker.internal:8000`. The comment that says Compose overrides this to `http://api:8000` is only true when the variable is empty. On staging, set it explicitly to the Compose DNS name so n8n callbacks do not depend on the published host port.

### Values that must be set

| Variable | Staging value |
| --- | --- |
| `ATLAS_ENVIRONMENT` | `production` after the one-time seed. Production refuses a placeholder secret, `double` providers, and `ATLAS_COOKIE_SECURE=false`. |
| `ATLAS_PUBLIC_DEMO` | `false` |
| `ATLAS_SECRET_KEY` | Random, at least 32 characters, not the example placeholder. Seals webhook secrets and signs session cookies. Rotation signs everyone out and makes existing webhook secrets unreadable. |
| `ATLAS_DATABASE_URL` | Leave this to Compose. The API service builds `postgresql+psycopg://...@postgres:5432/atlas`. Use an alphanumeric database password so the URL does not need escaping. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Unique user and a long password. Not `atlas` / `atlas`. |
| `ATLAS_CORS_ORIGINS` | The public origin, for example `https://staging.example.com`. Unused for same-origin browser calls, and required if any client calls the API host directly. |
| `ATLAS_COOKIE_SECURE` | `true` |
| `ATLAS_LLM_PROVIDER` | `groq` |
| `ATLAS_LLM_BASE_URL` | `https://api.groq.com/openai/v1` |
| `ATLAS_LLM_API_KEY` | Server-side only. Never in the web image. |
| `ATLAS_LLM_MODEL` | A chat model the Groq account can call. |
| `ATLAS_EMBEDDING_PROVIDER` | `ollama` for the recommended path |
| `ATLAS_EMBEDDING_BASE_URL` | `http://host.docker.internal:11434/v1` or `http://ollama:11434/v1` |
| `ATLAS_EMBEDDING_MODEL` | `nomic-embed-text` |
| `ATLAS_EMBEDDING_DIMENSIONS` | `768` |
| `ATLAS_EMBEDDING_API_KEY` | Empty for Ollama |
| `ATLAS_PUBLIC_API_URL` | `http://api:8000` |
| `ATLAS_N8N_LEAD_WEBHOOK_URL` | `http://n8n:5678/webhook/atlas-lead` |
| `ATLAS_EMAIL_MODE` | `sandbox` |
| `ATLAS_EMAIL_LIVE_ENABLED` | `false` |
| `ATLAS_SMTP_HOST` | `mailpit` (Compose already sets this on the API service) |
| `ATLAS_SMTP_PORT` | `1025` |
| `ATLAS_SMTP_FROM` | A staging from-address. Mail stays in Mailpit. |
| `ATLAS_CALENDAR_MODE` | `simulation` |
| `ATLAS_STORAGE_DIR` | `/var/lib/atlas/storage` |
| `ATLAS_MODEL_DIR` | `/var/lib/atlas/models` |
| `NEXT_PUBLIC_API_URL` | `https://staging.example.com` as a **build argument**. Changing it requires a web image rebuild. |
| `N8N_ENCRYPTION_KEY` | Random, set before n8n's first start. The Compose default is the example placeholder. |
| `N8N_HOST` | The private name operators use, or the staging hostname if the editor is ever proxied. Today it is hardcoded to `127.0.0.1`. |
| `N8N_PROTOCOL` | `http` on the private network. `https` only if n8n itself terminates TLS. |
| `WEBHOOK_URL` | The URL n8n uses to register webhooks. The internal base `http://n8n:5678/` is enough while ATLAS calls n8n by Compose DNS. |
| `N8N_SECURE_COOKIE` | `true` if the editor is served over HTTPS. The file currently sets `false`. |
| `ATLAS_HOOK_KEY_ID` | The webhook key id returned once by `POST /api/v1/integrations/webhook-keys`. |
| `ATLAS_HOOK_SECRET` | The matching secret, shown once. The follow-up workflow signs with this pair. The lead workflow forwards the signature ATLAS already created. |
| `SEED_ADMIN_PASSWORD`, `SEED_STAFF_PASSWORD`, `SEED_OUTSIDER_PASSWORD` | Long unique passwords. The seed refuses `production`, so these are used only for the one-time bootstrap below. |

### Leave unset or at the code defaults

`ATLAS_LANGFUSE_PUBLIC_KEY`, `ATLAS_LANGFUSE_SECRET_KEY`, `ATLAS_LANGFUSE_HOST`, both token prices, `ATLAS_MCP_PYTHON`, `ATLAS_LLM_MAX_OUTPUT_TOKENS`. Empty Langfuse keys keep traces local. An empty MCP path uses the virtualenv Python already on `PATH` in the image.

Do not commit `.env`. Do not bake secrets into either Dockerfile. CI already runs gitleaks. There is no deploy workflow and no GitHub Environment for staging secrets yet. Until that exists, the secret store is a root-owned file on the VPS, mode `0600`, plus a copy in a password manager.

## Security concerns

**Public ports.** `infrastructure/compose.yaml` publishes Postgres `5432`, the API `8000`, Mailpit `1025` and `8025`, and n8n `5678` on all interfaces. The checked-in defaults are database user `atlas` / password `atlas`, n8n encryption key `replace-with-a-long-random-string`, and `N8N_SECURE_COOKIE=false`. A clean `docker compose up` on a public IP exposes the database, the mailbox, and the workflow editor.

**Cookies and CSRF.** The cookie is `atlas_session`, HttpOnly, `SameSite=Lax`, `Path=/`, with no `Domain`. Production refuses to start unless `ATLAS_COOKIE_SECURE=true`. Browsers drop a `Secure` cookie on plain HTTP, so login looks like a failure. `localhost` and `127.0.0.1` are different sites. A page on the VPS public IP that calls `http://127.0.0.1:8000` calls the visitor's computer. CSRF is the `X-CSRF-Token` header checked against the server session. The proxy must forward that header, `Cookie`, and `Set-Cookie`.

**One origin.** A reverse proxy is not in the repo. Hosting Next.js on one registrable domain and the API on another will not send the Lax cookie on `fetch`. CORS cannot fix that.

**Streaming.** Assistant responses are `text/event-stream`. The proxy must flush immediately and allow more than `ATLAS_LLM_TIMEOUT_SECONDS` (120 seconds). A buffering proxy stalls the checking state until the whole answer exists, or cuts the stream.

**Client address.** Login limits use the TCP peer, not `X-Forwarded-For`. Behind one proxy every user shares the proxy's address. The default is 40 failures per address in 15 minutes, counted in that API process. One replica makes the counter real. It also means a shared lockout is possible. Do not run a second API to "spread" the limit. The counters would diverge.

**Webhooks.** Signatures are HMAC-SHA256 over `timestamp.idempotency_key.body`. The API allows 300 seconds of clock skew and 30 requests per minute per key, in memory. The secret is sealed with a key derived from `ATLAS_SECRET_KEY` and returned once. There is one key per organization and no overlap during rotation. n8n must be able to reach `ATLAS_PUBLIC_API_URL`. Use `http://api:8000` on the Compose network. A public URL often fails from a container because hairpin NAT is not reliable.

**Email.** Sandbox mode cannot be pointed at a public SMTP server. That is intentional. Live email needs `ATLAS_EMAIL_MODE=live` and `ATLAS_EMAIL_LIVE_ENABLED=true`, and an admin approval still gates the send. Leave both off.

**Demo flag.** `ATLAS_PUBLIC_DEMO=true` refuses the Groq key and the n8n URL. Staging that exercises chat and workflows must not set it. Do not publish the seeded admin password.

**Process model.** Do not scale the API. Do not add a worker from the same image. Restarting the only API marks an accepted n8n run `needs_attention` until the callback arrives. That is expected.

**Supply chain.** Images are built on the server from the git revision you check out. Pin the VPS to `d336d1a` or a later reviewed commit. n8n is pinned to `1.70.3`. The follow-up workflow needs `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` and `NODE_FUNCTION_ALLOW_BUILTIN=crypto`, which Compose already sets. Do not bump n8n until those workflows are retested.

**Backups.** A volume on the same disk is not a backup. Lose the disk and you lose Postgres, uploads, trained artifacts, and n8n. Lose `ATLAS_SECRET_KEY` and the webhook secrets in the dump cannot be opened. Test a restore before calling staging ready.

**What this audit did not do.** No host was created, no DNS was changed, no certificate was issued, and no third-party account was opened.

## Estimated costs

Prices below are public list prices checked on 2026-11-22 and 2026-11-23. They exclude VAT. Recheck them before purchasing. Model spend for a small staging tenant is noise next to the host.

### Recommended: one VPS

| Item | Approximate monthly cost |
| --- | --- |
| Hetzner CX33, 4 vCPU, 8 GB RAM, 80 GB, EU, IPv4 included | €8.99 |
| Optional weekly snapshot or off-site backup storage | €1–3 |
| Domain name, amortized | about €1 |
| Groq chat, light staging use | €0 on the free tier, or a few euros |
| Ollama embeddings on the same VPS | €0 |
| OpenAI embeddings, only if Ollama is skipped | well under €1 at $0.02 / million tokens |
| n8n Community Edition and Mailpit on the VPS | €0 |
| **Typical total** | **about €12–15** |

A 4 GB CX23 at €5.99 is cheaper and is the wrong first host: image builds and the combined footprint are likely to run out of memory. A US Hetzner plan costs more than the EU CX33. A DigitalOcean or similar 8 GB VPS is usually several times the Hetzner price for the same job.

Operator load: you own SSH, Docker, the firewall, certificate renewal, backups, and n8n upgrades. Caddy renews certificates by itself. There is one bill and one network.

### Managed split

| Item | Approximate monthly cost | Staging problem |
| --- | --- | --- |
| Vercel or similar for Next.js | €0–20 | The browser bundle still calls whatever origin was baked in. A `*.vercel.app` page calling Render or Railway is a different site, so the Lax cookie is not sent. |
| Render web service, 1 CPU / 2 GB, for the API | $25 plus a $0–25 workspace | 2 GB is the smallest size that can hold this API. Persistent disk is extra ($0.25 / GB). One replica must be enforced by hand. |
| Render Postgres, 1 GB–2 GB | $19–40 | Confirm `CREATE EXTENSION vector` on the plan before relying on it. |
| Neon Launch, always-on small compute | about $15 typical, free tier is 100 CU-hours | pgvector is available. Scale-to-zero pauses the database and fails `/ready` until it wakes. LangGraph checkpoint setup uses `CREATE INDEX CONCURRENTLY`. |
| Railway Hobby | $5 plus usage above $5 | RAM at $10 / GB-month and CPU at $20 / vCPU-month. The same containers are often $40–80 once they stay up. |
| n8n Cloud Starter | €20 billed annually | Separate from the API network. The callback URL, the encryption key, and the webhook secret become another system to lock down. Self-hosting avoids this bill. |
| **Split total** | **about €50–120** | More bills, and login still needs a same-origin proxy you would have to add. |

Managed hosting reduces patching and provides hosted backups on the paid database plans. It does not remove the single-replica rule, the Mailpit hostname allowlist, the baked web URL, or the same-origin cookie. Those are why the first staging environment should be one VPS. Move Postgres to Neon or Render later if you want point-in-time recovery and you have already proven the proxy.

## Deployment blockers

Phase 1 closes the browser-login, volume-ownership, and published-port gaps for the staging Compose file. The local development Compose file still publishes Postgres, n8n, and Mailpit. That file is for a developer machine.

### Closed in Phase 1

- The staging web image does not call `127.0.0.1:8000`. Caddy terminates HTTPS and forwards `/api` unchanged.
- The API process runs as uid 10001 and can create files on the upload and model volumes.
- Staging secrets are required from `infrastructure/staging/.env`. There is no `atlas`/`atlas` default and no placeholder n8n key in the staging file.

### Still open

1. **No public host.** The local proof is `https://atlas.localhost:8443` with Caddy's CA. Let's Encrypt is what Caddy will use when `STAGING_HOST` is a real DNS name and ports 80 and 443 are published. No VPS, DNS record, or firewall has been created.
2. **Accounts and n8n are still a manual bootstrap.** Production refuses the seed. The smoke script seeds in `development`, then switches the API to `production`. n8n still does not import `infrastructure/n8n/*.json`, and the follow-up signer still needs the one-time webhook secret in `STAGING_HOOK_KEY_ID` and `STAGING_HOOK_SECRET`.
3. **Embeddings and chat are not live.** Ollama is on the private network, and the model `nomic-embed-text` is not pulled. No Groq key is stored. Upload and grounded answers still return unconfigured or unavailable until those are set. There is no backup job and no image registry. Login limits still see Caddy's address, not the browser's.

### Further gaps, after the three above

- Compose does not give the API service `host.docker.internal`. An Ollama process on the host is unreachable with the file as written.
- `.env.example` sets `ATLAS_PUBLIC_API_URL` to `http://host.docker.internal:8000`. If that file is copied as-is, n8n callbacks use the published host port instead of `http://api:8000`.
- Health checks ignore Groq, embeddings, disk, n8n, and Mailpit.
- There is no backup job, no deploy workflow, and no image registry.
- Login rate limits treat the proxy as the client.
- The 0.45 citation distance was measured for `nomic-embed-text`. An OpenAI 1536 index needs that threshold remeasured before citation quality is trusted.
- Building both images on a 4 GB VPS can exhaust memory. Use 8 GB, or build on CI and pull.

## What the development Compose file still does on a clean server

This list is `docker compose up` using `infrastructure/compose.yaml`, not the staging file. Checked out at `d336d1a`, with Docker installed and `.env.example` copied to `.env`:

1. `docker compose up -d` starts Postgres, the API, Mailpit, and n8n. It does not start Next.js.
2. Postgres initializes `atlas` and also creates `atlas_test` and `atlas_migration_test` from `infrastructure/postgres/init/01-databases.sql`. Those extra databases are harmless and are not needed in staging.
3. The API runs `alembic upgrade head` against `pgvector/pgvector:pg17`. That part can succeed. Uvicorn then serves `/api/v1/ready`.
4. The API image entrypoint gives the upload and model directories to uid 10001, then starts uvicorn as that user. An image built before that entrypoint still leaves fresh volumes root-owned.
5. The embedding provider is OpenAI with an empty key, so ingestion returns `embedding_unconfigured`. Groq is not selected. Ollama is not installed.
6. n8n starts with the placeholder encryption key, an empty workflow database, and a published editor. The lead webhook path does not exist until someone imports the JSON.
7. Mailpit accepts sandbox mail and its UI is published.
8. Postgres is published with password `atlas`.
9. Nothing listens on 443. A production-mode restart with the example secret fails closed, which is correct, and leaves no site to open.
10. No user exists, because the seed was not run and production would refuse it.

The local Windows workflow in the README avoids several of these failures because the API and Next.js run on the host, Ollama runs on the host, and the ports are bound for a developer machine. That workflow is not what a clean server runs.

## Step-by-step implementation plan

Phase 1 added the staging Compose file, Caddy, the same-origin web build, and the volume entrypoint. The remaining steps are the host, the model, n8n import, and backups. Do not point this at a purchased server until those are done.

1. **Reserve the name.** Register a hostname and point an A record at the VPS. Pick an EU Hetzner CX33 or another amd64 plan with 8 GB RAM. Add an SSH key. Enable the firewall for 22, 80, and 443 before Compose starts.
2. **Prepare the host.** Install Docker Engine and the Compose plugin, turn on NTP and unattended security updates, and create a deploy user that can run Docker. Clone the repository and check out the reviewed commit.
3. **Write secrets.** Create a root-owned `.env` from the table above. Generate `ATLAS_SECRET_KEY`, `POSTGRES_PASSWORD`, and `N8N_ENCRYPTION_KEY` before any container starts. Set `ATLAS_PUBLIC_API_URL=http://api:8000` and `ATLAS_N8N_LEAD_WEBHOOK_URL=http://n8n:5678/webhook/atlas-lead`. Leave the Groq key and the webhook secret empty until the steps that need them.
4. **Publish only Caddy.** `infrastructure/compose.staging.yaml` already keeps Postgres, n8n, Mailpit, Ollama, and the API off the host. On the VPS set `STAGING_HTTP_PORT=80` and `STAGING_HTTPS_PORT=443`. Add `extra_hosts` for the API only if Ollama stays on the host instead of the Compose service.
5. **Confirm the volumes.** The API entrypoint gives `/var/lib/atlas/storage` and `/var/lib/atlas/models` to uid 10001. Confirm with a file create, not only with `/ready`.
6. **Point Caddy at the public name.** The Caddyfile already routes `/api` unchanged to `api:8000` and every other path to `web:3000`, with no response buffering and 180 second proxy timeouts. Set `STAGING_HOST` to the public name so Caddy requests a Let's Encrypt certificate.
7. **Use the staging web image as built.** `NEXT_PUBLIC_API_URL=same-origin` is already the staging build argument. Do not bake the public hostname into the image.
8. **Install the embedding model.** Install Ollama on the host or as a private Compose service. Run `ollama pull nomic-embed-text`. Point the API at it with dimensions 768. Skip this step only if the OpenAI 1536 alternative was chosen on purpose.
9. **Bootstrap accounts once.** Start Postgres and the API with `ATLAS_ENVIRONMENT=development` and the staging passwords. Run `python -m app.scripts.seed` inside the API container. Confirm the three users exist. Switch `ATLAS_ENVIRONMENT` to `production`, set `ATLAS_COOKIE_SECURE=true`, and recreate the API container. Do not run the seed again. It resets those passwords and it will refuse production.
10. **Set the Groq key** in `.env` and recreate the API. Confirm provider status from a logged-in session. The status payload must not contain the key.
11. **Import n8n.** Create the n8n owner through an SSH tunnel to port 5678. Import `infrastructure/n8n/lead-processing.json` and `infrastructure/n8n/follow-up.json` and activate them. In ATLAS, create the organization webhook key. Put the id and the one-time secret into `ATLAS_HOOK_KEY_ID` and `ATLAS_HOOK_SECRET`. Recreate n8n so the follow-up signer sees them. Store the secret in the password manager. It is not shown again.
12. **Prove the product path.** From a browser that is not on the VPS: log in as admin, upload a text file and see it reach `ready`, ask a question that cites it, start an agent run, approve a customer response, and read that message in Mailpit through the SSH tunnel. Create a lead and confirm the n8n execution calls `http://api:8000/api/v1/hooks/lead-processed` and the workflow run completes. Repeat one approval to confirm the idempotency key does not send a second email.
13. **Back up and restore.** Take a `pg_dump`, copy the upload and model volumes, and store the two encryption keys separately. Restore onto a second data directory or a scratch volume and open a document. A backup that has never been restored is not a backup.
14. **Leave the public demo flag off.** Keep live email off. Keep the calendar in simulation. Keep a single API replica.

After that, staging is ready to use. Production hosting, a container registry, and moving Postgres to a managed service are later decisions and are out of scope for this cut.
