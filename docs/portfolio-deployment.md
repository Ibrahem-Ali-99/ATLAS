# Public portfolio deployment

This is the public Upwork demonstration: one fictional workspace a visitor can open in a browser. It is not the customer production stack in [production.md](production.md). No server, domain, or paid account was purchased for this procedure.

The public website and the signed-in application stay on one origin. Caddy sends `/api` and `/api/*` to the API and every other path to the Next.js app. The website session already serves `/`, `/demo`, `/case-study`, and `/portfolio/*` from that app. Workspace pages such as `/overview` stay on the same origin. Do not put the website on a second host. The session cookie is HttpOnly and SameSite=Lax, and a browser will not send it across sites.

## Configuration the website session already requires

These rules come from the current application and from `docs/portfolio-demo.md`. This deployment does not change them.

- The serving process sets `ATLAS_PUBLIC_DEMO=true`. That process refuses a paid model key, live email, and an n8n URL.
- Production refuses the deterministic provider. A public demo refuses a paid chat key. Together, those two rules leave no chat provider that `ATLAS_ENVIRONMENT=production` will boot. The portfolio process therefore uses `ATLAS_ENVIRONMENT=development` with the public-demo flag. Caddy answers `/docs`, `/openapi.json`, and `/redoc` with 404, so the development schema is not on the public origin.
- The prepared records are written only by `python -m app.scripts.portfolio_demo`, only into a database named `atlas_portfolio`, and only from a one-off process with `ATLAS_PUBLIC_DEMO=false`. The serving process refuses that command.
- The one-off writes the knowledge file outside its own upload directory. The serving process mounts that directory as `ATLAS_STORAGE_DIR`, so the API can index the file after it restarts.
- The visitor account in the seed is staff and cannot approve an external action. Do not publish the administrator password.
- Assistant answers use the deterministic provider. The stored sentence is the fixed grounded sentence. Retrieval uses the in-process embedding at 1536 dimensions. Nothing is sent to Groq or OpenAI.
- The seeded organization stays on the Free plan until a confirmed subscription changes it: 2 seats, 100 assistant requests, 1 GB of knowledge files, and 2 active workflows. This stack also caps a model response at 256 tokens and an upload at 2 MiB.
- Login failures are limited to 5 per email and 120 per client address inside the one API process, over 15 minutes. Behind Caddy every visitor shares Caddy's address, so the per-email limit is the one that isolates an account. Webhook calls are limited to 10 per key per minute. Do not run a second API container. The counters are not shared, and a second process would recover the same rows.

If the application later accepts a keyless local chat model in production, the environment can move to production. Until that change exists, do not set `ATLAS_ENVIRONMENT=production` on this file. The API will not start.

## What this stack leaves out

| Production service | Portfolio |
| --- | --- |
| Caddy | Kept. The only published ports. |
| Web and one API | Kept. Same-origin `/api/v1`. |
| PostgreSQL `atlas_portfolio` | Kept. 512 MB. The development database is not mounted. |
| Mailpit | Kept private, capped at 200 messages. Sandbox SMTP stays on the Compose network. |
| n8n | Omitted. A public demo cannot call it. |
| Ollama and the embedding pull | Omitted. The deterministic embedding does not need a model download. |
| Groq, Stripe, WhatsApp, Google Calendar | Omitted. The compose file sets those keys empty. |
| Off-host backup bucket, registry, Redis, GPU | Omitted. |

Memory limits are 64 MB for Caddy, 384 MB for the web app, 768 MB for the API, 512 MB for PostgreSQL, and 64 MB for Mailpit. That is under 2 GB. The production file reserves about 5.4 GB because it also runs Ollama and n8n.

Use one amd64 Ubuntu LTS virtual machine with 2 vCPU, 4 GB RAM, and 40 GB disk. That is enough to build the images and run this stack. Do not rent the 4 vCPU / 8 GB production shape for the demonstration. Do not add a GPU.

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
- Leave the provider, Stripe, and Google values empty.

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

Share the staff password with a visitor only after this hostname is serving this stack. Do not share the administrator password. The public pages do not contain either password.

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

## What was verified on this machine

The portfolio proof used project `atlas-portfolio-proof` on `127.0.0.1:19380` and `:19343`. Caddy served the public home page, `/demo`, `/case-study`, `/login`, and the overview capture. `/api/v1/health` and `/api/v1/ready` came from the API. `/api/v1/auth/me` and a failed login returned 401 and did not set a session cookie. `/docs`, `/openapi.json`, and `/redoc` returned 404. HTTP redirected to HTTPS. Postgres, Mailpit, the API, and the web app published no host ports.

The same proof wrote the fictional Harbor & Co. records into `atlas_portfolio`, indexed `Bonded warehousing overview` to ready, renamed that company, restored the archive, and read the original company back inside Atlas Demo only. It then deleted that project. Containers whose names start with `atlas-` were still the same processes afterward.

The production proof used project `atlas-prod-stack-proof` on `127.0.0.1:19480` and `:19443`, with volume names that cannot replace a real production volume. The full file started: Caddy, web, API, PostgreSQL, Mailpit, n8n, and Ollama. Ollama became healthy, the embedding provision container exited successfully, and Caddy became healthy only after the API and web app were healthy. n8n was still running when the proof removed the project. The same smoke checks passed. No `atlas-` container was replaced, and the only volumes removed were the proof volumes.

