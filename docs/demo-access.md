# Interactive demo access

The public site can open the real ATLAS workspace without a published password. `POST /api/v1/demo/sessions` creates one organization, one user, and one HttpOnly session. The organization slug starts with `harbor-visitor-`. The user belongs only to that organization. A second visitor receives a different organization and cannot read the first.

The session lasts 45 minutes. The browser cookie uses the same lifetime. `POST /api/v1/demo/sessions/restart` deletes that visitor organization and starts another. Expired visitor organizations are removed when a new session starts. Cleanup refuses every slug that does not use the visitor prefix, so Atlas Demo, Northwind, and any other workspace stay in place.

Harbor & Co. rows are written with the existing CRM, inbox, knowledge, workflow, campaign, and assistant models. The library is stored ready, with deterministic embeddings, so the ingestion worker does not send it to a paid provider. Chat and embedding calls for a visitor organization use the deterministic stand-in even when the process has a live model key. That stand-in returns the first line of the first retrieved passage. The bonded note starts with the north-pier sentence, so the prepared question returns that sentence. The assistant screen says demonstration mode, and the provider status for that organization reports the stand-in rather than a paid model configured on the process.

The prepared workspace is a fictional logistics book: 20 companies, 40 contacts, 50 leads, 30 opportunities, 40 conversations, 35 tasks, 20 simulated appointments, 15 service notes, 8 inactive workflows, recorded workflow runs, and campaign rows whose delivery status is `simulated`. Dates span about 120 days, so a 90-day analytics window reads stored rows. Records that have an origin are `demo`. A visitor-created company, document, or reply stays `operational`. Analytics on Operational therefore omits the prepared leads. All records includes them. Opportunities, tasks, inbox threads, and campaigns have no origin column, so those lists show the prepared rows in every scope. Appointment rows use provider `simulation` and have no external event id. Campaign rows are not queued.

## Limits

Each API process allows 8 launches per direct client address per 15 minutes. The address is the connection peer. `X-Forwarded-For`, `X-Real-IP`, and `Forwarded` do not choose a different counter, the same rule as login. Behind Caddy that peer is Caddy, so the launch counter is shared by everyone who reaches that one API process. Do not move the counter onto a forwarded header.

A process also keeps at most 40 active visitor organizations. The count and the insert share one database advisory lock, so two launches at the same moment cannot both pass the limit. A session also allows 400 requests, 12 assistant replies, 3 documents, and 500 KB of knowledge files. An upload larger than 200 KB is refused. Those document, storage, and assistant limits count what the visitor adds. The prepared service notes and the one prepared assistant reply do not use up that allowance. Workflow definitions are stored inactive. The free plan still allows 2 active workflows. Activating a third returns the plan limit.

## What a visitor cannot do

Integration configuration, billing checkout, billing portal, invitations, webhook keys, and Google Calendar connect return `demo_restricted`. Campaign scheduling is refused, and a queued visitor delivery is skipped instead of sent. Approval execution of a customer message or an appointment is refused before an intent is staged. A workflow that would call n8n is recorded as simulated and the webhook is not called. Login and password reset do not accept the generated visitor address.

## Production

A production process does not start demo sessions unless `ATLAS_PUBLIC_DEMO=true` and the process has no live email, live campaigns, live WhatsApp, n8n URL, paid model key, Stripe key, or Google Calendar client secret. Development and test can start sessions because those side effects are refused for the visitor organization. Do not publish the development seed passwords, and do not add the visitor to Atlas Demo or Northwind.

Leave the development database URL and provider credentials unchanged. The visitor organization is a tenant in the API database the process already uses. It is not the development workspace.
