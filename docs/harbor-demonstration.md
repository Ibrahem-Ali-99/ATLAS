# Harbor & Co. demonstration data

Harbor & Co. is fictional. The interactive demo writes this workspace into a visitor organization when `POST /api/v1/demo/sessions` runs. Dashboards count those rows. They do not use a hardcoded total.

The same writer can fill a database named `atlas_harbor`. It refuses every other database, including the development database, `atlas_portfolio`, and `atlas_test`.

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
