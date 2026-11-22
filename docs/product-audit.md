# ATLAS product reality audit

Audited on 22 November 2026 against the running API at `127.0.0.1:8000` and the production web app at `127.0.0.1:3000`. The scenario evidence, the records that were created, and the corrective backlog are in `docs/product-acceptance.md`.

Status words:

- **Fully functional** — a person can finish the job in the product, and the stored result matches the screen.
- **Functional but sandboxed** — the job runs, and delivery is deliberately confined to a local or simulated adapter.
- **Partially functional** — a real path exists, and a business user still cannot finish the job.
- **Read-only** — the screen shows stored or configured facts and cannot change them.
- **Simulated** — the product stores a stand-in and does not call the external system the label might suggest.
- **Missing** — there is no user-facing way to do the job.
- **Broken** — the control exists and the live result is wrong or the job stops.

A passing test is not treated as a completed product. Deliberate safety limits are named separately from missing behavior.

## Feature matrix

| Feature | Status | What was verified | Persistence and integration | Limit |
|---|---|---|---|---|
| Sign in and sign out | Fully functional | Seeded admin signs in. A wrong password returns the server message. Logout returns 204 and the next session read returns 401. | `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `POST /api/v1/auth/logout`. Login is rate limited. Mutations other than login require `X-CSRF-Token`. | No signup, password reset, invite, or profile edit. That absence is deliberate. |
| Organizations | Partially functional | Every call uses the membership loaded on the server. A user from another organization receives 404 for this organization's company. | `GET /api/v1/organizations`. The client uses `memberships[0]`. | No switcher, create, rename, or invite. |
| CRM companies, contacts, leads, inquiries | Fully functional | Created a company, contact, inquiry, and lead, then set the lead to qualified. The records appear in CRM search and in analytics. | CRUD under `/api/v1/organizations/{id}/...`. Creating a lead also stages the n8n lead automation. | No assignment control in the UI. The lead owner stays the signed-in user. |
| Knowledge upload, index, and search | Fully functional | A text file reached `ready`. Search returned its excerpt. PDF and other types were not retested in this pass. | Upload, ingest, and search use the configured Ollama embedding model at 768 dimensions. | No folders or tags. A failed index remains a row. Changing the embedding width still requires a manual reindex. |
| Assistant | Partially functional | Capability, inventory, and company-list questions answer from stored rows and do not call the model. A document question called Groq and stated the fact in the uploaded file. A recall question quoted the prior turn. | Conversations and messages persist. Citations are retrieved rows, not phrases parsed from the answer. | The grounded answer also cited an unrelated brochure and CRM rows. See the acceptance backlog. |
| Agent runs | Broken | Three starts on the new inquiry classified it with Groq, then failed in `search_company_knowledge` with `tool_failed`. Older runs on this database have completed. | LangGraph still runs `load_inquiry → classify → retrieve_knowledge → lookup_customer → qualify → propose → await_approval → execute → record_outcome`. Reads go through MCP. The Groq key is not passed to the child. | The live path stops before a proposal. The stored message does not include the tool exception. |
| Approvals | Fully functional for an existing pending action; not reached for the new run | Staff approval of an existing pending action returned 403. The new run produced no proposal, so approve, reject, execute, and resume were not available. | Approve and reject require an admin and CSRF. Execute is a separate admin call. A second execute is rejected in the service as `already_executed`. | The proposal email recipient in code is `inbox@localhost`. The user cannot edit the payload. |
| n8n lead processing | Fully functional for the new lead | The new lead's workflow run is `completed` with one `succeeded` attempt. `completed` is written by the signed callback, after dispatch has only reached `accepted`. | `stage_lead_created` is idempotent per lead. n8n calls `POST /api/v1/hooks/lead-processed`. | The user cannot create, edit, trigger, or retry a workflow. One older run remains `needs_attention`. |
| Follow-up automation | Partially functional | The installed card is visible. This scenario did not call the follow-up hook, and the card still shows no completed follow-up. | n8n opens an approval through the signed follow-up hooks. Mail waits for admin execute. | No schedule editor and no manual run. |
| Email | Functional but sandboxed | Settings and the automation snapshot report `email_mode: sandbox`. No email row was created, because the agent never reached execute. | Sandbox SMTP refuses a non-local host. Live send also requires `email_live_enabled`. | No compose window. The agent address is fixed. |
| Calendar | Simulated | The snapshot reports `calendar_provider: simulation`. | `SimulatedCalendar` writes a local booking and no external event id. | No external calendar and no user-chosen time. |
| Lead score | Partially functional | Not exercised in this pass. The score endpoint stores a prediction and does not change the lead. Analytics does not aggregate scores. | `POST /leads/{id}/predictions`. Training is `POST /ml/train` and is not in the UI. | The model is not a business forecast. |
| Analytics | Partially functional | Lead total moved from 6 to 7, qualified from 2 to 3, and inquiries from 8 to 9. The production page shows 7 leads. | `GET /analytics`. The window is a fixed 30 days. Rates stay null when the denominator is empty. | Counts include demonstration and exercise rows. There is no origin filter and no date control. |
| Monitoring | Partially functional | The three new failures are listed as historical `tool_failed` runs. Recorded cost is null. | Diagnostics read stored runs and traces. | The tool failure has no inner exception. An `mcp_tool` trace was not stored; the API logged `trace_record_failed`. |
| Overview | Partially functional | The production page loads. Its numbers come from the same analytics snapshot and the pending-approval and failed-run lists. | Pending work links to Approvals and Agent Runs. | The same mixed counts as analytics. |
| Workflows | Read-only, with one admin cancel | The two installed automations, sandbox email, and simulated calendar are shown. | The page reads the automation snapshot. An admin can cancel a simulated booking. | No editor, trigger, or retry. |
| Settings | Read-only | Account, membership, Groq, Ollama, sandbox email, simulated calendar, and webhook presence are shown. The provider payload does not contain a key. | Provider status probes the configured models and returns no secrets. | Nothing on the page can be saved. Installing a webhook key remains API-only. |
| MCP tools | Partially functional | `search_company_knowledge` returns hits when called from a fresh interpreter, including the new inquiry text. The same tool fails inside the running agent. | `find_contact`, `get_lead`, and `search_company_knowledge`. The organization id is fixed in the child environment. | The assistant does not use these tools. A crash is reported only as `Error executing tool search_company_knowledge`. |

## Assistant behavior now

The single evidence gate described in the earlier audit is no longer the only path. `route_question` in `apps/api/app/domains/assistant/routing.py` chooses the path before a model call.

| Turn | What the live API did |
|---|---|
| Capability | Returned the fixed "What I can help with" answer. `document_search` was `skipped`. No citation. |
| Inventory and company list | Returned stored counts and names for the signed-in organization. The model was not required. |
| Grounded document question | Called the configured Groq model after retrieval. The sentence matched the uploaded file. The source list also included other documents and CRM rows that passed the evidence gate. |
| Recall | "What did we discuss" returned the prior user and assistant text from this conversation. Retrieval was skipped. |
| Rephrase | With history, "Rephrase the last answer more simply" called Groq and returned a new sentence. |
| Mutation | The router still refuses a write from chat and points the user to Agent Runs. This pass did not resend a mutation. |

Writes remain on the agent and approval path. The assistant does not create or update CRM records.

## Automations

Two automations are hardcoded. They are not loaded from an editable graph.

| Automation | Live result |
|---|---|
| Lead processing | Creating the acceptance lead dispatched n8n. The stored run is `completed`, which only the signed callback writes. |
| Follow-up | Installed and configured. This pass did not ask n8n to open a follow-up approval. |

Email stays sandbox unless live mode and `email_live_enabled` are both set. Calendar bookings stay in ATLAS.

## Demo, evaluation, and operational records

There is still no origin column. These rows share one organization and one set of counts:

- Seed rows such as Harbor & Co. The company note says it is a synthetic demonstration company.
- Earlier exercise rows such as the Cedar brochure and completed Cedar agent runs.
- Assistant conversations titled exactly `eval`, hidden in the assistant behind evaluation history.
- Evaluation runs started from Monitoring. They stay on the monitoring page and are labeled deterministic.
- The acceptance records created on 22 November 2026 and left in place: company, contact, lead, and inquiry stamped `433129a2`, the text document `acceptance-yard-433129a2`, two acceptance conversations, and three failed agent runs for that inquiry.

Do not delete these rows and do not reset the database. A safe separation is an additive origin. Existing rows stay `unclassified` until a person classifies them. New seed writes can be marked `demo`, retrieval-script chats `evaluation`, and ordinary product writes `operational`. Business counts exclude `demo` and `evaluation` only after the value is known. Monitoring can keep every origin.
