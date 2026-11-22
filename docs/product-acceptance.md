# ATLAS product acceptance

Acceptance pass on 22 November 2026. The API was `http://127.0.0.1:8000` and the production web app was `http://127.0.0.1:3000`. No page was redesigned, no database was reset, and no credential was changed. Records created for the scenarios were left in place.

The capability map is `docs/product-audit.md`.

## How this was tested

- Live HTTP calls as the seeded admin, staff user, and the user in the other organization.
- The production UI, signed in as the admin, for CRM, Analytics, Monitoring, and Workflows.
- `uv run pytest -q --tb=line` for `tests/test_assistant_routing.py`, `tests/test_approvals.py`, `tests/test_authorization.py`, `tests/test_automation.py`, and `tests/test_agents.py`. Result: 50 passed, exit code 0.
- Provider status reported Groq `openai/gpt-oss-20b` ready and Ollama `nomic-embed-text` at 768 dimensions ready. The status payload did not contain a key.

The full API suite was not rerun in this pass.

## Records left in the database

Stamp `433129a2` in the admin organization:

| Record | Id |
|---|---|
| Company Acceptance Yard 433129a2 | `bd2f3e04-698c-4a68-b974-2bab561b30be` |
| Contact Nora Acceptance 433129a2 | `214a06f2-3ee3-4164-be9b-49ba3d4832db` |
| Lead Acceptance pier 433129a2 | `9234b76b-4480-4416-9756-459fcef9c911` |
| Inquiry Bonded storage 433129a2 | `e39d7bdf-73c5-4787-b25d-4b44c22f2d71` |

Also left in place: document `acceptance-yard-433129a2` at status `ready`, two assistant conversations, the failed HTTP starts, and the completed run `12eb9db3-1243-49e7-80f9-798c75b169e4`. The first failed run id is `f8c7921c-88b9-4b39-80f7-dbb76dd187ab`.

## Scenario A — Customer management

**Result: passed.**

Created the company, contact, lead, and inquiry. Patched the lead from `new` to `qualified`. Analytics moved from 6 leads to 7, qualified from 2 to 3, and inquiries from 8 to 9. The production CRM search shows the company. The production Analytics page shows 7 leads.

Creating the lead also stored a lead-processing workflow. That result is scenario E.

## Scenario B — Business knowledge

**Result: passed for indexing and the answer. Failed for citation trust.**

Uploaded a text file stating that the acceptance company stores 42 bonded pallets and containing the token `AXYARD-433129a2-PALLETS`. The document reached `ready` with no error. Search for the token returned that excerpt first and also the Cedar brochure.

The grounded question returned HTTP 200, `document_search: ready`, and this answer: the acceptance company stores 42 bonded pallets and the token matches the file. That sentence is not the deterministic test double. Groq was ready, so this was a live model completion grounded in retrieval.

The stored sources also included the Cedar brochure, the new company and lead, the Cedar lead, North pier expansion, and the new contact. The answer used the uploaded file. The source list does not say which row supported the sentence.

The follow-up "What did we discuss about that pallet count?" returned the prior user and assistant text. `document_search` was `skipped`. That is the recall path, and it used this conversation rather than treating the prior answer as a new citation.

## Scenario C — General assistant

**Result: passed, with the inventory definition kept visible.**

| Question | Model | Evidence |
|---|---|---|
| What can you help with? | Not called | Fixed capability answer. `document_search: skipped`. No sources. |
| What information do you have? | Not called | Inventory for this organization: 2 companies and 7 leads. It states that attention includes new, contacted, and qualified. |
| Which companies are in my CRM? | Not called | Acceptance Yard 433129a2 and Harbor & Co. only. |
| Rephrase the last answer more simply. | Groq | `document_search: skipped`. Answer: "There are two companies listed in your CRM." |

The company list is organization-scoped. Harbor remains because it is a real row in this organization, not because the assistant crossed tenants.

## Scenario D — Agent execution

**Result: the product API cannot start a run. The decision path works once a run exists.**

`POST /agent-runs` on the API serving `127.0.0.1:8000` was tried four times, including once after the successful run below. Each returned HTTP 502 `tool_failed` with `Error executing tool search_company_knowledge`. The stored runs show `load_inquiry` succeeded, Groq `classify` succeeded, and then `run` failed. The message is the MCP crash wrapper. The child exception is not stored.

The same `start_run` function, imported by a fresh interpreter against this database, reached `awaiting_approval`. Run `12eb9db3-1243-49e7-80f9-798c75b169e4`:

| Step | Stored result |
|---|---|
| classify | Category `Storage`. Contact name `Nora Acceptance`. |
| retrieve_knowledge | Cedar brochure and `acceptance-yard-433129a2`. The acceptance excerpt contains the 42-pallet sentence. |
| lookup_customer | Contact `214a06f2-3ee3-4164-be9b-49ba3d4832db` and lead `9234b76b-4480-4416-9756-459fcef9c911`. |
| qualify | `qualified`. |
| propose | `update_lead`, `prepare_customer_response`, `request_appointment`. |

Through the HTTP API, an admin approved `update_lead` and rejected the email and the appointment. Staff rejection of the email returned 403. Resume returned 200 and the run status became `completed`. The execute event succeeded. The lead notes changed from "Asked about bonded pallet capacity." to "Nora from Acceptance Yard requests rates for bonded pallet storage (yard note AXYARD-433129a2-PALLETS)." The lead status stayed `qualified`. A second execute returned 409 `already_executed`. No email row was stored for the lead. No calendar booking was stored for the lead.

The classifier name omitted the stamp. Lookup still stored the contact and lead that were created for this inquiry. The knowledge hits list the Cedar brochure beside the acceptance document, with no mark for which hit the proposal used.

## Scenario E — Automation

**Result: lead dispatch and callback passed. Follow-up and sandbox send were not invoked.**

The acceptance lead's workflow run is `completed` with one attempt, outcome `succeeded`, and no error. Dispatch alone sets the run to `accepted`. `completed` is written by `complete_lead_callback` after the signed hook. n8n was configured and the webhook key was present. The key was not read or printed.

The follow-up card remains at 0 completed. This pass did not call `/api/v1/hooks/follow-ups`. The lead-processing card still counts 1 `needs_attention` from an older run.

Email mode is `sandbox`. Calendar provider is `simulation`. No sandbox message was sent, because the agent never executed `prepare_customer_response`.

## Scenario F — Business oversight

**Result: the new CRM records are visible. The new agent failures are visible. The pages still mix origins.**

After the scenarios, analytics reported 7 leads, 9 inquiries, 3 qualified, 2 pending approvals, and the fixed sentence that counts include synthetic demonstration records and are not revenue. Diagnostics reported 4 failed runs, cost `null`, 1 integration failure, and 0 approvals waiting on an uncertain outcome. The production Monitoring page shows `tool_failed`. Workflows shows Lead processing.

Overview uses this analytics snapshot plus the pending-approval and failed-run lists. It does not separate the acceptance company from Harbor or from earlier exercise rows.

## Scenario G — Security

**Result: the checks that could run passed. Duplicate execution was not reached on a live approval.**

| Check | Result |
|---|---|
| Company create without `X-CSRF-Token` | 403 `csrf_failed` |
| Staff approve of an existing pending action | 403 `forbidden`, "Admin role is required for this resource" |
| Other organization reads the acceptance company | 404 `not_found`. That user is an admin of the other organization. |
| Provider status | Groq and Ollama readiness only. No key marker in the payload. |
| Logout, then `GET /auth/me` | 204, then 401 |
| Second execute of the acceptance lead approval | 409 `already_executed`. The lead notes did not change again. |

## Failed or unavailable capabilities

- Starting an agent run from the API the product is serving. Classification works. The knowledge tool then crashes, and the crash cause is not stored.
- A follow-up approval opened from n8n. The hook was not called in this pass.
- A sandbox email delivery. The email proposal was rejected, so no send was attempted. That is the intended gate, and the sandbox path itself was not executed.
- A user-facing retry of a workflow, a webhook-key install, an organization switch, or a saved setting.
- An origin filter. The product cannot hide demonstration rows without a new field.

## Remaining limitations

These are deliberate or already bounded, and they are not the broken agent path:

- Email is sandbox unless live mode and the live-send flag are both set.
- Calendar bookings are local simulation.
- The assistant cannot write CRM, send mail, or book a calendar event.
- Settings cannot display or edit secrets.
- Analytics uses a fixed 30-day window and does not invent a score distribution.
- Exactly-once delivery is not the contract. Lead dispatch is idempotent per lead. An uncertain outcome stays `needs_attention`.
- This pass does not claim a pentest, a compliance review, or production readiness.

## Prioritized corrective backlog

### 1. The serving API cannot start an agent run

- **Severity:** Critical
- **Business impact:** An operator using the product cannot open the approval journey. The run is stored as a historical failure, and Monitoring cannot explain it. Approve, reject, and resume already work when a run has reached `awaiting_approval`.
- **Root cause:** `POST /agent-runs` on the process listening at `127.0.0.1:8000` classifies with Groq and then fails in MCP `search_company_knowledge`. The SDK replaces an unexpected tool exception with `Error executing tool search_company_knowledge`, and that is all the run stores. The same `start_run` call from a fresh interpreter, against the same database, stores knowledge hits and pauses for approval. The API process image is the base CPython under `%APPDATA%\uv\python`, which cannot import `mcp` when launched on its own. `server_parameters` uses `sys.executable` and does not pass the virtualenv. A direct spawn of that base interpreter fails earlier, with `ModuleNotFoundError: No module named 'mcp'`, so it is not the whole explanation of the stored wrapper. The serving process and a fresh interpreter do not produce the same tool result.
- **Frontend:** Show the stored error on the run and in Monitoring. When the message is only the generic tool wrapper, say that the tool crashed and the cause was not returned. Do not add a retry button until a start from this API process succeeds.
- **Backend:** Spawn the MCP child with the interpreter that has the API dependencies, and pass only the environment the child needs. Store the child exception class and a redacted message on the run. Keep the organization id fixed in the child and do not pass the Groq key.
- **Acceptance:** `POST /agent-runs` on the serving API reaches `awaiting_approval` with a lead proposal, an email proposal, and an appointment proposal. The knowledge event lists stored hits. A forced tool crash stores a cause an admin can read, without a secret or a database URL.

### 2. Grounded citations include rows the answer did not need

- **Severity:** Major
- **Business impact:** The pallet answer was right, and the source list also showed the Cedar brochure and unrelated leads. A user cannot tell which row was evidence.
- **Root cause:** `prepare_turn` attaches every CRM row from `search_records` and every chunk that passes the evidence gate. The model may use one row. The product stores all of them as sources.
- **Frontend:** Render the stored sources, and label a source that was retrieved but not required only if the API marks it that way. Do not hide a source the API still returns.
- **Backend:** Return the rows that passed the evidence gate in a distinguished list, and mark the rows that share a content token with the answer or that were the closest eligible hit. Do not drop a row silently and do not let the model invent a citation.
- **Acceptance:** For the acceptance document question, the uploaded file is the supporting source. The Cedar brochure is absent or marked as a candidate that was not used. A question with no eligible hit still returns the refusal and does not call the model.

### 3. Business counts mix demonstration, exercise, and operational rows

- **Severity:** Major
- **Business impact:** Analytics moved to 7 leads because the acceptance lead was added to Harbor and the older exercise leads. The notice is a fixed sentence. It does not say which 7 rows are included.
- **Root cause:** Companies, leads, documents, conversations, and runs have no origin. Overview, Analytics, and the assistant inventory count every row in the organization.
- **Frontend:** Until origin exists, keep the current notice. After it exists, give business counts a control that excludes `demo` and `evaluation`, and keep Monitoring able to show every origin.
- **Backend:** Add an origin column with a default that does not rewrite history. Existing rows stay `unclassified`. New seed writes can be `demo`. Ordinary creates from the product can be `operational`. Do not delete or relabel the current rows in a migration.
- **Acceptance:** The acceptance company and Harbor remain stored. A business analytics response can exclude a row marked `demo` or `evaluation`. An `unclassified` row stays visible. Monitoring still lists the failed acceptance runs.

### 4. MCP traces are dropped when the trace insert fails

- **Severity:** Minor
- **Business impact:** The failed knowledge call has an agent-run trace and no `mcp_tool` trace. Latency and the tool name are missing from the diagnostic run.
- **Root cause:** `record_operation` logs `trace_record_failed` and swallows the insert exception. The log was emitted for `mcp_tool` during the successful out-of-process call and is consistent with the missing diagnostic row.
- **Frontend:** None until a trace exists.
- **Backend:** Log the exception class. Fix the insert so a tool call stores operation, status, and latency. Do not log the query if it could contain customer text beyond the existing redaction.
- **Acceptance:** A knowledge tool call, success or failure, appears on the diagnostic run with operation `mcp_tool` and a latency.

### 5. Classifier contact name dropped the unique suffix

- **Severity:** Minor
- **Business impact:** The stored contact name is `Nora Acceptance`. The contact that was created is `Nora Acceptance 433129a2`. On the successful run, lookup still stored that contact id and the acceptance lead id, so no wrong customer was written.
- **Root cause:** The classify step asks the model for a contact name and stores it on the event. Lookup then searches by that string and can also fall back to the inquiry's lead id. A similar older name could win the search when the inquiry has no lead id.
- **Frontend:** Show the stored contact name as model output, and show the contact id from the lookup event beside it.
- **Backend:** If several contacts match the model name, store no contact id and say the customer was ambiguous. Do not let the model choose the organization.
- **Acceptance:** A run with one matching contact stores that contact id. A run with two matches stores neither id and does not update the older contact.

### 6. Settings cannot install the webhook key the API can already create

- **Severity:** Enhancement
- **Business impact:** This organization already has a key, and the acceptance lead completed. A new organization cannot install the key from Settings.
- **Root cause:** `POST /integrations/webhook-keys` exists for an admin. Settings is read-only and correctly hides the secret after it would have been shown once.
- **Frontend:** An admin action that creates a key and shows the secret once, then forgets it.
- **Backend:** None beyond the existing create-once response.
- **Acceptance:** The secret is not present on a later Settings load. A lead created after the key exists can dispatch. The Groq key remains unreadable.

## Readiness verdict

ATLAS can record a customer, index a document, answer from that document with Groq, dispatch a lead through n8n, and decide an existing agent proposal. It cannot start that proposal from the API process the product is using. On a run that was created outside that process, an admin approved the CRM write, rejected the email and the appointment, and resume wrote the lead notes once. A second execute was rejected. Staff could not reject. Another organization could not read the company. Business counts still mix demonstration and operational rows. The product is an operations shell with a broken agent start on this deployment, not a closed inquiry-to-approval workflow.
