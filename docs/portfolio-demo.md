# Portfolio demo

Harbor & Co. is fictional. This command fills a separate database with that account so a visitor deployment can use the real CRM, inbox, knowledge, workflow, campaign, and assistant models. It does not run against the development database, and it was not run against the database on this machine.

The public website can also open a short-lived visitor session in the API the process is already using. That path is described in [demo-access.md](demo-access.md). It does not publish a password and it does not sign the visitor into Atlas Demo.

## What it writes

The command calls the existing development seed, then adds demonstration rows for Atlas Demo:

- Lumen Freight and Jonah Ellis, beside Harbor & Co. and Mina Patel.
- An opportunity, tasks, and a discovery note on the North pier lead.
- An email thread with an unsent draft, and a website-chat thread.
- A pending text note, `Bonded warehousing overview`, stored outside the active upload directory. The isolated API indexes it on startup. No ingestion job is queued in the development process.
- An inactive workflow, `qualified-lead-follow-up`, and one completed historical run. The definition does not dispatch.
- A draft campaign in sandbox mode, with consent recorded for Mina. No delivery row is queued.
- An assistant conversation about bonded-yard capacity, without a fabricated citation.
- A completed inquiry run with a rejected customer response and a simulated appointment. The booking provider is `simulation` and it has no external event id. The rejected response has no execution intent.

Northwind keeps only its own seed rows. New demonstration CRM rows use `demo` origin. Several workspace lists default to operational records, so the visitor chooses Demo or All records.

The organization stays on the Free plan until a confirmed subscription changes it: 2 seats, 100 assistant requests, 1 GB of knowledge files, and 2 active workflows. The staff membership cannot approve an external action.

## Refusals

The command exits before it connects when any of these are true:

- `ATLAS_PORTFOLIO_DEMO` is not `apply`.
- `ATLAS_PORTFOLIO_DATABASE_URL` is not a database named `atlas_portfolio`.
- The process is production or `ATLAS_PUBLIC_DEMO=true`.
- Email is live, campaigns are live, WhatsApp is live, or an n8n URL is set.
- The chat or embedding provider is not `double`, or either API key is set.
- Billing is Stripe or a Stripe secret is set.
- A Google Calendar client secret is set.
- `ATLAS_PORTFOLIO_STORAGE_DIR` is empty or sits inside the active upload directory.

Passwords are not printed. Integration credentials are not copied. The command does not create the database and does not delete existing rows. Running it again updates the same demonstration records in place.

Create the empty database and apply migrations with `ALEMBIC_DATABASE_URL` pointed at `atlas_portfolio` for that process only. Leave the development `.env` database URL unchanged.

Set the overrides in the process so they take precedence over `.env`. Use the `SEED_*` values already present for local development. Replace the database user, password, and storage path with the local ones. Do not point either URL at the development database.

```powershell
$env:ATLAS_PORTFOLIO_DEMO = "apply"
$env:ATLAS_PORTFOLIO_DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@127.0.0.1:5434/atlas_portfolio"
$env:ATLAS_PORTFOLIO_STORAGE_DIR = "D:\ATLAS\var\portfolio-storage"
$env:ATLAS_ENVIRONMENT = "development"
$env:ATLAS_PUBLIC_DEMO = "false"
$env:ATLAS_LLM_PROVIDER = "double"
$env:ATLAS_LLM_API_KEY = ""
$env:ATLAS_EMBEDDING_PROVIDER = "double"
$env:ATLAS_EMBEDDING_API_KEY = ""
$env:ATLAS_EMAIL_MODE = "sandbox"
$env:ATLAS_EMAIL_LIVE_ENABLED = "false"
$env:ATLAS_CAMPAIGN_LIVE_ENABLED = "false"
$env:ATLAS_WHATSAPP_LIVE_ENABLED = "false"
$env:ATLAS_N8N_LEAD_WEBHOOK_URL = ""
$env:ATLAS_BILLING_PROVIDER = "sandbox"
$env:ATLAS_STRIPE_SECRET_KEY = ""
$env:ATLAS_GOOGLE_CALENDAR_CLIENT_SECRET = ""
uv run --project apps/api python -m app.scripts.portfolio_demo
```

Start the API for that database with the same sandbox overrides, `ATLAS_PUBLIC_DEMO=true`, and `ATLAS_STORAGE_DIR` set to the portfolio storage directory. Do not start it on the ports of the running development API. Visitors enter through Launch interactive demo, which creates its own short-lived organization. Do not give them the staff or administrator password. The development workspace can hold provider credentials and is not the public demo.

Login failures stay limited per email and per client address inside each API process. Webhook calls stay limited per integration key. This command does not change those limits.
