# Public portfolio deployment

This is the public Upwork demonstration: one fictional workspace a visitor can open in a browser. It is not the customer production stack in [production.md](production.md). No server, domain, or paid account was purchased for this procedure.

The public website and the signed-in application stay on one origin. Caddy sends `/api` and `/api/*` to the API and every other path to the Next.js app. That app is the replacement client in `apps/web-rebuild`. The image is built with `ATLAS_PUBLIC_SITE=1`, so `/` is the presentation, `/demo` and `/case-study` explain the session, and `/login` opens the workspace. Do not put the website on a second host. The session cookie is HttpOnly and SameSite=Lax, and a browser will not send it across sites. The earlier client in `apps/web` is not the image this file builds.

## Configuration the website session already requires

These rules come from the current application and from `docs/portfolio-demo.md`. This deployment does not change them.

- The serving process sets `ATLAS_PUBLIC_DEMO=true`. That process refuses the workspace model key (`ATLAS_LLM_API_KEY`), a workspace embedding key, live email, and an n8n URL. The public Groq key is a different variable, `ATLAS_PUBLIC_LLM_API_KEY`, and it is not read until `ATLAS_PUBLIC_LLM_AUTHORIZED` and `ATLAS_PUBLIC_INFERENCE_ENABLED` are both true.
- Visitor chat uses Groq `openai/gpt-oss-20b` only after that explicit authorization. Until then the visitor stays on the deterministic stand-in. A non-visitor cannot obtain the public client. The portfolio file leaves both switches false and the public key empty. Preflight rejects a public key that appears before authorization, and it rejects a public key that matches the workspace key.
- Visitor document search fits a latent semantic model on that visitor's own chunks. It does not call a paid embedding API unless `ATLAS_PUBLIC_EMBEDDING_AUTHORIZED` is set, which this file leaves false. The workspace chat provider remains `double`, so `ATLAS_ENVIRONMENT` stays `development`. Caddy answers `/docs`, `/openapi.json`, and `/redoc` with 404.
- Budgets are stored in Postgres and survive a restart. A visitor session may receive 8 replies. The process may receive 200 in an hour, 500 in a UTC day, and 4,000 in a UTC month. Token caps and a $5 monthly spend cap fail closed. Replies wait at least 2 seconds, at most 2 run at once, and each reply is capped at 256 tokens. Input over 2,000 characters, a repeated-character run, more than three links, or a prompt-injection pattern is rejected before a provider is called. An administrator of a non-visitor organization can set the kill switch at `POST /api/v1/organizations/{organization_id}/public-inference`. A visitor cannot. If the ledger cannot be read, the call is refused.
- The prepared records are written only by `python -m app.scripts.portfolio_demo`, only into a database named `atlas_portfolio`, and only from a one-off process with `ATLAS_PUBLIC_DEMO=false`. The serving process refuses that command.
- The one-off writes the knowledge file outside its own upload directory. The serving process mounts that directory as `ATLAS_STORAGE_DIR`, so the API can index the file after it restarts.
- Public entry is `POST /api/v1/demo/sessions` from Launch interactive demo. That session is a separate organization. The seeded staff account remains an operator login and cannot approve an external action. Do not publish the administrator or staff password.
- Visitor assistant answers call Groq only when the public key is authorized. Retrieval for that visitor uses the in-process semantic vectors at the configured width, fitted on that organization alone. Nothing is sent to Groq or OpenAI while the switches stay false. A non-visitor on this process still cannot call an external model.
- The seeded organization stays on the Free plan until a confirmed subscription changes it: 2 seats, 100 assistant requests, 1 GB of knowledge files, and 2 active workflows. This stack also caps a model response at 256 tokens and an upload at 2 MiB.
- Login failures are limited to 5 per email and 120 per client address inside the one API process, over 15 minutes. Demo launches are limited to 8 per direct client address per 15 minutes, and to 40 active visitor organizations. Behind Caddy every visitor shares Caddy's address, so the per-email login limit is the one that isolates an account, and the launch limit is shared by the whole site. A client-supplied forwarded address does not open another bucket. Webhook calls are limited to 10 per key per minute. Do not run a second API container. The counters are not shared, and a second process would recover the same rows.

Do not set `ATLAS_ENVIRONMENT=production` on this file. Production rejects the deterministic workspace chat provider. Visitor retrieval no longer needs that stand-in, but the signed-in workspace on this stack still does.

`PORTFOLIO_ENVIRONMENT=development` is the public process mode. The controls that a production process would enforce are still set on this stack:

- `ATLAS_COOKIE_SECURE` is true. The session cookie is HttpOnly and SameSite=Lax. Preflight refuses a public stack that turns the secure flag off.
- Caddy is the only published listener. It redirects HTTP to HTTPS and sends `Strict-Transport-Security` when the host is not localhost. The API, Postgres, and Mailpit have no host port.
- Caddy answers `/docs`, `/openapi.json`, and `/redoc` with 404. The API process also leaves those routes unmounted while `ATLAS_PUBLIC_DEMO` is true, so the schema is not available on the Compose network either.
- An unexpected exception returns `internal_error` with the message "An unexpected error occurred". The response and the log line do not include the exception text.
- `ATLAS_PUBLIC_DEMO=true` refuses a Harbor model key, a Harbor embedding key, live email, and an n8n URL. The seed command refuses to run in that process. Public inference stays off until both authorization switches are true, and preflight rejects a public key before that.
- State-changing requests still require the CSRF token issued for the session.

Development mode remains visible in the API configuration because the workspace chat provider is the deterministic stand-in. It does not publish the schema, weaken the cookie, or open a provider.

## What this stack leaves out

| Production service | Portfolio |
| --- | --- |
| Caddy | Kept. The only published ports. |
| Web and one API | Kept. Same-origin `/api/v1`. |
| PostgreSQL `atlas_portfolio` | Kept. 512 MB. The development database is not mounted. |
| Mailpit | Kept private, capped at 200 messages. Sandbox SMTP stays on the Compose network. |
| n8n | Omitted. A public demo cannot call it. |
| Ollama | Omitted. Local generation is not part of this stack. |
| Groq | Optional and off. `openai/gpt-oss-20b` is called only when the public key is authorized. Stripe, WhatsApp, and Google Calendar stay empty. |
| Off-host backup bucket, registry, Redis, GPU | Omitted. |

Memory limits are 64 MB for Caddy, 384 MB for the web app, 768 MB for the API, 512 MB for PostgreSQL, and 64 MB for Mailpit. That is 1,792 MB of container limits.

Use one amd64 Ubuntu LTS virtual machine with 2 vCPU, 4 GB RAM, and 40 GB disk. Do not add a GPU. Do not point this stack at the development database, `atlas_harbor`, or the Harbor upload directory. The earlier 8 GB recommendation was for the rejected local chat model. The measurement is in [Lean host](#lean-host).

## Install the host

Run these on the new machine. They install Docker Engine and the Compose plugin, turn on NTP, and allow only SSH, HTTP, and HTTPS.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git python3
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$USER"
sudo timedatectl set-ntp true
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

Open a new shell so the docker group applies. Confirm `docker compose version` prints a version.

## DNS

Create one A record from the public hostname to the server's IPv4 address. Add an AAAA record only when the server has a reachable IPv6 address. Wait until `getent hosts that-name` on the server returns the server's own address. Caddy requests the certificate when the stack starts. Ports 80 and 443 must be the published ports, or the HTTP-01 challenge cannot finish.

## Secrets

On the server, generate three values and store them in a password manager. Do not commit them.

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Run that three times. Use the first as `PORTFOLIO_SECRET_KEY`, the second as the value after `demo-01=`, and the third as `PORTFOLIO_POSTGRES_PASSWORD`. The database password must be letters and digits only. `token_hex` already is.

```bash
cp infrastructure/portfolio/.env.example infrastructure/portfolio/.env
```

Edit `infrastructure/portfolio/.env`:

- Replace the three generated values.
- Set `PORTFOLIO_HOST` to the public hostname.
- Set `PORTFOLIO_HTTP_PORT=80` and `PORTFOLIO_HTTPS_PORT=443`.
- Set `PORTFOLIO_CORS_ORIGINS` and `PORTFOLIO_CAMPAIGN_PUBLIC_URL` to `https://` plus that hostname, with no path and no port.
- Leave `PORTFOLIO_ENVIRONMENT=development` and `PORTFOLIO_PUBLIC_DEMO=true`.
- Leave `PORTFOLIO_PUBLIC_INFERENCE_ENABLED=false`, `PORTFOLIO_PUBLIC_LLM_AUTHORIZED=false`, and `PORTFOLIO_PUBLIC_LLM_API_KEY` empty.
- Leave the workspace provider, Stripe, and Google values empty.

The seed passwords do not go in this file. Export them in the shell only when you run the record command below. Use the same seed identity already used for local development. Do not invent a second set, and do not print the export lines into a log.

Check the file before starting. A failing check prints the rule and does not print the secret.

```bash
python3 infrastructure/portfolio/preflight.py --env-file infrastructure/portfolio/.env
python3 infrastructure/portfolio/compose_contract.py
```

## Deploy

```bash
sh infrastructure/portfolio/up.sh
```

The script runs the same checks, then builds and starts project `atlas-portfolio`. Caddy is the only service with a published port. PostgreSQL and Mailpit have none.

Write the fictional records after the API is healthy. This command is a one-off. It does not leave `ATLAS_PUBLIC_DEMO=false` on the serving process. It restarts the API so the pending knowledge note is indexed.

```bash
export SEED_ADMIN_EMAIL="the-existing-admin-email"
export SEED_ADMIN_PASSWORD="the-existing-admin-password"
export SEED_ADMIN_NAME="the-existing-admin-name"
export SEED_STAFF_EMAIL="the-existing-staff-email"
export SEED_STAFF_PASSWORD="the-existing-staff-password"
export SEED_STAFF_NAME="the-existing-staff-name"
export SEED_OUTSIDER_EMAIL="the-existing-northwind-email"
export SEED_OUTSIDER_PASSWORD="the-existing-northwind-password"
export SEED_OUTSIDER_NAME="the-existing-northwind-name"
python3 infrastructure/portfolio/apply_demo.py
unset SEED_ADMIN_PASSWORD SEED_STAFF_PASSWORD SEED_OUTSIDER_PASSWORD
```

Visitors use Launch interactive demo on the public site. That writes a short-lived Harbor & Co. organization into `atlas_portfolio` and sets an HttpOnly cookie for 45 minutes. Do not share the administrator or staff password. The public pages do not contain either password. Sign in remains the path for those accounts, and a visitor session cannot open them.

## What the interactive session can do

A visitor can open overview, CRM, inbox, knowledge, the assistant, workflows, analytics, campaigns, and approvals. The records are Harbor & Co., including the enterprise library and the fictional customer accounts. Assistant replies stay on the deterministic stand-in until the public Groq key is authorized. Document search for that visitor uses the in-process semantic index. The private Harbor review, including its verified provider connections, is not this database and is not opened by Launch interactive demo.

Restart deletes that visitor organization and opens another. Expired visitor organizations are removed when a later launch runs. Cleanup deletes a slug only when it starts with `harbor-visitor-`. Atlas Demo, Northwind, and any other slug stay, including one that merely begins with `harbor-`. The visitor address cannot sign in or reset a password.

Integration configuration, billing checkout, invitations, webhook keys, Google Calendar connect, campaign scheduling, and an n8n call return a refusal. A queued visitor delivery is skipped. Approval execution of a message or an appointment is refused before it is staged. The compose file leaves paid provider keys empty. `ATLAS_PUBLIC_DEMO=true` refuses to start if a paid model key, live email, or an n8n URL is added.

The release smoke test does not call the launch route. That route writes a visitor organization. Smoke confirms the origin, the health routes, and a failed login.

## Update

On the server, from the repository checkout:

```bash
sh infrastructure/portfolio/update.sh
```

That fast-forwards the git checkout and runs `up.sh` again. It rebuilds the images and recreates the containers. The named volumes, including `atlas_portfolio` and the knowledge files, stay in place. Do not run it against the development checkout on a workstation that is already using project `atlas`.

## HTTPS

Replace `HOST` with the public hostname.

```bash
curl -fsS "https://HOST/api/v1/health"
curl -sS -o /dev/null -w "%{http_code}\n" "https://HOST/api/v1/ready"
curl -sS -o /dev/null -w "%{http_code}\n" "https://HOST/demo"
curl -sS -o /dev/null -w "%{http_code}\n" "https://HOST/case-study"
curl -sS -o /dev/null -w "%{http_code}\n" "https://HOST/login"
curl -sS -o /dev/null -w "%{http_code}\n" "https://HOST/api/v1/auth/me"
curl -sS -o /dev/null -w "%{http_code}\n" "https://HOST/docs"
curl -sI "http://HOST/" | head -n 5
```

Expect `status` of `ok` from health, 200 from ready and the public pages, 401 from `/api/v1/auth/me`, 404 from `/docs`, and a 308 redirect from HTTP to HTTPS. The certificate line from `curl -v` should name the public hostname.

## Release smoke test

The same checks, including the security headers and a failed login that must not set a session cookie:

```bash
python3 infrastructure/portfolio/smoke.py --base-url "https://HOST"
```

The command prints `{"ok": true, ...}` and exits 0. It does not sign in and it does not write a row. On a `*.localhost` proof, pass `--ca` with Caddy's local root and `--http-url` with the published HTTP port. A public name on port 443 does not need either.

## Restore the demo records

Backup and restore accept only project `atlas-portfolio`, or a disposable project whose name starts with `atlas-portfolio-proof`. They refuse `atlas`, `atlas-staging`, and `atlas-production`.

```bash
python3 infrastructure/portfolio/backup.py backup --archive infrastructure/portfolio/backups/atlas-portfolio.tar.gz
python3 infrastructure/portfolio/backup.py restore --archive infrastructure/portfolio/backups/atlas-portfolio.tar.gz
```

The archive holds a custom-format dump of `atlas_portfolio` and the knowledge files. It does not hold the env file, a provider key, or another project's volume. The restore stops the portfolio API and web containers, replaces that database and those files, and starts them again. Keep the archive on the server. It contains password hashes for the fictional accounts.

To show the records again after a disposable change, restore that archive. Do not point the command at the development database, and do not run `portfolio_demo` against it. The command refuses any database name other than `atlas_portfolio`.

## Local proof

From the repository root, on a machine that is not the public server:

```bash
python infrastructure/portfolio/prove.py
python infrastructure/production/prove_stack.py
```

`prove.py` starts project `atlas-portfolio-proof` on unused high ports, runs the smoke test through Caddy, writes the fictional records, restores them after a rename, and deletes that project. `prove_stack.py` starts the full production Compose file as `atlas-prod-stack-proof`, with volume names that cannot replace a real production volume, and deletes it. Neither command stops the development or staging containers.

The result files are `var/portfolio-proof/result.json` and `var/production-stack-proof/result.json`. They are not committed.

## Lean host

Measured on 27 November 2026 after the local generation service was removed.

The visitor library is 54 documents and about 61 KB of source text. Fitting the in-process semantic space on those documents and projecting one question took 919 ms on this workstation, including the first import of the numeric library. A later question refits the same small matrix. PostgreSQL full text remains part of the answerable retrieval path. No GPU is required. CPU is idle except during that fit and during a Groq call, and a Groq call does not run until it is authorized.

The 27 November portfolio proof, which still loaded `llama3.2:1b`, measured the other containers without the model: the API about 217 MiB, the web app 38 MiB, Postgres 71 MiB, Caddy 15 MiB, and Mailpit 5 MiB. That is about 350 MiB resident. Ollama's 1.65 GiB is no longer part of the stack. The compose limits now add up to 1,792 MB, so the host needs room for those limits plus the operating system.

Minimum reliable specification: one amd64 Ubuntu LTS machine, 2 shared vCPU, 4 GB RAM, 40 GB disk. Ports 22, 80, and 443 only. A 2 GB machine can hold the measured resident set and then fail when a container reaches its limit. Do not add a GPU.

Published Hetzner list prices checked on 10 November 2026 put the orderable CX23 (2 vCPU, 4 GB RAM, 40 GB NVMe, 20 TB traffic) at €5.49 per month net in Germany, before VAT. A primary IPv4 is billed separately, about €0.50 per month net. A hostname and its DNS record are not included. With public inference left off, Groq cost is $0. If it is later authorized, the fail-closed ceiling is $5 per UTC month. At the published Groq rates recorded for `openai/gpt-oss-20b` on 27 November 2026 ($0.075 per million input tokens and $0.30 per million output tokens), the 4,000-reply monthly cap is under $1 at the reserved token hold. The $5 cap stops the process before that hold can be exceeded.

## What was verified on this machine

On 27 November 2026, `python infrastructure/portfolio/prove.py` built `apps/web-rebuild` and project `atlas-portfolio-proof` on `127.0.0.1:19380` and `:19343`. The result in `var/portfolio-proof/result.json` is not committed. Nothing was published, and no host, domain, or paid account was purchased.

That run reported preflight, compose up, and Caddy healthy. The smoke list was empty: the public home page, `/demo`, `/case-study`, `/login`, and `/portfolio/01-overview.png` were served; `/api/v1/health` and `/api/v1/ready` came from the API; `/api/v1/auth/me` and a failed login returned 401 without a session cookie; `/docs`, `/openapi.json`, and `/redoc` returned 404; HTTP redirected to HTTPS. Postgres, Mailpit, Ollama, the API, and the web app published no host ports. Caddy, web, API, Postgres, Mailpit, and Ollama became healthy. The one-shot model pull exited successfully before the API started. The proof wrote the fictional records, indexed `Bonded warehousing overview` to ready, restored the archive after a rename, and kept Harbor & Co. inside Atlas Demo. It then deleted that project. Containers whose names start with `atlas-` were not replaced. The private Harbor API on port 8014 stayed up.

A second boot of the same project measured the loaded model and the visitor session. With `llama3.2:1b` resident, Ollama used 1.65 GiB of its 1.75 GiB limit. The API used about 217 MiB, the web app 38 MiB, Postgres 71 MiB, Caddy 15 MiB, and Mailpit 5 MiB. That is about 2.0 GiB resident. The compose limits of that revision added up to 3.8 GiB. That host size was for the rejected local model. The current file's host is the lean host above.

The same boot launched a visitor organization. It received 20 stored companies, `demo` was true, and the slug started with `harbor-visitor-`. A request for Atlas Demo's companies returned 404. Integration configuration and billing checkout returned 403. An immediate second assistant message was stored as "Wait before sending another message". After eight model replies the next message was stored as "This chat has reached its reply limit". Expiring the session made `/api/v1/auth/me` return 401, and the next launch deleted that visitor organization.

`llama3.2:1b` is not an acceptable public assistant. On the same questions, the private Harbor assistant using Groq `openai/gpt-oss-20b` answered a greeting, the pallet arithmetic (4 full pallets and 18 cases), and an exact three-line instruction in 1.1 to 2.2 seconds. The local model invented a company, missed the three-line instruction, and either refused or mis-stated the same arithmetic when asked directly. Inside the public stack the arithmetic happened to be right in 5.2 seconds, and a document question whose search was ready still abstained. A company question returned "No companies are stored" in about 0.05 seconds on both the public stack and Harbor, so that miss is the catalog planner, not the model client.

The public Groq path now exists and stays off. `ATLAS_PUBLIC_DEMO=true` still refuses the workspace key. The public key is a separate variable, and preflight accepts it only when authorization and public inference are both true. Published Groq rates for `openai/gpt-oss-20b` on 27 November 2026 were $0.075 per million input tokens and $0.30 per million output tokens. At 200 replies an hour and 256 output tokens, a full hour is a few cents. The monthly spend cap is $5. Leave the switches false until that key is accepted.

An earlier production-stack proof, not repeated for this revision, used project `atlas-prod-stack-proof` on `127.0.0.1:19480` and `:19443`, with volume names that cannot replace a real production volume. The full file started: Caddy, web, API, PostgreSQL, Mailpit, n8n, and Ollama. Ollama became healthy, the embedding provision container exited successfully, and Caddy became healthy only after the API and web app were healthy. n8n was still running when the proof removed the project. The same smoke checks passed. No `atlas-` container was replaced, and the only volumes removed were the proof volumes.

