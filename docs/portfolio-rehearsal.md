# Portfolio rehearsal

The four Harbor & Co. demonstrations were clicked through on an isolated API at `http://127.0.0.1:8012` and web app at `http://127.0.0.1:3012`, using the database `atlas_portfolio`. The development API on port 8000 was left running. No WhatsApp message, live email, Google event, or Stripe charge was created.

Screenshots from that pass are in `docs/portfolio-rehearsal/screenshots/`.

## Acceptance

| Step | Result | Evidence |
| --- | --- | --- |
| Isolated origin | Pass. The browser called ports 3012 and 8012 only. | Rehearsal log |
| Inbox, prepared thread | Pass. **Cold storage for the north pier** is already linked to Mina and the north pier lead. The inquiry control is **Save inquiry**, not **Create lead and inquiry**. | `03-inbox-thread-desktop.png` |
| Appointment request | Pass. A free local slot was **Available on the ATLAS workspace calendar.** **Open approval** leaves the dialog. | `08-appointment-desktop.png` |
| Staff cannot approve | Pass. After the pending row is selected, the page says an admin has to approve or reject it. **Approve** is absent. | `13-staff-approvals-desktop.png` |
| Approve, then execute | Pass. Execute writes a booking whose provider is `simulation`. The same slot a second time fails with `That time is already booked`. | `08c-approval-executed-desktop.png` |
| CRM company profile | Pass. Harbor & Co. lists Mina Patel, the north pier lead, and the bonded-yard request. Northwind Traders is not in this workspace. | `02-crm-harbor-desktop.png` |
| Booked appointment | Pass. The executed approval stores the simulated booking. The company profile can list that row only after the inbox channel is read as text. | `08c-approval-executed-desktop.png` |
| Assistant citation | Pass. The answer preview includes cold storage from the indexed service note. | `06-assistant-citation-desktop.png` |
| Knowledge upload and replace | Pass. The library title drops `.txt`. After replacement, a new chat cites Thursday afternoon. Wait until **Searching…** finishes before reading search hits. | `05-knowledge-ready-desktop.png`, `07-knowledge-replaced-desktop.png`, `07b-assistant-updated-desktop.png` |
| Workflow branch | Pass. The disposable draft validates, **Preview only** saves nothing, and the applied run follows the matching path and waits for **Confirm approval**. | `10-workflow-canvas-desktop.png`, `11-workflow-preview-desktop.png` |
| Repeat refusal | Pass. A second apply while the first run is pending or awaiting approval returns `workflow_run_in_progress`, including when the repeat box is checked. After the task is saved, the page says the workflow already changed the record. Checking the box runs the saved actions again. A preview stays allowed. | `11c-workflow-repeat-desktop.png` |
| Northwind isolation | Pass. Signed in as the Northwind-only account, CRM did not list Harbor & Co. or Mina Patel. The frame captured during that navigation was still loading, so it is not included. | Rehearsal log |
| Billing | Pass for this process. The banner is **Sandbox billing**. Limits in effect stay on Free. Checkout was not opened. | `14-billing-desktop.png` |
| Overview and analytics | Pass. The loaded Overview shows Demo scope counts and the 30-day range. Analytics rendered stored rows. | `01b-overview-demo-scope-desktop.png`, `15-analytics-desktop.png` |
| Mobile width | Pass at 390×844. Overview, Inbox, Workflows, Approvals, and Billing had no horizontal page overflow. | `16-overview-mobile.png` through `16e-billing-mobile.png` |
| Reset and repeat | Pass. Dropping only `atlas_portfolio`, migrating, and seeding again restored Harbor & Co., the inactive qualified-lead workflow, one simulated booking, and a pending service note. The disposable workflow and extra bookings were gone. Starting the isolated API indexed the note to ready with one passage. | Database check after reset |

The deterministic chat provider returned the retrieved passage. That citation is a stored chunk from the demonstration document. It is not a hosted-model sentence.

## Closure

The profile and workflow regression tests ran on `atlas_rehearsal_profile`, a database created for this check. They did not truncate `atlas_test`. Set `ATLAS_TEST_DATABASE=atlas_rehearsal_profile` before `pytest`. The default test database stays `atlas_test`.

`tests/test_crm_profile.py` passed. A stored inbox channel of `email` is returned as text. `_channel_label` also reads an enum value.

`test_a_second_run_waits_until_the_first_finishes` passed. `workflow_run_in_progress` blocks another apply while the first run is pending or awaiting approval. `confirm_repeat` does not bypass that wait. After the task exists, a repeat without confirmation is still `workflow_effect_already_recorded`, and confirmation queues another run.

Groq (`openai/gpt-oss-20b`) and Ollama (`nomic-embed-text:v1.5`, 768 dimensions) were checked on a disposable database, `atlas_rehearsal_providers`, using only the fictional bonded-warehousing note. The note indexed to ready with one passage. The cold-storage question called the model, cited `bonded-warehousing-overview`, and the stored excerpt contained the note. The answer said cold storage for the third quarter is confirmed for existing customers. A question for a bank account number did not call the model, stored no citation, and did not invent digits. That database was dropped afterward. The API on port 8012 was not restarted and was not pointed at Groq.

The public demo page says Mina Patel asks about bonded warehousing, and that Northwind is the second organization. `python -m app.scripts.verify_portfolio_demonstration` passed.

## Reset

Stop only the process listening on port 8012. Leave port 8000, port 3000, and the tunnel running.

From `apps/api`, with the portfolio URL ending in `/atlas_portfolio`:

1. Terminate connections to `atlas_portfolio` and drop that database. Refuse any other name.
2. Run `python -m alembic upgrade head` with `ALEMBIC_DATABASE_URL` pointed at `atlas_portfolio`.
3. Run `python -m app.scripts.portfolio_demo` with `ATLAS_PORTFOLIO_DEMO=apply`, the portfolio URL, a storage directory outside the active upload store, and the sandbox overrides in `docs/portfolio-demo.md`. `ATLAS_PUBLIC_DEMO` stays false for this command.
4. Start the API on port 8012 with `ATLAS_PUBLIC_DEMO=true`, `ATLAS_DATABASE_URL` set to `atlas_portfolio`, `ATLAS_STORAGE_DIR` set to the portfolio storage directory, `ATLAS_SESSION_COOKIE_NAME=atlas_portfolio_session`, CORS limited to `http://127.0.0.1:3012`, and the same sandbox provider overrides. Do not use `--reload`.
5. Start the canonical web app from `apps/web-rebuild` with `ATLAS_API_URL=http://127.0.0.1:8012`, `NEXT_DIST_DIR=.next-portfolio`, and `npx next dev --hostname 127.0.0.1 --port 3012`.
6. Sign in with the local seed accounts. Passwords stay in the local environment file.

Running the portfolio command again without dropping the database updates the prepared rows and leaves extra rehearsal rows in place. A clean repeat drops `atlas_portfolio` first.

## Release blockers

No open defect remains from this rehearsal.

These limits are still true:

- Stripe test checkout was not run. The isolated process stays on **Sandbox billing**.
- Executing a second appointment for a slot that is already booked fails with `That time is already booked`. The presenter uses a free slot.
