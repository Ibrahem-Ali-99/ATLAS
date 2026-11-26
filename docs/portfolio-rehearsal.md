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
| Repeat refusal | Pass, after the first task is saved. The page says the workflow already changed the record and to confirm before running the actions again. | `11c-workflow-repeat-desktop.png` |
| Northwind isolation | Pass. Signed in as the Northwind-only account, CRM did not list Harbor & Co. or Mina Patel. The frame captured during that navigation was still loading, so it is not included. | Rehearsal log |
| Billing | Pass for this process. The banner is **Sandbox billing**. Limits in effect stay on Free. Checkout was not opened. | `14-billing-desktop.png` |
| Overview and analytics | Pass. The loaded Overview shows Demo scope counts and the 30-day range. Analytics rendered stored rows. | `01b-overview-demo-scope-desktop.png`, `15-analytics-desktop.png` |
| Mobile width | Pass at 390×844. Overview, Inbox, Workflows, Approvals, and Billing had no horizontal page overflow. | `16-overview-mobile.png` through `16e-billing-mobile.png` |
| Reset and repeat | Pass. Dropping only `atlas_portfolio`, migrating, and seeding again restored Harbor & Co., the inactive qualified-lead workflow, one simulated booking, and a pending service note. The disposable workflow and extra bookings were gone. Starting the isolated API indexed the note to ready with one passage. | Database check after reset |

The deterministic chat provider returned the retrieved passage. That citation is a stored chunk from the demonstration document. It is not a hosted-model sentence.

## Reset

Stop only the process listening on port 8012. Leave port 8000, port 3000, and the tunnel running.

From `apps/api`, with the portfolio URL ending in `/atlas_portfolio`:

1. Terminate connections to `atlas_portfolio` and drop that database. Refuse any other name.
2. Run `python -m alembic upgrade head` with `ALEMBIC_DATABASE_URL` pointed at `atlas_portfolio`.
3. Run `python -m app.scripts.portfolio_demo` with `ATLAS_PORTFOLIO_DEMO=apply`, the portfolio URL, a storage directory outside the active upload store, and the sandbox overrides in `docs/portfolio-demo.md`. `ATLAS_PUBLIC_DEMO` stays false for this command.
4. Start the API on port 8012 with `ATLAS_PUBLIC_DEMO=true`, `ATLAS_DATABASE_URL` set to `atlas_portfolio`, `ATLAS_STORAGE_DIR` set to the portfolio storage directory, `ATLAS_SESSION_COOKIE_NAME=atlas_portfolio_session`, CORS limited to `http://127.0.0.1:3012`, and the same sandbox provider overrides. Do not use `--reload`.
5. Start the web app with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8012`, `NEXT_DIST_DIR=.next-portfolio`, and `npx next dev --hostname 127.0.0.1 --port 3012`.
6. Sign in with the local seed accounts. Passwords stay in the local environment file.

Running the portfolio command again without dropping the database updates the prepared rows and leaves extra rehearsal rows in place. A clean repeat drops `atlas_portfolio` first.

## Release blockers

- The customer profile returned HTTP 500 when an inbox channel was stored as text, so **Appointments** never rendered. `customer_profile` now reads a string channel without calling `.value`. The profile unit test could not be finished while another session held the shared test database.
- This rehearsal did not open Stripe. The isolated process is **Sandbox billing**. A claim that a visitor completed Stripe test checkout is not covered here.
- The citations above come from the deterministic provider. A Groq or other hosted-model wording pass was not part of this run.
- Executing a second appointment for a slot that is already booked marks that approval failed. The presenter has to use a free slot.
- Starting a second workflow run before the first saved effect exists does not show the repeat refusal. Wait for the task, then run again.
- The public pages in the working tree no longer name Mina Patel, so `python -m app.scripts.verify_portfolio_demonstration` fails that alignment check. Those pages belong to the public website session and were not edited here.
