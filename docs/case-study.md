# Case study

Harbor & Co. is fictional. The problem is not. A consulting team keeps inquiries in a mailbox, company facts in a shared drive, and follow-up in a CRM that nobody updates the same way. A model that can draft the follow-up is useful only if a person still decides what gets written, and only if the draft is tied to the right customer.

## Engineering problem

The system has to keep one organization's documents and CRM rows away from another, let a model read them, and stop before an email, a booking, or a CRM change. It also has to be explainable on a laptop: one API, one web app, and Postgres, with n8n outside the process.

## What was built

The API loads the membership for the session user and treats the organization id in the URL as a lookup key. Documents are chunked, embedded, and searched with vector distance plus full text. The assistant cites those rows or CRM records and refuses when nothing matches. The agent runs in LangGraph, calls three read-only MCP tools bound to the current organization, and stores proposed actions. An admin approves, then a separate execute step writes the stored payload. If the payload changed, execute does nothing. n8n receives a signed webhook only after that point. Email defaults to a local sandbox. The calendar adapter only simulates a booking. Lead scores come from a model trained on a synthetic set, and the explanation follows the model that produced the label.

## What was verified

The API suite covers tenant isolation, CSRF, approval integrity, webhook authentication, ingestion recovery, and the rule that an uncertain email is not sent twice. A Playwright test signs in, creates CRM records, uploads a document, asks the assistant, runs the agent, executes one approval, rejects another, and signs out. That browser run uses deterministic providers. Docker images for the API and the web app build locally. No public URL was created.

Live model calls and Langfuse export were not verified, because those credentials are not configured. The deterministic evaluation is a regression check, not a measure of a hosted model.

## Decisions that should stay

External side effects wait for a person. The model does not approve itself and does not pick the organization. Failed logins share one error and are limited inside the process. A public demo cannot hold a paid model key or an n8n URL. Seeding resets development passwords, so it does not run in production or in that demo.

## Limits

Login limits and webhook limits are not shared across processes. Rotating `ATLAS_SECRET_KEY` signs everyone out and retires sealed webhook secrets. Model files are still loaded with `joblib` from the model directory. The lead score is a synthetic demonstration. Exactly-once delivery to n8n or SMTP is not promised. A missing callback stays visible until it arrives. This write-up is not a penetration test or a compliance certificate.
