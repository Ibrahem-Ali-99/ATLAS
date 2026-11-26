# Case study

Harbor & Co. is fictional. The operational problem is not. A team keeps inquiries in a mailbox, company facts in a shared drive, and follow-up in a CRM that people update differently. A draft is useful when it is tied to the right customer and when a person still chooses what gets written, booked, or changed.

The public page for this write-up is `/case-study`.

## Business problem

The system has to keep one organization's documents and CRM rows away from another, let a model read them, and stop before an email, a booking, or a CRM change. It also has to run as one API, one web app, and PostgreSQL, with n8n outside the process when an operator configures it.

## Product capabilities

Identity uses Argon2 passwords, HttpOnly server-backed sessions, CSRF, tenant roles, invitations, and email password reset. CRM covers companies, contacts, leads, inquiries, opportunities, and tasks. Inbox covers signed email, WhatsApp, and website chat, with assignment and handoff.

Knowledge ingests PDF and text. The assistant answers with citations or a stored refusal. Conversations belong to the user who created them. Inquiry runs propose actions and pause. An administrator approves or rejects. Execute writes the stored payload, or does nothing if that payload changed.

Workflows are a visual definition with all or any conditions, two ordered paths, manual runs, human review, activation, pause, and run inspection. Campaigns use segments, consent, suppression, a pinned transport, unsubscribe links, and recipient-level delivery feedback. Billing has a Free plan and Stripe test prices for Starter ($19 monthly or $190 yearly), Pro ($49 or $490), and Business ($99 or $990). Entitlements follow a confirmed provider event. Free includes 2 seats, 100 assistant requests, 1 GB of knowledge files, and 2 active workflows.

## System architecture

The web client is Next.js App Router, React, TypeScript, Tailwind, Radix UI, and TanStack Query. The API is a Python 3.12 FastAPI modular monolith using Pydantic, SQLAlchemy, Alembic, PostgreSQL, and pgvector. LangGraph coordinates inquiry processing. Domain services own the business rules. Routes validate the contract and call the service. A read-only MCP process supplies scoped CRM and knowledge context. Ingestion, workflow recovery, and training run inside the one API process.

```text
Browser → Next.js → FastAPI → PostgreSQL
FastAPI → sandbox SMTP
FastAPI → n8n, when a webhook URL is configured
```

## Engineering decisions

External side effects wait for a person. The model does not approve itself and does not choose the organization. Failed logins share one error and are limited inside the process. A public demo cannot hold a paid model key, live email, or an n8n URL. Seeding resets development passwords, so it does not run in production or in that demo. Provider keys that are empty fail closed. The deterministic provider is a stand-in for tests and a public demo, not a measure of a hosted model.

An isolated visitor database is prepared with `app.scripts.portfolio_demo`, described in [portfolio-demo.md](portfolio-demo.md). That command refuses the development database.

## Intelligent retrieval

Documents are chunked with page numbers when the extractor provides them. Embeddings are stored at 1536 or 768 dimensions, matching the configured model. Search uses cosine distance plus Postgres full text, and it only returns chunks from the caller's organization. The default maximum cosine distance is 0.55. A neighbor becomes model context when it shares a content word with the query, or when a vector-only neighbor is at or below distance 0.45. Rank alone does not put a neighbor into that context.

A stored citation is a row that contains a number, code, email, or distinctive word the answer states. The model does not choose the stored ids. A specific fact that appears in none of the supplied rows is replaced, in the stored message, with a sentence that the fact could not be confirmed. When retrieved rows are present, the server checks the completed draft before the client renders it. If neither documents nor CRM records match, the assistant stores a refusal and does not call the model.

## Workflow execution

```text
Inquiry → LangGraph → MCP reads → stored proposal → admin decision → CRM write or sandbox action
```

The MCP tools are `find_contact`, `get_lead`, and `search_company_knowledge`. They do not accept an organization id and they do not write.

A lead create or update commits the CRM row and the executed approval in one transaction. A customer response or appointment first stores an execution intent with a stable idempotency key. One worker claims it. Sandbox SMTP uses the local mailbox. A timeout becomes needs attention and is not sent again. A refused connection can be tried twice. The calendar adapter in simulation mode writes a booking row and no provider event id. This is at-least-once delivery with reconciliation. It is not an exactly-once guarantee.

Visual definitions can match all or any conditions and then follow the matching path or the otherwise path. The selected branch is stored before approval. A manual request cannot be reused for a different record. n8n receives a signed webhook only after the approval point for the lead path, and a missing callback stays visible until it arrives.

## External integrations

Workspace credentials are encrypted. Connection tests and disconnect are explicit. Google Calendar uses session-bound single-use state and PKCE, checks availability again at execution, and records the owning calendar so cancellation targets that event. WhatsApp verifies signed inbound messages. Approved outbound replies use a separate live gate. Resend can record delivery, bounce, and complaint, with suppression on bounce and complaint. Stripe checkout does not change entitlements until the webhook confirms the subscription. Webhook signing secrets are sealed and returned once.

## Multi-tenant security

A session cookie identifies the user. Organization access is loaded from memberships. Roles are admin and staff. Mutations other than login require the CSRF token issued for that server session. Retrieval, CRM, knowledge, assistant, agent, and approval routes require the membership. Approving or rejecting requires admin. Uploaded documents, retrieved passages, and model output are treated as data.

Record origin is operational, demo, evaluation, or unknown, stored on the row. An organization is not itself one of those kinds. Analytics and several lists default to operational rows. The local seed writes new demonstration rows as demo.

## Testing and reliability

API tests cover tenant isolation, CSRF, approval integrity, webhook authentication, ingestion recovery, and the rule that an uncertain email is not sent twice. Browser acceptance walks CRM, knowledge, the assistant, an agent run, one executed approval, and one rejection. That browser path uses the deterministic providers. Login limits default to 8 failures per email and 40 per direct client address inside 15 minutes. Webhook limits default to 30 requests per minute for each integration key. Both counters live in the API process that received the request.

Lead scoring trains on a documented synthetic set. A stored prediction is advisory. It does not change the lead, create an approval, or authorize an external action. The score is not a measurement of real conversion.

## Deployment

Production is one API process and one Next.js app behind one browser origin. The session cookie is HttpOnly and SameSite=Lax, and CSRF expects the browser to call the API that issued the token. PostgreSQL with pgvector holds the rows. Uploads live on a persistent disk. Staging HTTPS is served by Caddy. Migrations run before traffic. A second copy of the API would recover the same rows, so ingestion and workflow recovery stay in the one API process.

A shared demo sets the public-demo flag. The process then refuses to start with a paid model key, live email, or an n8n webhook URL. Anonymous requests still need a session.

## Limits

Login limits and webhook limits are not shared across processes. Rotating the session secret signs everyone out and retires sealed webhook secrets. Exactly-once delivery to n8n or SMTP is not promised. Direct edits made in Google Calendar are not imported. This write-up is not a penetration test or a compliance certificate.
