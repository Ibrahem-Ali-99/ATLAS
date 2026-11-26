# ATLAS portfolio demonstration

Harbor & Co. is a fictional logistics company. Mina Patel, operations lead, asks whether the north pier yard can hold bonded freight and cold storage in the third quarter. Northwind is a second fictional organization used only to show that its records stay hidden. Neither company is a customer. The public site, the case study, and this demonstration use the same names.

The click path belongs on an isolated database named `atlas_portfolio`. The existing command is `python -m app.scripts.portfolio_demo`, run from `apps/api`. It writes only when `ATLAS_PORTFOLIO_DEMO=apply`, `ATLAS_PORTFOLIO_DATABASE_URL` ends in `/atlas_portfolio`, and `ATLAS_PORTFOLIO_STORAGE_DIR` is outside the active upload store. It refuses the development database, the test databases, production, a public-demo process, live email, live campaigns, live WhatsApp, an n8n URL, a paid chat or embedding key, a Stripe secret, and a Google Calendar client secret.

Do not point that command at the database that holds operational records. Do not remove keys from the shared environment file to make the command accept the running process. If this workspace has a paid model key, a Stripe secret, or a Google client secret, leave them in place and show the prepared scene, or run the command in a separate process whose settings are the deterministic sandbox. Do not restart the API, the web app, or the tunnel for this demonstration.

The checker in `app.scripts.verify_portfolio_demonstration` reads this document and the product guards. It does not connect to a database, send a message, open Stripe, or create a row.

Do not send WhatsApp, live email, or a live campaign. Do not complete a Stripe checkout with a real card. Do not book a new Google Calendar event for this demonstration. Passwords are not written here. The operator uses the local seed accounts already configured for Atlas Demo, a staff member, and Northwind. Prepared rows use demo origin, so choose **Demo** or **All records** under **Advanced data filters** when a list looks empty.

## What is real, and what is a sandbox

| What the audience sees | What it is |
| --- | --- |
| Inbox message stored from the local website chat widget | Real application write. No message leaves the machine. |
| CRM lead, inquiry, task, and opportunity | Real rows in PostgreSQL for the signed-in organization. |
| Assistant answer and citation | Real retrieval. The wording comes from the configured chat model. With the deterministic provider, the answer is the fixed grounded sentence. With Groq or another configured model, the wording is that provider's and can be wrong. The citation is a retrieved passage, not a sentence invented by the page. |
| Document upload, replace, archive | Real indexing. Local Ollama embeddings stay on this machine. An OpenAI embedding key would send passages to that account. The public-demo process refuses a paid embedding key. |
| Approval, then Execute | Real gate. Nothing is written to CRM, email, or a calendar until an administrator executes the stored payload. |
| Sandbox email | SMTP to the local mailbox. It is not a customer delivery. |
| ATLAS calendar booking with provider `simulation` | A row in ATLAS. No Google event is created. |
| Google Calendar booking | A real private event, and only after approval, a second availability check, and an existing OAuth connection. Do not start a new Google booking in this demonstration. |
| Stripe test checkout | A Stripe test-mode payment. The Billing page must say `Stripe test mode`. Entitlements stay on the current plan until Stripe confirms the subscription. A page that says `Sandbox billing` has not charged Stripe at all. |
| Analytics | Counts of stored rows. Missing amounts stay blank. Currencies are not added together. |

## Shared scene

Use these inputs whenever a step needs an example. They match the public site and `app.scripts.portfolio_demo`.

| Item | Value |
| --- | --- |
| Company | Harbor & Co. |
| Contact | Mina Patel, `mina.patel@harbor.example` |
| Lead | North pier expansion |
| Inquiry subject | Schedule a bonded-yard visit |
| Inquiry body | Mina asked to walk the bonded yard before the third quarter. |
| Visitor message | Could you confirm bonded and cold storage at the north pier yard? |
| Knowledge file | `bonded-warehousing-overview.txt` |
| Knowledge text | Harbor & Co. service note. Bonded warehousing is available at the north pier yard. Cold storage for the third quarter is confirmed for existing customers. A written service sheet is issued after a person reviews the inquiry. |
| Replacement sentence | The north pier bonded yard now confirms cold storage through the third quarter, and the visit window is Thursday afternoon. |
| Assistant question | Does Harbor & Co. have cold storage this quarter? |
| Follow-up question | When can Mina visit the north pier bonded yard? |
| Workflow name | Qualified lead follow-up |
| Matching task | Send the bonded service sheet |
| Otherwise task | Ask Mina for the missing yard details |
| Appointment | 18 March 2027, 15:00–15:30 local |
| Opportunity | North pier bonded capacity, 48000 USD |
| Second company | Lumen Freight, Jonah Ellis. Fictional, same workspace, not a second tenant. |
| Other tenant | Northwind |

The portfolio command, when an operator runs it later against `atlas_portfolio`, stores this scene. It was not run against the development database. A presenter can show the stored rows without creating anything. The numbered steps are the click path when the audience should see the action happen, and they belong only on `atlas_portfolio`. Archive disposable copies there when the recording ends. Leave Harbor & Co., Mina Patel, and the north pier lead in place.

Prepared rows, using the names the command writes:

| Record | What is stored |
| --- | --- |
| Inbox | Email subject `Cold storage for the north pier`, with an unsent draft. Website chat subject `Website chat: bonded yard visit`. |
| Knowledge | Title `Bonded warehousing overview`, file `bonded-warehousing-overview.txt`. The row is pending until the isolated API indexes it. The development process does not queue that job. |
| Assistant | Conversation `Bonded yard capacity`. It does not contain a fabricated citation. A citation appears only after a question is asked against indexed passages. |
| Workflow | Inactive `Qualified lead follow-up`, slug `qualified-lead-follow-up`. The matching path is an approval, then the task `Send the service sheet`. The otherwise path is empty, so the definition does not dispatch. One historical run is completed and says no message was sent. The task `Prepare the yard agenda` is completed. |
| Approval | A rejected customer response, subject `Bonded warehousing`, to `mina.patel@harbor.example`. The note says no message was sent. |
| Appointment | Executed, provider `simulation`, 18 March 2027, 15:00–15:30 UTC. There is no external event id. |
| Campaign | Draft `Q3 cold-storage briefing`, sandbox mode. No delivery row is queued. |
| Plan | Free until a confirmed subscription: 2 seats, 100 assistant requests, 1 GB, and 2 active workflows. |

## Demonstration 1 — Intelligent customer operations

Goal: a customer message becomes a lead, a sourced summary, an appointment request, an approval, and a calendar row.

1. Sign in as the Atlas Demo administrator. Open **Inbox**. If the thread is missing, open **Advanced data filters** and choose **Demo** or **All records**.
2. If the prepared thread **Cold storage for the north pier** is already there, select it. To show intake live, open the local website chat embed for Atlas Demo and send: `Could you confirm bonded and cold storage at the north pier yard?` Return to **Inbox** and select the new thread. Do not use WhatsApp and do not type a staff reply that would leave the machine.
3. In **Linked CRM records**, choose Mina Patel under **Existing contact**, or create the contact with name `Mina Patel` and email `mina.patel@harbor.example`.
4. Open **Record customer inquiry**. Set the lead title to `North pier expansion`. Choose **Create lead and inquiry**. The thread then links the lead. Choose **Open CRM inquiry** if it appears.
5. Open **AI Assistant**. Start **New chat**. Ask: `Does Harbor & Co. have cold storage this quarter?` Wait until the answer finishes. Open the citation **Preview**. The excerpt must come from `bonded-warehousing-overview` or the service note, and it must mention cold storage. If no source is listed, say that retrieval found nothing. Do not read a sentence that has no citation as a company fact.
6. Return to the lead **North pier expansion** in **CRM**, or stay in Inbox once the lead is linked. Choose **Request appointment**. Set **Starts at** to `2027-03-18T15:00` and **Ends at** to `2027-03-18T15:30`. Choose **Check availability**. The status line says either `Google Calendar and in ATLAS` or `the ATLAS workspace calendar`. Continue only when it says **Available**. Choose **Request approval**. This does not book anything yet.
7. Open **Approvals** from the link, or from the Approvals navigation. Read the stored times. Choose **Approve**. The page says the change is not applied until execution. Choose **Execute** and confirm. A customer-response approval, if one is proposed, stays **Rejected** or is rejected in this demonstration. Rejected text is not sent.
8. Open **CRM**, select Harbor & Co. or the north pier lead, and read **Appointments**. The row shows 18 March 2027, 15:00, and a status of booked. If the availability line named Google Calendar, say that the event is a private Google event and do not create a second one. If it named the ATLAS workspace calendar, say the booking is stored in ATLAS and no external calendar was written.

Expected result: Inbox shows Mina's question, CRM shows the lead and inquiry, the assistant shows a cited cold-storage sentence, Approvals shows the appointment as executed, and the customer profile lists the booking. No outbound WhatsApp or customer email was sent.

## Demonstration 2 — Intelligent knowledge retrieval

Goal: a file is indexed, a question cites it, and a replacement changes the next answer.

1. Open **Knowledge**. Read **How search uses your documents**. The page names the embedding provider and model, for example local Ollama, and links to **Integrations**.
2. The prepared note `Bonded warehousing overview` starts pending. On the isolated API, wait until that row is **ready** before asking a question about it. To show the upload click itself, choose **Upload document** and select a disposable text file that contains the service-note text. Choose **Upload and index**. The row moves from queued or processing to **ready**. Select the row. **File preview** shows the note. **Indexed passages** lists at least one chunk. Do not upload this file into the development library.
3. Open **Semantic search**. Search `cold storage`. Choose **Open source**. The same document and passage are selected.
4. Open **AI Assistant**, **New chat**, and ask `Does Harbor & Co. have cold storage this quarter?` Open **Preview** on the source. The excerpt includes cold storage and the north pier. The document title matches the uploaded file.
5. Return to **Knowledge**. On that document choose **Replace file** and upload a text file whose only new fact is: `The north pier bonded yard now confirms cold storage through the third quarter, and the visit window is Thursday afternoon.` Wait until the row is **ready** again. The old passage is no longer the indexed text.
6. Search `Thursday afternoon`. **Open source** shows the replacement. Search for a phrase that existed only in the first file and was removed. It does not return this document.
7. Start another **New chat**. Ask `When can Mina visit the north pier bonded yard?` The new citation preview includes Thursday afternoon. The earlier conversation may still show the first citation. Say that past answers keep the passage they used, and a new answer uses the current index.
8. Do not archive the Harbor service note if later scenes need it. A disposable extra file can be archived. **Show archived** lists it, and **Restore** indexes it again. Archived documents are absent from search and from new assistant answers.

Expected result: the audience sees queued, processing, and ready states, a preview, a search hit, a citation, and a second citation after replacement. Uploading the same bytes again is refused as a duplicate. Open and click tracking is not part of this scene.

## Demonstration 3 — Business process automation

Goal: a visual workflow branches, a preview saves nothing, an approval gates the task, and history shows the path.

1. Open **Workflows**. The prepared definition `Qualified lead follow-up` is inactive. Its matching path is an approval and the task `Send the service sheet`. Its otherwise path is empty. To show branching, choose **New workflow** and name the draft `Qualified lead follow-up branch`. Leave the trigger on **Lead created**. Set the task title to `Send the bonded service sheet`. Choose **Create draft**. Do not choose **Activate**.
2. On the canvas, select the trigger. Add a condition. Set it to lead status **qualified**, and keep **All conditions**. The canvas splits into **Conditions match** and **Otherwise**. On a narrow screen the matching path is first and the otherwise path is second.
3. On the matching path, add an approval, then keep the task `Send the bonded service sheet`. On the otherwise path, add a task titled `Ask Mina for the missing yard details`. The approval note can read: `Confirm the bonded service sheet before creating the task.` This otherwise path is the disposable draft. Do not describe the prepared definition as already having it.
4. Choose **Validate**. The page says the workflow was validated. The header also says activation checks the trigger, conditions, and actions before the workflow can run.
5. Save, then open **Runs and approvals**. Choose **Test workflow**. Select the lead **North pier expansion** only if its status is not qualified, so the otherwise path is the one under test. First choose **Preview path**. The run is labeled **Preview only**. No task is saved and no approval is requested.
6. Open **Test workflow** again. Select a qualified lead, or set the north pier lead to qualified in CRM first if this database is the isolated portfolio database. Choose **Run on this record**. The run waits at **Awaiting approval**. Approve it in the run panel. The remaining step creates the task. **Run details** says it followed the matching path. The task appears under the lead and can be marked completed.
7. Choose **Run on this record** again for the same lead. The product asks for confirmation before it repeats the saved actions. Leave that box unchecked to show the refusal. A preview does not need that confirmation.
8. Open **Workflow settings** and archive only the disposable copy if a second draft was made. Leave the inactive prepared definition if the portfolio database should stay as published. Do not activate a workflow on a workspace that receives real leads.

Expected result: the canvas shows two paths, the preview run saves nothing, the applied run waits for approval, history shows the branch and the task, and a repeat requires confirmation. No customer message is sent.

## Demonstration 4 — SaaS engineering

Goal: two organizations stay apart, staff cannot approve, billing tells the truth about Stripe, and analytics reads stored rows.

1. Stay signed in as the Atlas Demo administrator. Open **CRM**. Harbor & Co. and Lumen Freight are visible. Northwind is not in the company list, the inbox, or the knowledge library.
2. Sign out. Sign in as the Northwind administrator. Overview, CRM, Inbox, and Knowledge show that organization's own rows. Harbor & Co., Mina Patel, and the bonded service note are absent. Sign out.
3. Sign in as the Atlas Demo staff member. Open **Approvals** and select a pending item. The page says an admin has to approve or reject it. **Approve** and **Execute** are not offered. Sign out and return as the administrator for the rest of the scene.
4. Open **Settings**, then **Billing**. Read the banner before saying anything about payment.
   - `Stripe test mode`: say checkout uses a Stripe test account and does not create a live charge. Choose **Starter** and **Monthly**. The public catalog lists Starter at $19 monthly or $190 yearly, Pro at $49 or $490, and Business at $99 or $990. Choose **Continue to checkout** only when the recording is allowed to open Stripe's test page. Use Stripe's published test card. Stop on the Billing page if the return says the payment is not confirmed yet. **Current plan** can change only after confirmation. **Limits in effect** stays on the previous plan until then. Do not use a real card.
   - `Sandbox billing`: say the plan change stays in this workspace and Stripe was not called. Do not describe it as a charge.
5. Read **Limits in effect**. The Free plan is 2 seats, 100 assistant requests, 1 GB of knowledge files, and 2 active workflows. Starter is 5 seats, 1,000 assistant requests, 10 GB, and 10 active workflows. A workspace over a limit receives a plan-limit error instead of a silent success.
6. Open **Overview**. Open **Advanced data filters** and choose **Demo** when the rows were prepared as demo origin, or **All records** when the audience should see both operational and demo rows. Set the date range to **Last 30 days**. The comparison is against the previous window of the same length. Pipeline amounts stay in their own currency. A stage with no stored amount does not show a total.
7. Open **Analytics**. The same date range, comparison, pipeline, and export are available. Choose **Download CSV** for opportunities. The file has a header. It does not include archived opportunities. Campaign metrics, when shown, count delivery status. The page says open and click events are not stored.

Expected result: Northwind cannot see Harbor & Co., staff cannot approve, the billing banner matches the provider that is actually connected, and analytics numbers are stored counts rather than a decorated chart.

## 90-second product script

Say this while the recording follows the shot list. Do not add a customer count, a testimonial, or a claim that a live charge or a live message was sent.

Harbor & Co. is fictional. Mina Patel asks whether the north pier can store bonded freight. Her message lands in Inbox, and one action records the lead and the inquiry on that company. The assistant answers from the service note and shows the passage it used. An appointment is only requested. An administrator approves it, then executes it, and the booking appears on the customer. Replacing the service note changes the next citation. The old answer keeps the passage it used. A workflow shows the matching path and the otherwise path. A preview saves nothing. The real run waits for approval before it creates the task. A second organization, Northwind, never sees these records, and a staff member cannot approve the booking. Billing says when the page is Stripe test mode and when it is only a sandbox. Analytics reads the rows that were stored. The model can read the workspace. A person still decides what gets booked or sent.

## Five-minute technical walkthrough

Use the same scene. Pause on each result instead of rushing the click.

**0:00 — Tenant and scene.** Sign in to Atlas Demo. Say the session cookie is HttpOnly and the organization is taken from the membership, not from a value the browser chooses. Open CRM and name Harbor & Co., Mina Patel, and the north pier lead. State that Lumen Freight is another fictional company in the same workspace, while Northwind is a different organization.

**0:40 — Intake.** Open Inbox and the north pier thread. Show the customer message. Link Mina or show the link already stored. Open **Record customer inquiry** only if the lead is not already linked. Show the CRM inquiry. Say this write did not send email or WhatsApp.

**1:20 — Retrieval.** Open Knowledge, select the bonded warehousing note, and show ready status, the file preview, and one passage. Ask the assistant whether cold storage is confirmed this quarter. Open the citation preview. Say the stored citation is chosen from the retrieved passage, and a fact that is not in the supplied rows is not treated as company knowledge. If the recording includes replacement, show the new Thursday-afternoon sentence and a new chat that cites it.

**2:20 — Approval.** From the lead, request the 18 March 2027 visit. Show the availability line and say which calendar it names. Approve, then execute. Open the appointment on the customer profile. If a customer-response proposal is visible, reject it and say the text was not sent.

**3:10 — Workflow.** Open the qualified-lead workflow. Point at the condition, the matching path with approval and the service-sheet task, and the otherwise path. Run **Preview path** and show **Preview only**. Run the qualified lead, approve the step, and show the task plus the recorded branch. Say a repeated run must be confirmed so the task is not created by a second click.

**4:10 — Isolation, billing, and analytics.** Sign in as Northwind only long enough to show an empty or unrelated list, then return. As staff, show the sentence that an admin has to decide. On Billing, read the banner aloud and stop before checkout unless this take is the Stripe test take. On Overview, show the 30-day comparison and say currencies are not summed. End on Analytics or Monitoring with one stored count and the statement that a missing rate stays empty.

## Screenshot and recording shot list

Capture at 1440×960 unless the row says 390×844. Do not include the password field, API keys, webhook secrets, or a full card number. Crop Stripe's test page to the test-mode badge and the Starter price.

| Shot | Type | Duration | On screen | Must be true in the frame |
| --- | --- | --- | --- | --- |
| 01 | Still | — | Overview, Atlas Demo, last 30 days | Harbor counts come from stored rows. No invented total. |
| 02 | Still | — | CRM, Harbor & Co. and Mina Patel | Northwind is absent. |
| 03 | Recording | 12s | Inbox thread, Mina's bonded-storage question | The message is inbound. No send button is pressed. |
| 04 | Recording | 10s | Record customer inquiry, then the linked lead | Lead title is North pier expansion. |
| 05 | Still | — | Knowledge, service note, status ready | Preview and one passage are visible. |
| 06 | Recording | 15s | Assistant answer and open citation preview | The excerpt mentions cold storage. The title is the service note. |
| 07 | Recording | 12s | Replace file, then ready, then Thursday-afternoon search | The new passage is the one selected. |
| 08 | Recording | 15s | Request appointment, availability line, Approvals, Execute | The times are 18 March 2027, 15:00–15:30. The banner matches simulation or Google. |
| 09 | Still | — | CRM customer profile, Appointments | The booked row uses those times. |
| 10 | Recording | 18s | Workflow canvas, both paths, Validate | Approval sits on the matching path. Otherwise has the missing-details task. |
| 11 | Recording | 12s | Preview only, then an approved run and the task | Preview has no saved task. The applied run names the matching path. |
| 12 | Still | — | Northwind CRM or Inbox after that sign-in | Harbor & Co. is not listed. |
| 13 | Still | — | Approvals as staff | The sentence says an admin has to approve or reject. |
| 14 | Still | — | Billing banner and current plan | The banner is read as Stripe test mode or Sandbox billing, whichever is on screen. |
| 15 | Still | — | Analytics, 30-day comparison and pipeline | Amounts are split by currency or absent. |
| 16 | Still, 390×844 | — | Overview or Inbox | No horizontal page scroll. Navigation is in the drawer. |

Recording takes, in order, for the 90-second cut: shots 03, 04, 06, 08, 09, 10, and 11. Insert 12 and 14 only if the cut still has time. The five-minute walkthrough uses the full list except 14 when Billing is sandbox and the presenter will not open Stripe.

## Engineering claims that this pack will stand behind

These statements match the current application. The verification script checks the ones that are facts in source. It does not connect to a database or call a provider.

- One Next.js app and one FastAPI process. Organization access comes from membership. Roles are admin and staff.
- Session cookies are HttpOnly. State-changing requests other than login send the CSRF token for that session.
- Inbox can store a website-chat message, link a contact, and create a lead and inquiry from that thread. Retrying intake returns the records already stored.
- The assistant answers from retrieved passages or CRM rows. A citation preview is the stored excerpt. When nothing matches, the assistant stores a refusal and does not call the model for that turn.
- Replacing a document deletes its old passages before the new file is indexed. The same file bytes are not indexed twice for one organization. Archiving removes the document from search until restore.
- An appointment request does not book until an administrator approves and executes it. Staff see that an admin has to decide. A rejected customer response is not sent.
- A simulation booking is a row in ATLAS. A Google booking is a separate, already connected path and is not required for this demonstration.
- A workflow can require all or any conditions, then follow the matching path or the otherwise path. Preview records the steps and does not save the task, lead change, or follow-up draft. Repeating a saved action on the same record requires confirmation.
- The portfolio command writes only `atlas_portfolio`. It refuses production, a public-demo process, live email, live campaigns, live WhatsApp, an n8n URL, a paid chat or embedding key, a Stripe secret, and a Google Calendar client secret.
- Free limits are 2 seats, 100 assistant requests, 1 GB of knowledge files, and 2 active workflows. Starter is 5 seats, 1,000 requests, 10 GB, and 10 active workflows. Paid catalog prices published on the site are Starter $19 or $190, Pro $49 or $490, and Business $99 or $990.
- Stripe checkout does not change **Limits in effect** until the provider confirms the subscription. Sandbox billing never calls Stripe.
- Analytics uses stored rows for the selected dates. It does not add different currencies into one total, and it does not invent open or click events.

Not claimed: a public production URL, a live WhatsApp conversation in this script, a real card charge, an exactly-once guarantee for SMTP or n8n, or that a hosted model's wording is always correct.
