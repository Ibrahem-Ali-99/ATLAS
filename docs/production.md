# Production deployment

ATLAS production is one Linux host running Docker Compose. Caddy is the only process with a public port. The API and the web app share that HTTPS origin. PostgreSQL, n8n, Mailpit, and Ollama stay on the private Compose network.

No server, DNS record, certificate, or paid account was created for this procedure. The checks below were run on disposable containers.

## Environments

| Environment | Compose file | Project | Env file | Published ports |
| --- | --- | --- | --- | --- |
| Development | `infrastructure/compose.yaml` | `atlas` | repository `.env` | Postgres, API, Mailpit, and n8n on the developer machine |
| Staging | `infrastructure/compose.staging.yaml` | `atlas-staging` | `infrastructure/staging/.env` | Caddy only |
| Production | `infrastructure/compose.production.yaml` | `atlas-production` | `infrastructure/production/.env` | Caddy only |
| Public portfolio | `infrastructure/compose.portfolio.yaml` | `atlas-portfolio` | `infrastructure/portfolio/.env` | Caddy only |

The portfolio stack is the public demonstration. Its procedure is in [portfolio-deployment.md](portfolio-deployment.md). It is not a smaller copy of this production file: it does not run n8n or Ollama, and it keeps the deterministic provider behind the public-demo flag.

Each project uses its own volumes. A production command must not use the development, staging, or portfolio project. Restore refuses `atlas`, `atlas-staging`, and `atlas-production`. The portfolio backup refuses those names as well and only accepts `atlas-portfolio`.

Development may keep local passwords. Production Compose has no password default. `infrastructure/production/up.sh` runs the preflight and the Compose contract before it starts containers. The checked-in `.env.example` is rejected by that preflight.

## Minimum host

One amd64 virtual machine is enough. Use 4 vCPU, 8 GB RAM, and 80 GB disk. Ubuntu LTS, Docker Engine, and the Compose plugin are the only host packages. NTP must be on, because webhook signatures expire outside 300 seconds of clock skew.

The production Compose file limits memory so one container cannot consume the host:

| Service | Limit |
| --- | --- |
| PostgreSQL | 1024 MB |
| API | 1536 MB |
| Ollama | 1280 MB |
| n8n | 768 MB |
| Web | 512 MB |
| Embedding provision | 512 MB |
| Caddy | 128 MB |
| Mailpit | 128 MB |

That is about 5.4 GB for the long-running services. The rest is for the operating system and for building an image. Do not run a second API container. Training, ingestion, workflow recovery, and checkpoint setup run in the one API process.

A Hetzner CX33-class machine in the EU was listed at about €8.99 per month before VAT in November 2026, with IPv4 included. A domain name is about €1 per month when the yearly price is spread out. Optional off-host backup storage is about €1–7 if an S3-compatible bucket is added later. Groq's free tier covers light chat use. Ollama on the same machine serves `nomic-embed-text:v1.5` at 768 dimensions, so embeddings do not need a paid API. n8n Community Edition and Mailpit add no license fee.

Do not start with a 4 GB machine for this production file. Image builds and the combined footprint are too tight. The public portfolio demonstration does not use this file; its smaller host is described in [portfolio-deployment.md](portfolio-deployment.md). Do not add Redis, a queue, a container registry, or a managed database for the first boot. The host builds from the git checkout. A registry can wait until builds on the server become the slow step.

```text
Browser
  |  HTTPS :443
  v
Caddy (Let's Encrypt for a public name, local CA for *.localhost)
  |-- /api/*  --> api:8000     one replica, migrations before uvicorn
  |-- /*      --> web:3000     same-origin /api/v1
                    |
                    v
             postgres:5432     private, pgvector
             n8n:5678          private, workflows imported inactive
             mailpit:1025      private sandbox mailbox
             ollama:11434      nomic-embed-text:v1.5
```

Outbound calls, when configured, are Groq for chat and Let's Encrypt for certificates. Email stays in Mailpit until a live SMTP host is accepted. Stripe live keys are rejected.

## First boot

1. Install Docker Engine and the Compose plugin. Enable NTP and unattended security updates. Allow inbound TCP 22, 80, and 443 only.
2. Clone the repository and check out the reviewed commit. The production files in this tree are the ones to use.
3. Copy `infrastructure/production/.env.example` to `infrastructure/production/.env`. Generate unique values for the session secret, the credential keyring, the Postgres password, and the n8n encryption key. The Postgres password must be at least 32 letters or digits so it can sit in the database URL without escaping. Store the same values in a password manager. The backup archive does not contain this file.
4. For a public name, set `PRODUCTION_HOST` to that name, `PRODUCTION_HTTP_PORT=80`, `PRODUCTION_HTTPS_PORT=443`, and set `PRODUCTION_CORS_ORIGINS` and `PRODUCTION_CAMPAIGN_PUBLIC_URL` to `https://` plus that name. A `*.localhost` name may use the high ports in the example.
5. Leave billing in `sandbox`, email in `sandbox`, and WhatsApp live mode false. Set the chat provider to `groq` or `openai` and put the key only in the env file.
6. Run the gate. It prints the failing rule and does not print secret values.

```bash
python3 infrastructure/production/preflight.py --env-file infrastructure/production/.env
python3 infrastructure/production/compose_contract.py
python3 infrastructure/production/migrate.py --check
```

7. Start the stack. The shell script runs the same gate again.

```bash
sh infrastructure/production/up.sh
```

8. Create the first administrator on stdin. A second run is refused and does not replace the password.

```bash
docker compose --project-name atlas-production --project-directory infrastructure \
  -f infrastructure/compose.production.yaml --env-file infrastructure/production/.env \
  exec -T -u atlas api python -m app.scripts.bootstrap
```

9. Confirm `python -m app.scripts.bootstrap --status` and `GET /api/v1/ready` through Caddy. Import n8n workflows with `infrastructure/staging/provision_n8n.py` only after pointing it at the production project, and leave them inactive until the webhook key exists. Reach the n8n editor through an SSH tunnel. Do not publish port 5678.

Startup order is Postgres healthy, Mailpit healthy, Ollama healthy, the embedding provision exited 0, then the API. The web container waits for API `/api/v1/ready`. Caddy waits until the web and API health checks pass.

## Security

Production startup rejects a placeholder session secret, a missing credential keyring, `ATLAS_COOKIE_SECURE=false`, and a `double` provider. The Compose file hardcodes `ATLAS_ENVIRONMENT=production`, `ATLAS_COOKIE_SECURE=true`, and `ATLAS_PUBLIC_DEMO=false`. The preflight also rejects:

- a Postgres password of `atlas`, `password`, or the database user
- HTTP CORS origins and a CORS list that omits the site origin
- a public hostname that is not published on ports 80 and 443
- an embedding URL of `127.0.0.1` or `localhost` inside the container
- `DEBUG` logs
- `sk_live_` and `rk_live_` Stripe keys
- `PRODUCTION_WHATSAPP_LIVE_ENABLED=true`
- live email aimed at Mailpit, and sandbox email aimed at a public SMTP host

Caddy forwards `/api` unchanged, flushes streamed responses, and allows 180 seconds for a model response. It sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Content-Security-Policy: frame-ancestors 'none'`, and a locked-down `Permissions-Policy`. It removes the `Server` header. API responses are `Cache-Control: no-store`. `Strict-Transport-Security` is set only when the hostname is not `localhost`, `*.localhost`, or `127.0.0.1`, so a local proof does not pin HSTS.

Login limits still use the TCP peer. Behind Caddy that peer is Caddy, so the address limit is shared by every visitor of the one API process. Do not add a second API process to split the counter. The proxy does not turn on forwarded headers.

The session cookie is HttpOnly and `SameSite=Lax`. The browser must call the API on the same origin that set the cookie. Hosting the web app on one site and the API on another will not send the cookie.

## Logs and health

Each service uses the json-file driver with a 10 MB cap and five files. The API writes structured request logs and keeps `/health` and `/ready` at debug. `GET /api/v1/health` does not touch the database. `GET /api/v1/ready` checks the database. A green ready check does not mean Groq, Ollama, or n8n accepted a call.

```bash
python3 infrastructure/production/health.py --project atlas-production --env-file infrastructure/production/.env
docker compose --project-name atlas-production --project-directory infrastructure \
  -f infrastructure/compose.production.yaml --env-file infrastructure/production/.env logs --tail 100 api
```

The health command only reads `docker compose ps`. It does not restart containers.

## Backup

Install the timer on the production host. It runs at 02:40 UTC, which is offset from the staging timer so the two do not share a unit name.

```bash
sudo install -m 600 infrastructure/production/backup.env.example /etc/atlas/production-backup.env
sudo cp infrastructure/production/atlas-production-backup.service /etc/systemd/system/
sudo cp infrastructure/production/atlas-production-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now atlas-production-backup.timer
```

Edit the env file before enabling the timer. The passphrase must be random and must not be the placeholder. An empty passphrase is refused. Fourteen archives are kept. The archive contains a custom-format `pg_dump` of each database, globals without role passwords, and tar files of uploads, model artifacts, and the n8n data directory. It does not contain Ollama weights, Mailpit mail, Caddy certificates, or the Compose env file. n8n is stopped only while its files are archived. Postgres stays up.

Keep these outside the archive: `PRODUCTION_SECRET_KEY`, `PRODUCTION_CREDENTIAL_ENCRYPTION_KEYS`, `PRODUCTION_POSTGRES_PASSWORD`, `PRODUCTION_N8N_ENCRYPTION_KEY`, and `ATLAS_BACKUP_PASSPHRASE`. Losing the session secret makes sealed webhook secrets unreadable. Losing the n8n key makes stored n8n credentials unreadable.

Optional S3 upload uses the same rules as staging and is skipped when `ATLAS_BACKUP_S3_URI` is empty. Do not buy a bucket until a restore has been rehearsed.

## Restore

Restore onto a new Compose project, never onto `atlas-production`.

```bash
python3 infrastructure/production/restore.py \
  --project atlas-production-restore \
  --env-file infrastructure/production/.env \
  --archive /var/backups/atlas/atlas-YYYYMMDDTHHMMSSZ.tar.gz.enc
```

The command decrypts the archive, checks every SHA-256, loads each dump with `pg_restore`, and extracts uploads, models, and n8n into fresh volumes. Start that project only after the command prints `restore_ok`. Sign in, open a restored document, and confirm n8n still opens with the original encryption key. A different key must not decrypt stored credentials.

A local disposable proof is:

```bash
uv run --project apps/api --frozen python infrastructure/production/drill_restore.py
```

It uses project `atlas-prod-drill`, a loopback database port, and removes its own containers and volumes. It does not attach to `atlas` or `atlas-staging`.

## Migrations

The API entrypoint runs `alembic upgrade head` and then one uvicorn worker. That is the normal upgrade path. Before a deploy that includes a new revision:

1. Take a backup and confirm `backup_ok`.
2. Run `python3 infrastructure/production/migrate.py --check`.
3. Recreate the API container so the entrypoint applies the new head.
4. Confirm `/api/v1/ready`.

To undo one reversible revision, stop traffic and run `alembic downgrade -1` once inside the API container. Do not start a second API process while the database is at the older revision, because the entrypoint would upgrade it again.

`python3 infrastructure/production/migrate.py --plan` prints this procedure and lists revisions whose downgrade cannot remove a PostgreSQL enum value. Those revisions need a backup restore, not a walk backward through `alembic downgrade`. The current manual revision is `20261123_0015`.

## Incident recovery

| Situation | What to do |
| --- | --- |
| API container restarts | One replica comes back and runs `alembic upgrade head`. In-flight work that was accepted by n8n stays `needs_attention` until the callback arrives. |
| `/api/v1/ready` fails | Read the API log. If Postgres is unhealthy, do not delete the volume. Restore only onto a new project. |
| A migration fails during boot | The old container is already stopped. Restore the backup taken before the deploy onto a new project. Do not run a second downgrade if the plan marked the revision manual. |
| Disk loss | Provision a new host, restore `/etc/atlas/production-backup.env` and `infrastructure/production/.env` from the password manager, and restore the newest archive onto a new project. Caddy requests a new certificate. The embedding provision pulls `nomic-embed-text:v1.5` again. |
| Session secret lost | Webhook secrets in the database cannot be opened. Create a new key after setting a new `PRODUCTION_SECRET_KEY`. Everyone is signed out. |
| n8n encryption key lost | Workflow credentials in the n8n volume cannot be opened. Restore the volume and the original key together. |
| Certificate error | For a public name, confirm ports 80 and 443 reach Caddy and the DNS A record matches the host. Caddy renews Let's Encrypt certificates. Local names use Caddy's CA. |
| Bad deploy of the app | Check out the previous git revision, rebuild, and recreate the API and web containers. If the new revision migrated the database, follow the migration plan before recreating the API. |

## Verification on this machine

These checks did not restart the development or staging containers.

- Production Compose config renders with the example env file.
- The example env file is rejected by preflight, and the failure text does not contain the placeholder.
- `migrate.py --check` reported head `20261126_0055`, 55 revisions, and manual downgrade `20261123_0015`.
- `drill_restore.py` started the production Postgres service with no host port, rolled the schema back one revision and forward again, encrypted a logical dump plus an upload, destroyed those volumes, restored them, and matched the row, the revision, and the upload SHA-256. The running `atlas` and `atlas-staging` containers kept the same ids and start times.
- The API image build dropped from 275008082 bytes to 182834263 bytes by leaving the installer in the build stage. The process is one uvicorn worker and the image has a `/api/v1/ready` health check.
- The web image context fell from about 1.5 GB of local `.next*` caches to 14 MB. The built image is 80700563 bytes, runs as user `atlas`, and has a `/login` health check. `NEXT_PUBLIC_API_URL=same-origin`.
- `drill_proxy.py` verified the Caddy file on disposable containers. `https://proof.example` with an internal certificate returned the API path unchanged, set the security headers including HSTS, and hid the `Server` header. `https://atlas.localhost` set the same headers without HSTS. Plain HTTP returned 308. The Caddy admin health command succeeded. The running development and staging containers were unchanged.
- `prove_startup.py` ran the new API image with `no-new-privileges`. A placeholder secret, `ATLAS_COOKIE_SECURE=false`, and `ATLAS_LLM_PROVIDER=double` each exited before serving. A valid production configuration became healthy, dropped to uid 10001, returned 200 from `/api/v1/ready` and `/api/v1/health`, and returned 404 from `/docs`.

The drill reports under `var/production-drill/` are local and are not committed.

## Remaining external prerequisites

These are not done here, and nothing was purchased.

1. A public amd64 host, a DNS A record, and a firewall that allows 22, 80, and 443.
2. A password-manager copy of the production env file and the backup passphrase.
3. A Groq or OpenAI chat key placed only in `infrastructure/production/.env`.
4. The first administrator password, supplied on stdin to bootstrap and not written into the image.
5. An n8n owner created through an SSH tunnel, then an organization webhook key, before either workflow is activated.
6. Let's Encrypt will issue the certificate when the public name and ports 80 and 443 are in place. This machine used Caddy's local CA.
7. Live email, live WhatsApp, Google Calendar, and Stripe remain outside this boot. Stripe live keys are rejected. Test-mode Stripe keys can be set only after the billing procedure in `docs/stripe-test-mode.md` is accepted.
8. An off-host bucket is optional. Leave `ATLAS_BACKUP_S3_URI` empty until a restore onto a second host has been rehearsed.
9. Login rate limits still see Caddy's address. One API replica is required anyway.
10. A container registry is optional. The host can build from git.
