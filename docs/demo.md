# Demonstration

The story is Harbor & Co., a fictional logistics customer of Atlas Demo. Mina Patel asks about bonded warehousing. The records, the document, the agent proposal, and the approval all use that account. Northwind is a second organization used to show that its data stays hidden.

Reset the local database with:

```powershell
cd apps\api
uv run python -m app.scripts.seed
```

The command is idempotent. It resets the three development passwords and prints the emails, not the passwords. It refuses production and `ATLAS_PUBLIC_DEMO=true`. The example passwords live only in `.env.example`.

To clear stored agent runs, approvals, workflow rows, traces, and documents for the `atlas-demo` organization without changing passwords or CRM rows:

```powershell
cd apps\api
$env:ATLAS_ENVIRONMENT = "development"
$env:ATLAS_DEMO_RESET = "yes"
uv run python -m app.scripts.reset_demo
```

The command refuses any other environment, a public demo, and any database name outside `atlas`, `atlas_demo`, `atlas_e2e`, and `atlas_test`. Failed historical runs stay available until that command is used. It was not run against the current development database as part of this change.

## Modes

| Mode | What you are seeing |
| --- | --- |
| Local infrastructure | Postgres, the API, and the Next.js app on this machine. |
| Deterministic provider | `ATLAS_LLM_PROVIDER=double` and `ATLAS_EMBEDDING_PROVIDER=double`. Fixed text and hash embeddings. Not a live model. |
| Real provider | `openai` with a key in `.env`. Empty keys fail closed. This checkout has no key, so live verification is blocked. |
| Sandbox email | SMTP to Mailpit on port 1025. The mailbox UI is `http://127.0.0.1:8025`. |
| Simulated calendar | A row in ATLAS. No external calendar is booked. |

n8n on port 5678 is a local integration. The editor should stay on localhost. A public demo must leave `ATLAS_N8N_LEAD_WEBHOOK_URL` empty.

## Two-minute script

1. Sign in as the Atlas Demo admin. Overview shows the membership and the lead, inquiry, and approval counts from stored rows.
2. Open CRM. Harbor & Co. and the lead "North pier expansion" are the synthetic account. Northwind is not in this list.
3. Open Knowledge and upload a short text file that mentions bonded yards. Wait until the status is ready.
4. Open AI Assistant, start a conversation, and ask about bonded yards. With the deterministic provider the answer is the fixed grounded sentence and the citation is the uploaded file. With a real provider the wording comes from that provider and can be wrong. The citation is still a retrieved row, not a claim invented by the page.
5. Create an inquiry from Mina Patel about bonded storage rates. Start an agent run from that inquiry. The run stops at awaiting approval. No lead is written yet.
6. Open Approvals. Approve the lead update, then execute it. The North pier lead notes become the stored summary. Reject the customer-response proposal. Workflows stays on sandbox email and a simulated calendar, and the rejected action does not send mail.
7. Open Analytics and Monitoring. The figures are counts and traces already stored for Atlas Demo. A missing conversion rate stays empty instead of becoming zero.
8. Sign out from the account menu or from Settings.

An isolated visitor database, separate from this development workspace, is described in [portfolio-demo.md](portfolio-demo.md). The public tour is `/demo`. A short-lived session that opens Harbor & Co. inside the running application, without a published password, is described in [demo-access.md](demo-access.md).

The browser test in `apps/web/e2e/workspace.spec.ts` follows this path with deterministic providers and an isolated `atlas_e2e` database. Screenshots `01` through `13` are from that test server. The assistant image shows the fixed sentence `Grounded answer from the supplied company records.`, not a hosted model. The workflows image shows `n8n_not_configured` because that test process has an empty webhook URL. A local API with `ATLAS_N8N_LEAD_WEBHOOK_URL` set is a different mode. The Next.js development badge is visible on those shots. Screenshots `14` through `27` are from `next start` against the local development database and do not include that badge.
