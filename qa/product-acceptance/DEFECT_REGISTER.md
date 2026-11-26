# ATLAS independent product acceptance

Run: 27 November 2026, evidence `var/product-acceptance/20261127-002201`. Isolated API `127.0.0.1:8097`, web `127.0.0.1:3097`, database `atlas_e2e_09aed2d579e5429fa45511a76605e7e7`. The shared API on port 8000 and the web app on port 3000 both returned 200 before and after the run. They were not restarted.

The acceptance process used the current workspace code with Groq for chat and local Ollama for embeddings. It forced sandbox billing, cleared Stripe credentials and the n8n dispatch URL, left live email, live campaigns, and live WhatsApp off, and pointed SMTP at a closed local port. No checkout was opened, no message was sent, and no charge was created.

Assistant prompts stay in `qa/product-acceptance/sealed/`. This register cites case ids and observed behavior. Re-run with `qa/product-acceptance/run.ps1`. The runner writes a machine copy to the evidence directory and does not replace this review.

The earlier run `var/product-acceptance/20261126-234403` did not approve the product. The defects from that run are closed below.

## Verdict

Approved for this isolated run. 35 workflow checks held. All 18 sealed assistant cases held. No material defect remained.

## What held

- CRM: a company, contact, lead, and inquiry were created; search and a notes edit survived a fresh read; the company total increased by one; a missing CSRF token was refused; the other organization received 404.
- Overview: New opportunity created `QA night-gate opportunity`, which was then visible on the pipeline.
- Knowledge: the acceptance note reached `ready`. A search for its unique phrase returned that note.
- Workflows: an inactive manual workflow was saved and listed. It was not activated.
- Campaigns: a draft with a subject and message was saved and was not scheduled. The delivery guidance no longer asks for a subject and message that are already stored. Schedule delivery stays disabled without an eligible audience.
- Analytics: the all-records company total matched the CRM total (2).
- Workspace search: the saved company appeared in Search workspace.
- Typography: the computed body font was Inter at 14px. The background remained `rgb(247, 248, 250)`.
- Inbox, Approvals, Agent Runs, Monitoring, Settings, and the listed routes opened for the administrator. Overview had no horizontal overflow at 390px.
- Agent run `63943f88-e910-4776-bc92-1885d5329214` paused at `awaiting_approval`. Staff approval returned 403. The administrator rejected the proposals. No email row was created.
- Assistant: 18 of 18 sealed cases held, including multi-step work, a document linked to a CRM contact, an ambiguous person, an approval before a booking or email, a refused direct send, recovery of the stored pallet count, and no leak of the other organization's companies.

## Closed defects

### QA-ASSIST-TASK — closed — Multi-step requests were searched as a literal lead title

The remainder of the instruction was used as the lead name, so the stored contact was missed and the document was not read. A turn now resolves a stored contact or lead inside the instruction, keeps the approval proposal, and attaches the related passage. Sealed case `multi-step-task` held.

### QA-ASSIST-CROSS — closed — A document person was not matched to CRM

An empty document search became a not-found answer. When a question connects a written source to a CRM contact, the assistant searches again and says whether that person is a contact in this workspace only. Sealed case `cross-module` held.

### QA-ASSIST-AMBIGUOUS — closed — A vague request about one person did not name the record

A request that names one stored person and does not ask for a fact now identifies that contact and lead and asks what to do. Sealed case `ambiguous` held.

### QA-ASSIST-TOOLS — closed — Booking and email were answered as a missing document

Those actions now prepare an appointment and a follow-up. Neither is sent. A question about an appointment already on file reports that none is stored. Sealed cases `tool-selection` and `appointment-scheduling` held.

### QA-ASSIST-LIMIT — closed — A provider rate limit failed the turn

Chat and embedding calls retry transient 429 and 503 responses, honor Retry-After up to eight seconds, and otherwise wait with exponential backoff and jitter. Permanent authorization failures are not retried. The retry wraps the provider call, so tools and proposals are not repeated. When attempts are exhausted and no stored evidence is available, the turn still returns `llm_rate_limited`. Sealed case `instruction-conflict` held.

### QA-SEARCH-RECORDS — closed — Workspace search listed pages only

Search workspace now queries companies, contacts, and leads for the signed-in organization and links each result to that CRM record.

### QA-CAMP-GUIDANCE — closed — A complete draft was described as missing its subject and message

The delivery note lists only the prerequisites that are actually missing. A saved subject and message with no eligible audience asks for recipients. Schedule delivery stays disabled, and this run did not send mail.

### QA-VIS-TYPE — closed — The shell used Segoe UI

The body font now uses the bundled Inter face. The computed family contains Inter. The background color was left at `#f7f8fa`.

## Integration classification

| Service | What was executed | Classification |
| --- | --- | --- |
| Groq chat | Assistant turns completed with the configured chat model. | Real provider. A later rate limit can still occur after the bounded retries. |
| Ollama embeddings | The acceptance note reached `ready` and search returned it. | Real local provider. |
| Email | Sandbox mode. Live send off. No email row was created. SMTP pointed at a closed port. | Local sandbox, not a delivered message. |
| Campaigns | Draft saved. Schedule was not called. | Unsent draft. |
| WhatsApp | No workspace credential. Live flag off. | Unconfigured. |
| Google Calendar | Deployment client can be present. This workspace was not connected. No booking was created. | Not a live booking. |
| n8n | Dispatch URL cleared on this process. | Not exercised. |
| Stripe | Billing mode was sandbox. No checkout and no charge. | Not called. |
