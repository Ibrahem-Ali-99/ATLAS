# ATLAS product acceptance

## Release acceptance

This is the current verdict. It was recorded on 22 November 2026 after the local MCP, citation, provenance, and streaming commits. The API was `http://127.0.0.1:8000` and the production web app was `http://127.0.0.1:3000`. Nothing was pushed, deployed, or reset, and no credential was changed. Historical rows were not deleted or relabeled.

`origin/main` is `985c9a5ccd366afdff25b0ccbf820cdc95185583`. Local `main` is ahead of that commit and has not been pushed. GitHub Actions has not run these local commits. The migration chain is linear from `20261122_0001` through `20261122_0011`. `0011` adds `origin` with server default `unknown` and does not update rows by name. `.env.example` still documents Postgres on port 5432, which matches CI. A local `.env` may use another port and is not committed. CI installs the API with `uv sync --frozen` and the web app with `npm ci`. `uv.lock` and `apps/web/package-lock.json` are in the repository. The workflow uses Python 3.12, Node 22, and `pgvector/pgvector:pg17` on port 5432.

The API suite does not read the development database. Each test truncates `atlas_test`. Migration tests use `atlas_migration_test`. The skipped test calls Groq and Ollama only when `ATLAS_LIVE_PROVIDERS=yes`. The live numbers below depend on rows already stored in `atlas-demo`, including the earlier acceptance document and the provenance proof rows.

### Streaming

A grounded reply is no longer sent token by token before citation checks. The server reads the model stream, checks the completed draft against the retrieved rows, and emits one token whose text is the stored message. The production assistant shows "Checking the answer against company records" and then the stored answer. A turn with no retrieved rows still sends tokens as they arrive.

The live question "How many bonded pallets does Acceptance Yard store?" returned one token, equal to the saved message "Acceptance Yard stores 42 bonded pallets." The only source title was `acceptance-yard-433129a2`. The production page showed the checking state and then that sentence with that source.

### Checks run

| Check | Result |
|---|---|
| Ruff check and format | Passed |
| mypy | No issues in 108 source files |
| pytest | 129 passed, 1 skipped |
| ESLint, `next build`, `tsc --noEmit` | Passed. The build emitted 15 static routes |
| Playwright `e2e/workspace.spec.ts` | 4 passed, including the narrow viewport walk |
| gitleaks v8.30.1 | 73 commits scanned after the streaming commits, no leaks |
| Sign-in, then logout | `GET /auth/me` was 200, logout was 204, the next `GET /auth/me` was 401 |
| Staff list, staff approve, other organization | 200, 403, 404 |
| Analytics scopes against SQL | No mismatch. Operational 1 lead and 0 inquiries. Demo 1 and 0. Evaluation 0 and 1. Legacy 8 and 10. All 10 and 11 |
| Unsigned lead callback | 401 `webhook_unauthorized` |
| Email mode and calendar | `sandbox` and `simulation` |
| Agent start on this API | 201, status `awaiting_approval`, origin `evaluation`, knowledge step stored |
| Approval of that run | The three proposals were rejected. Resume returned 200 and the run completed. No historical lead was rewritten |
| Diagnostics | Operational failed runs: 0. Legacy and all: 7. The new run's linked traces are `agent_run` and `approval_decision` |

### Real integration

Checked against the API on `127.0.0.1:8000`, n8n in `atlas-n8n-1`, and Mailpit in `atlas-mailpit-1`. The records use stamp `2b39fc62` and origin `operational`. They were left in place. No credential or delivery mode was changed. Mailpit was stopped only for the failure send and then started again.

| Record | Id |
|---|---|
| Company Integration Yard 2b39fc62 | `4f0dfdad-90e0-4f99-882a-ed4c66a8c460` |
| Contact Integration Contact 2b39fc62 | `932e09cf-64f3-4b05-8ae5-c58cd38c07e3` |
| Lead Integration operational lead 2b39fc62 | `bf5efd70-fdfe-4c9f-9c82-db593c409925` |
| Inquiry Integration operational inquiry 2b39fc62 | `f9967a55-e707-44c9-b753-96ef13b94527` |
| Agent run | `d37273a0-f7b2-4347-89b4-e4500c19c9ad` |
| Workflow run | `e244ce8f-23b2-4c46-bd20-f28df45f9eb4` |
| Update approval | `19d11a82-2d1f-4266-91a2-c604cb70f961` |
| Email approval | `5b839945-0936-4443-b4f4-8dfa5e14a5c5` |
| Appointment approval | `272306d5-2759-4401-a39f-9e2dc57caae0` |
| Email row | `ed99db4e-3355-46a9-ad90-f30575f146d5` |
| Email interaction | `b10937a3-21a2-4149-bba6-85fdad86dfd6` |
| Failure inquiry | `ea4e291e-1eb7-402f-a340-7063a0a19a48` |
| Failure run | `5680fc74-8dab-4fc6-b8cc-f470e0cd1eaa` |
| Failed email row | `b05e3214-30ca-4cfd-af40-f8c3054e1b80` |

**Signed n8n callback: passed.** Creating the lead returned 201 and dispatched the active workflow `ATLAS Lead Processing`. n8n execution `16` is mode `webhook`, status `success`, from `2026-11-22 22:18:36.214` to `2026-11-22 22:18:36.293`. Its nodes `Lead webhook`, `Normalize`, and `Call ATLAS` are each `success`. The HTTP node stored the callback response `{"status":"completed","workflow_run_id":"e244ce8f-23b2-4c46-bd20-f28df45f9eb4"}`. The workflow row is `completed`, origin `operational`, with one attempt and no error. The lead stayed operational, titled `Integration operational lead 2b39fc62`, with the original notes. An empty callback returned 401 `webhook_unauthorized`. A callback with a forged key and signature `00` returned 401 `webhook_unauthorized`, and the workflow stayed `completed`.

**Sandbox email: passed.** The response proposal could not execute while pending. Admin approval returned 200, then execute returned 200. The stored row is status `sent`, mode `sandbox`, recipient `inbox@localhost`, subject `Operational Lead`, and the body is the approved payload. Mailpit message `BocUxT7CX3gxMzjTc95wQg` has Message-ID `8c43dd456d18837ffcaf4262@atlas.local`, From `atlas@localhost`, To `inbox@localhost`, the same subject, and the same text aside from SMTP carriage returns. The address is local. A second approved response was executed while Mailpit was stopped: HTTP 502 `delivery_failed`. That row is status `failed`, mode `sandbox`, with no provider message id and error `delivery_failed`. Mailpit's message total stayed 3.

**Idempotent approval execution: passed.** Execute on the pending update returned 409 `invalid_transition`. Staff approval returned 403 `forbidden`. The other organization reading the lead returned 404 `not_found`. Admin approval returned 200. The first execute returned 200 and wrote the lead once: status `qualified`, notes `Inquiry about bonded storage rates`, origin still `operational`. The second execute returned 409 `already_executed`. Interactions, emails, and bookings stayed at 0 across that second call. The appointment was rejected with 200, so no booking exists. Resume returned 200 and the run is `completed`. The successful email then added one interaction and one email. The failure run is `failed`, which matches the refused delivery.

### Verdict

ATLAS is not release-ready. The three integration paths above passed on the running local services. GitHub Actions has not run the unpushed commits, including the container build job, so this is not a deployed release.

### Unresolved product limits

These are not the reason the streaming or provenance work failed. They remain outside a release claim:

- Rows that existed before `20261122_0011` stay `unknown` until a later explicit write. The operational view does not include them.
- Operation traces have no origin. Diagnostic latency and cost use the latest traces in the organization, not the selected scope.
- An MCP tool trace is stored without `agent_run_id`, so the run view does not list `mcp_tool`. The agent event still records `retrieve_knowledge`.
- The approval queue is not filtered by origin, so a demo proposal stays decidable.
- Calendar bookings are local simulation. Live email requires sandbox to be turned off and the live-send flag to be set.
- Delivery is at-least-once with `needs_attention`. It is not exactly-once.
- Citation checks compare the answer text with the retrieved rows. They are not a proof that every sentence is supported.
- Settings does not install a webhook key.

The sections below are the earlier pass from the same day, before the MCP interpreter fix, citation repair, provenance, and this streaming change.

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

Superseded by the release acceptance section at the top. That section is the current verdict: the local product separates those records and can start an agent, and it is not release-ready until the unpushed commits pass GitHub Actions and the live n8n, sandbox email, and repeat-execute checks have been run.
