# Interactive demo access

The public site can open the real ATLAS workspace without a published password. `POST /api/v1/demo/sessions` creates one organization, one user, and one HttpOnly session. The organization slug starts with `harbor-visitor-`. The user belongs only to that organization. A second visitor receives a different organization and cannot read the first.

The session lasts 45 minutes. The browser cookie uses the same lifetime. `POST /api/v1/demo/sessions/restart` deletes that visitor organization and starts another. Expired visitor organizations are removed when a new session starts. Cleanup refuses every slug that does not use the visitor prefix, so Atlas Demo, Northwind, and any other workspace stay in place.

Harbor & Co. rows are written with the existing CRM, inbox, knowledge, workflow, campaign, and assistant models. The knowledge file is stored ready, with a deterministic embedding, so the ingestion worker does not send it to a paid provider. Chat and embedding calls for a visitor organization use the deterministic stand-in even when the process has a live model key.

## Limits

Each API process allows 8 launches per direct client address per 15 minutes. The address is the connection peer. A forwarded header is not trusted, the same rule as login. A process also keeps at most 40 active visitor organizations, 400 requests on a session, 12 assistant replies, 3 documents, and 500 KB of knowledge files. An upload larger than 200 KB is refused.

## What a visitor cannot do

Integration configuration, billing checkout, billing portal, invitations, webhook keys, and Google Calendar connect return `demo_restricted`. Campaign scheduling is refused, and a queued visitor delivery is skipped instead of sent. Approval execution of a customer message or an appointment is refused before an intent is staged. A workflow that would call n8n is recorded as simulated and the webhook is not called. Login and password reset do not accept the generated visitor address.

## Production

A production process does not start demo sessions unless `ATLAS_PUBLIC_DEMO=true` and the process has no live email, live campaigns, live WhatsApp, n8n URL, paid model key, Stripe key, or Google Calendar client secret. Development and test can start sessions because those side effects are refused for the visitor organization. Do not publish the development seed passwords, and do not add the visitor to Atlas Demo or Northwind.

Leave the development database URL and provider credentials unchanged. The visitor organization is a tenant in the API database the process already uses. It is not the development workspace.
