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

Also left in place: document `acceptance-yard-433129a2` at status `ready`, two assistant conversations, and three failed agent runs for that inquiry. The first failed run id is `f8c7921c-88b9-4b39-80f7-dbb76dd187ab`.

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

**Result: failed before a proposal.**

Three starts of the acceptance inquiry each returned HTTP 502 `tool_failed` in about four seconds. The stored run shows:

1. `load_inquiry` succeeded.
2. `classify` succeeded. Groq recorded category `pricing_inquiry` and contact name `Nora Acceptance`.
3. `run` failed. `error_message` is `Error executing tool search_company_knowledge`.

No approval was created. Approve, reject, resume, and a second execute could not be performed on this run. The lead notes are still "Asked about bonded pallet capacity." No email row was created for the lead.

The same MCP tool, called from a fresh interpreter with the same inquiry text, returned 2 hits. Older runs on this database, including "Cedar pallet quote" and an earlier "Bonded storage" inquiry, are `completed`. The graph can finish. This live process currently stops every new start of this inquiry inside the knowledge tool, and the tool crash is replaced with a generic message before it reaches Monitoring.

The classifier stored the contact name without the stamp that makes this contact unique. Lookup did not run, so a wrong-customer write was not observed.

Staff denial was tested on an already pending approval and is recorded in scenario G.

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
| Second execute of the new lead approval | Not run. The agent never created the approval. The service rejects `already_executed`, and the approval tests passed. |

## Failed or unavailable capabilities

- Starting an agent run on the acceptance inquiry. Classification works. Knowledge retrieval in the running API does not.
- Approving an internal write, rejecting the email and appointment, resuming, and proving a single CRM write. Blocked by the failure above.
- A follow-up approval opened from n8n. The hook was not called.
- A sandbox email delivery. No execute occurred.
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

### 1. Agent knowledge retrieval crashes inside the running API

- **Severity:** Critical
- **Business impact:** An operator cannot start the inquiry-to-approval journey. The run is stored as a historical failure, and Monitoring cannot explain it.
- **Root cause:** After Groq classification, `retrieve_knowledge` calls MCP `search_company_knowledge`. The tool process raises an unexpected exception. `UnexpectedToolError` replaces that exception with `Error executing tool search_company_knowledge` before the API stores `tool_failed`. The same call from a fresh interpreter returns hits, so the documents and the tool function are usable outside this agent invocation.
- **Frontend:** Show the stored error on the run and in Monitoring. When the message is only the generic tool wrapper, say that the tool crashed and the cause was not returned. Do not add a retry button that calls the same failing start until the backend returns.
- **Backend:** Preserve the child exception type and a redacted message on the agent run. Make `search_company_knowledge` succeed from the API process that serves `/agent-runs`, using the same inquiry text that already returns hits out of process. Keep the organization id fixed in the child and do not pass the Groq key.
- **Acceptance:** A new inquiry run reaches `awaiting_approval` with a lead proposal, an email proposal, and an appointment proposal. The knowledge event lists stored hits. A forced tool crash stores a cause an admin can read, without a secret or a database URL.

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
- **Business impact:** The stored contact name is `Nora Acceptance`. The contact that was created is `Nora Acceptance 433129a2`. Lookup did not run, so no wrong lead was written.
- **Root cause:** The classify step asks the model for a contact name and stores it on the event. It is not constrained to a contact id returned by `find_contact`.
- **Frontend:** Show the stored contact name as model output, and show the contact id only after lookup returns one.
- **Backend:** Resolve the name with `find_contact` and store that id. If several contacts match, store no id and let the proposal say the customer was ambiguous.
- **Acceptance:** A run that reaches lookup either stores the stamped contact id or records that the name was ambiguous. It does not attach an older contact with a similar name.

### 6. Settings cannot install the webhook key the API can already create

- **Severity:** Enhancement
- **Business impact:** This organization already has a key, and the acceptance lead completed. A new organization cannot install the key from Settings.
- **Root cause:** `POST /integrations/webhook-keys` exists for an admin. Settings is read-only and correctly hides the secret after it would have been shown once.
- **Frontend:** An admin action that creates a key and shows the secret once, then forgets it.
- **Backend:** None beyond the existing create-once response.
- **Acceptance:** The secret is not present on a later Settings load. A lead created after the key exists can dispatch. The Groq key remains unreadable.

## Readiness verdict

ATLAS is not ready to run the inquiry-to-approval operation on this deployment. CRM, knowledge indexing, organization-scoped assistant reads, Groq answers for a grounded question and a rephrase, the n8n lead callback, analytics updates, CSRF, tenant isolation, and the staff approval denial all worked. The agent stops at the knowledge tool, so the approve, reject, resume, and single-write checks could not be completed. Business counts still mix demonstration and operational rows. Treat the product as a working operations shell with a broken agent handoff, not as a closed business workflow.
