# Portfolio release acceptance

Recorded 26 November 2026 on `feature/atlas-product-completion`. The shared API on port 8000 and the web app on port 3000 were not restarted. Browser checks used a disposable database (`atlas_e2e_*`), API port 8011, web port 3011, sandbox billing, and sandbox mail. API checks used `atlas_test`. No live card was charged, and unrestricted WhatsApp or live email was not enabled.

Simulated means a deterministic provider, a sandbox mailbox, or a test double. It is not a call to a paid or customer-facing provider.

## Business journeys

| Journey | Result | How it was verified |
|---|---|---|
| Inquiry, Inbox, lead, qualification, opportunity, and follow-up task | Passed | Browser: website chat creates the contact, inquiry, and lead; CRM qualification and archive survive reload; a workflow creates a task from a new lead; Overview creates an opportunity on a phone-width layout. |
| Appointment proposal, approval, booking, and cancellation | Passed for the simulated path | Browser: the Inbox journey requests an appointment and opens the approval. API: simulated booking and cancellation. Live Google Calendar was not called in this pass. |
| Knowledge, Assistant answer, citation, and proposed action | Passed with the deterministic model | Browser: a disposable document is indexed, cited in the Assistant, and removed from later search. A follow-up draft stays behind approval, and sandbox delivery is recorded. This was not a live Groq call. |
| Campaign, audience, approval, sandbox delivery, and reporting | Passed | Browser: one consented recipient, one sandbox send, and the receipt remains after reload. Not a live Resend send. |
| CRM activity, Analytics, Overview, and CSV export | Passed | Browser: Overview and Analytics follow a CRM change. API: the analytics export is `text/csv`. |
| Invitation, onboarding, team, and permissions | Passed | There is no public self-registration. An administrator invites a teammate through a single-use link, setup is saved, staff settings stay read-only, and another organization cannot see Harbor records. |
| Subscription entitlements, restrictions, and usage limits | Passed for the contract | API: sandbox plan changes apply immediately; Stripe checkout without keys does not grant a paid plan; an unsigned webhook is rejected while billing is in sandbox; failed payment and renewal rules stay covered by the billing suite. A new hosted Stripe checkout was not repeated. |

## Reliability and security

| Check | Result |
|---|---|
| Tenant isolation | Passed. Staff in one organization cannot read another organization's CRM records. Authorization tests passed. |
| Role limits | Passed. Staff cannot change billing or provider settings. |
| Duplicate submission | Passed. A second approval execution does not write again. A second contact with the same email is rejected. |
| Persistence after refresh | Passed for CRM archive, workflow task status, campaign receipt, and a saved provider key. |
| Invalid input and failed requests | Passed. A bad CSRF token does not show success. An incompatible embedding change is rejected and the saved dimensions stay in place. |
| Provider failure and recovery | Passed in simulation. Missing Stripe configuration returns `billing_provider_unavailable` and leaves the Free plan. Provider verification covers success, invalid credentials, and timeout. |
| Desktop and mobile | Passed. The acceptance browser runs include 1440px and 390px layouts, and the narrow workspace opens every page. |
| Controls do what they say | Passed after fixing duplicate profile links, the account menu name, and selectors that still looked for retired labels. |

## Defects corrected in this pass

- Billing and approval tests no longer depend on a developer machine that has Stripe test mode configured, and they no longer open a Stripe checkout while asserting that keys are absent.
- Company, contact, and lead profiles no longer show the same related record twice.
- A company stays open while its record reloads, so archive confirmation is not dismissed.
- A saved provider key and a disabled connection remain visible after refresh.
- Changing embedding dimensions warns that a replacement index is required before the current index can change.

## Blocked

- The shared API was left running, so this pass did not repeat hosted Stripe checkout, the billing portal, or a live renewal.
- Live email, live WhatsApp, and live Google Calendar were not called.
- A React duplicate-key warning appeared while opening pages at a narrow width. Those pages still loaded. The warning was not traced during this acceptance pass. The later qualification found it on Workspace setup: the profile form and the knowledge upload were siblings keyed by the same organization id. Those keys are now distinct, and the release verification walk reports no duplicate key.
