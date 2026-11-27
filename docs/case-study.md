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

The public portfolio client is the replacement Next.js 16 app in `apps/web-rebuild`. The earlier client in `apps/web` remains the development application. The API is a Python 3.12 FastAPI modular monolith using Pydantic, SQLAlchemy, Alembic, PostgreSQL, and pgvector. LangGraph coordinates inquiry processing. Domain services own the business rules. Routes validate the contract and call the service. A read-only MCP process supplies scoped CRM and knowledge context. Ingestion, workflow recovery, and training run inside the one API process.

```text
Browser → Next.js → FastAPI → PostgreSQL
FastAPI → sandbox SMTP
FastAPI → n8n, when a webhook URL is configured
```

## Engineering decisions

External side effects wait for a person. The model does not approve itself and does not choose the organization. Failed logins share one error and are limited inside the process. A public demo cannot hold a paid model key, live email, or an n8n URL. Seeding resets development passwords, so it does not run in production or in that demo. Provider keys that are empty fail closed. The deterministic provider remains the stand-in for tests and for visitor document search. It is not a measure of a hosted model.

An isolated visitor database is prepared with `app.scripts.portfolio_demo`, described in [portfolio-demo.md](portfolio-demo.md). That command refuses every database name other than `atlas_portfolio`, including the development database and `atlas_harbor`.

## Intelligent retrieval

Documents are chunked at 800 characters with 100 characters of overlap. Page numbers are kept when the extractor provides them. Embeddings are stored at 1536 or 768 dimensions, matching the configured model. Search stays inside the caller's organization.

The assistant default is `answerable` in `apps/api/app/domains/knowledge/retrieval.py`. Candidate search is an AND full-text query, an OR full-text query, and vector neighbors inside the existing cosine cutoff, fused by reciprocal rank. A second stage keeps a passage only when the question's rare constraints occur together as positive mentions and the passage has the kind of fact asked for. A negated mention does not count. The 0.45 and 0.55 distance gates were not moved. Dense neighbors inside 0.45 are candidates, not answers. On local Ollama `nomic-embed-text:v1.5`, development hard negatives landed inside that gate and dense retrieval abstained on none of them. Answerability abstained on all four.

A stored citation is a row that contains a number, code, email, or distinctive word the answer states. The model does not choose the stored ids. `80000` and `80,000` are the same figure. `9` and `09` are the same clock component. `19` is not accepted as `9`. A specific fact that appears in none of the supplied rows is replaced, in the stored message, with a sentence that the fact could not be confirmed. If neither documents nor CRM records qualify, the assistant stores a refusal and does not call the model.

Anonymous website chat and a visitor Assistant session do not call a model unless `ATLAS_PUBLIC_INFERENCE_ENABLED` is true. The default is false. The portfolio stack can point chat at a keyless Ollama model on the private network. `llama3.2:1b` was measured on 27 November 2026 and is not an acceptable public assistant: it missed exact instructions and invented a company that had not been supplied. The private Harbor assistant on Groq `openai/gpt-oss-20b` answered the same greeting, arithmetic, and format instruction correctly in about 2 seconds. A public Groq path is not enabled. The budgets prepared for a visitor are 8 replies per session and 200 for the process inside one hour, a 2 second gap, 2 in flight, and 256 output tokens. An empty key is accepted only for a visitor and only for a loopback or `ollama` host. A public model host with an empty key is refused. A non-visitor on that process cannot obtain the client. Visitor document search stays on the deterministic stand-in, so a public question does not call a paid embedding API. The deterministic stand-in is not a measure of a hosted model.

## Retrieval evaluation

Recorded on 26 November 2026 after the answerable stage was frozen. The questions were not edited to raise these scores. Neither corpus is Harbor & Co. Both runs used hash embeddings and PostgreSQL full text on `atlas_test`, and the rows were rolled back. Ranked metrics use K = 5. Generation used Groq `openai/gpt-oss-20b`. The detail is in [assistant-rag-evaluation.md](assistant-rag-evaluation.md).

| Measure | Plover Dock | Orry Beacon | Target |
| --- | ---: | ---: | ---: |
| Recall@5 | 0.9286 | 0.8056 | 0.85 |
| Abstention accuracy | 0.8000 | 1.0000 | 0.90 |
| Factual correctness | 0.7143 | 0.5000 | 0.85 |
| Citation correctness | 0.7273 | 0.7222 | |
| Mean retrieval latency | 10.81 ms | 11.62 ms | |

Plover Dock is 45 questions. Recall cleared the target. Abstention and factual correctness did not. Orry Beacon is 26 questions scored afterward. It abstained on every unsupported question, and its factual correctness was 0.50. Public inference stayed off after both runs. Mean retrieval latency is the search itself and does not include the Groq call.

## Inquiry agent

An inquiry run is a LangGraph sequence. It loads the inquiry, classifies it with the configured chat model, then calls three read-only tools: `search_company_knowledge`, `find_contact`, and `get_lead`. Those tools do not accept an organization id and they do not write. The run stores a lead proposal, a reply draft, and an appointment request, then pauses. The model has no approval tool.

An administrator approves or rejects each stored payload. Execute writes that payload, or does nothing if it changed. A completed row with no stored steps is a recorded booking or proposal. It is not a successful language-model execution. Agent runs, monitoring, and workflow activity open on every stored origin so demonstration rows stay visible. An operator can narrow the list.

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

Record origin is operational, demo, evaluation, or unknown, stored on the row. An organization is not itself one of those kinds. Analytics can be narrowed to operational rows. Agent runs, monitoring, and workflow activity open on every stored origin so a demonstration workspace stays visible, and an operator can narrow them. The local seed writes new demonstration rows as demo.

## Testing and reliability

API tests cover tenant isolation, CSRF, approval integrity, webhook authentication, ingestion recovery, and the rule that an uncertain email is not sent twice. Browser acceptance walks CRM, knowledge, the assistant, an agent run, one executed approval, and one rejection. That browser path uses the deterministic providers. Login limits default to 8 failures per email and 40 per direct client address inside 15 minutes. Webhook limits default to 30 requests per minute for each integration key. Both counters live in the API process that received the request.

Lead scoring trains on a documented synthetic set. A stored prediction is advisory. It does not change the lead, create an approval, or authorize an external action. The score is not a measurement of real conversion.

## Release evidence

On 26 November 2026 the working tree that included `b71d0de` and the qualification fixes in `44631e1` was checked without restarting the shared API or web app.

| Check | Result |
| --- | --- |
| API | 284 passed, 1 skipped, 0 failed |
| Browser | 37 passed, 2 skipped, 0 failed |
| Frontend unit tests | 12 passed, 0 failed |
| TypeScript and production build | passed |

The API skip does not call Groq or Ollama. The browser skips are design screenshots and the Resend transport settings test. The runs used `atlas_test` and a disposable `atlas_e2e_*` database, sandbox billing, and sandbox mail. They did not send a message or create a charge. Alembic had one head, `20261126_0055`. Stripe test-mode checkout, the portal, upgrade, downgrade, cancellation, a declined card, and a failed renewal were recorded earlier that day and were not repeated. The tree also held uncommitted demo and deployment files, so these counts are not a clean checkout of `44631e1`. The clean command is `.\scripts\verify-release.ps1` in [release-checklist.md](release-checklist.md).

## Deployment

Production is one API process and one Next.js app behind one browser origin. The session cookie is HttpOnly and SameSite=Lax, and CSRF expects the browser to call the API that issued the token. PostgreSQL with pgvector holds the rows. Uploads live on a persistent disk. Staging HTTPS is served by Caddy. Migrations run before traffic. A second copy of the API would recover the same rows, so ingestion and workflow recovery stay in the one API process.

A shared demo sets the public-demo flag. The process then refuses to start with a paid model key, live email, or an n8n webhook URL. The public image is `apps/web-rebuild`. The connected provider demonstration stays on `atlas_harbor` and is not mounted by this stack. Anonymous requests still need a session.

## Limits

Login limits and webhook limits are not shared across processes. Rotating the session secret signs everyone out and retires sealed webhook secrets. Exactly-once delivery to n8n or SMTP is not promised. Direct edits made in Google Calendar are not imported. This write-up is not a penetration test or a compliance certificate.

Monitoring classifies a connection from the last stored verification and recent failed operations. It does not call the provider, send a message, create a booking, or start a payment. A fresh connection test still belongs to the integration session. Assistant executions list the stored request, tools, records, duration, and failure. They do not include the originating conversation, because that identifier is not on the execution response. A completed inquiry run with no stored model steps is labeled as a recorded row, not as a successful model execution. A new Harbor & Co. acceptance run waits until the assistant execution contract and the live connection checks are finished.
