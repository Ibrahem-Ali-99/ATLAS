# Harbor & Co. demonstration data

Harbor & Co. is fictional. The interactive demo writes this workspace into a visitor organization when `POST /api/v1/demo/sessions` runs. Dashboards count those rows. They do not use a hardcoded total.

The same writer can fill a database named `atlas_harbor`. It refuses every other database, including the development database, `atlas_portfolio`, and `atlas_test`.

The public portfolio stack is a different database and a different web image. Do not point it at `atlas_harbor`, this password, or `var/harbor-storage`. Launch interactive demo must not be used against this review API. The connected providers stay on this private process.

## What is stored

| Records | Count | How they stay honest |
| --- | --- | --- |
| Companies | 20 | Origin `demo`. Two contacts each. |
| Contacts | 40 | Example email addresses only. |
| Leads | 50 | New, contacted, qualified, unqualified, won, and lost. |
| Opportunities | 30 | Stages match the pipeline. USD and EUR stay in separate totals. |
| Conversations | 40 | Inbound messages plus an unsent draft. |
| Tasks | 35 | Open, completed, and cancelled, with past and future due dates. |
| Appointments | 20 | Provider `simulation`. No external event id. |
| Service notes | 15 | Ready text, deterministic embeddings, one passage each. |
| Workflows | 8 | Inactive, with completed runs that say no message was sent. |
| Campaigns | 3 | One draft. Two recorded campaigns whose recipient status is `simulated`. |
| Approvals | Pending and historical | A rejected reply says no message was sent. Executing a customer message or a new appointment is still refused in a visitor session. |
| Evaluation questions | 5 | The same yard facts as the service notes, plus one handoff and one missing-fact question. |

Activity is spread over about 120 days. A 90-day analytics range therefore reads stored rows. The prepared assistant reply cites the bonded-warehousing note.

## Visitor limits

Prepared documents do not count toward the visitor allowance of 3 files and 500 KB. The prepared assistant reply does not count toward the 12 replies. A file the visitor uploads, including one marked demo, counts. Workflows stay inactive so the free plan's 2 active workflows remain available. Forty visitor organizations at a time is still the process cap. Each library is about 15 short text files, so the set stays small on a low-cost host.

## Isolated database

Create an empty `atlas_harbor` database and run migrations against it. Then, from the repository root, with sandbox provider settings:

```powershell
$env:ATLAS_HARBOR_DEMO = "apply"
$env:ATLAS_HARBOR_DATABASE_URL = "postgresql+psycopg://atlas:atlas@127.0.0.1:5434/atlas_harbor"
$env:ATLAS_HARBOR_STORAGE_DIR = "D:\ATLAS\var\harbor-storage"
# Optional. The command does not print this value.
$env:ATLAS_HARBOR_PASSWORD = "choose-a-long-password"
uv run --project apps/api python -m app.scripts.harbor_demonstration
```

The storage directory must be outside the upload directory of the process that holds operational files. A sandbox API that should serve these documents uses `atlas_harbor` as its database and `ATLAS_HARBOR_STORAGE_DIR` as `ATLAS_STORAGE_DIR`. Sign-in is `harbor-showcase@harbor.example` only when the password was set. Leave live email, live campaigns, live WhatsApp, n8n, paid model keys, Stripe, and Google Calendar unset. Running the command again leaves an already complete workspace in place.

The interactive demo does not write this database. It writes a separate visitor organization in whatever database the API is already using, and that organization is deleted when the session ends.

## Connected providers

`app.scripts.harbor_operations` copies sealed grants from the operational workspace into `harbor-showcase` and then calls the providers. It does not copy companies, contacts, or messages. A grant is not treated as verified until that provider accepts a new request. Set `ATLAS_HARBOR_CONNECTIONS=apply` and `ATLAS_HARBOR_DATABASE_URL` to the `atlas_harbor` URL. The command refuses production, a public demo, live WhatsApp, live email, live campaigns, and a live Stripe key.

`app.scripts.harbor_journeys continue` finishes routes that are still open. It does not copy grants again. Public model replies are enabled only in that process, and the inference budgets still apply. The operational environment file is not changed.

n8n keeps `ATLAS_PUBLIC_API_URL` on the operational API. `ATLAS_LEAD_CALLBACK_ORIGINS` also allows the portfolio API on port 8012 and the Harbor listener on port 8013. A signed callback can complete a Harbor workflow without replacing either of those other callbacks. A workflow that already ended `callback_missing` stays that way. A later run dispatches one new workflow to the Harbor listener.

The Harbor review uses its own API and web process. Leave the API on port 8000 and the web app on port 3000 running. From `apps/api`, start the review API on port 8014 with `ATLAS_DATABASE_URL` pointed at `atlas_harbor`, `ATLAS_STORAGE_DIR` pointed at `ATLAS_HARBOR_STORAGE_DIR`, `ATLAS_SESSION_COOKIE_NAME=atlas_harbor_session`, `ATLAS_CORS_ORIGINS=http://127.0.0.1:3014`, and `ATLAS_PUBLIC_API_URL=http://127.0.0.1:8014`. Do not set the public-demo flag or the live send flags. From `apps/web`, start `npx next dev --hostname 127.0.0.1 --port 3014` with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8014` and `NEXT_DIST_DIR=.next-harbor`. Sign in as `harbor-showcase@harbor.example` only when that password was set. `app.scripts.harbor_review` prints the stored plan, verification, and Resend event. It does not call a provider.

WhatsApp inbound for the existing test number stays on the operational callback. The Cloud API has one callback URL per app, so pointing that URL at Harbor would replace the operational callback. A Harbor inbound demonstration needs a separate Meta app and test number whose callback is the Harbor API only. Renewing the existing token and saving it in Integrations does not change that callback. `app.scripts.harbor_stripe` starts a Harbor API and the Stripe CLI, completes Checkout with the official test card, and records the plan only after the signed webhook. The CLI signing secret stays in that process. The operational webhook secret is not replaced. Resend acceptance and a later `last_event` of `delivered` are stored as different facts. A restricted Resend key can accept a test and still be unable to read delivery events.

## Limitations

- The deterministic stand-in is not a hosted model. It returns the first line of the first retrieved passage. The bonded note starts with the north-pier sentence so that question returns that sentence. A citation is still a stored passage.
- The missing-fact evaluation question has no supporting passage. With the full CRM loaded, a later run can still ground on a CRM row. That is a retrieval result, not a bank or payroll fact. The library states that it does not hold card numbers or government identity numbers.
- Opportunities, tasks, inbox threads, and campaigns have no origin column. Choosing Operational hides prepared leads and companies in analytics, and those other lists stay visible.
- Recorded campaign totals are counts of `simulated` rows. They are not sandbox SMTP receipts and not a live provider result. Open and click events are not stored.
- A visitor can reject a prepared reply, and can approve then execute the prepared lead-note change. Executing a customer message or a new appointment returns `demo_restricted` and does not stage an intent.
- Scheduling a campaign, connecting a provider, inviting a teammate, and opening billing stay refused.
- This procedure was not run against the development database.

## Verified browser journey

`apps/web/e2e/harbor-demonstration.spec.ts` launches a visitor session on a disposable database. It checks overview and 90-day analytics totals, CRM search, company creation, inbox history, knowledge search, an assistant reply, rejecting a prepared customer message, refusing execution of another message, executing the prepared lead note and reading it back, workflow history and a preview run, and a campaign labeled simulated. Screenshots from that run are in `docs/demo/harbor/`.
