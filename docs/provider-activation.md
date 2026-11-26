# Provider activation and acceptance

Use a disposable workspace, approved test identities, and an HTTPS origin that the providers can reach. Keep the default staging stack in sandbox mode. External transport checks require separate approval before enabling live flags or sending to a real recipient. Store keys in the deployment secret store or encrypted workspace integration settings.

| Connection | Configure | Verify and disconnect |
| --- | --- | --- |
| Website chat | Open Integrations → Website chat, allow the exact storefront origin, and install the displayed embed. | Send a visitor message from the storefront and reply from Inbox. Pause the embed and verify that new sessions stop and existing threads remain readable. |
| Inbound email | Set an independent `ATLAS_INBOX_WEBHOOK_SECRET`. Configure a trusted mail gateway to route verified envelope-recipient addresses to the appropriate workspace callback. | Send a test message and reply. Check threading and one-copy retry behavior. Remove the gateway route to disconnect it, and rotate the signing secret if exposed. |
| Approved SMTP replies | Configure an authenticated TLS or STARTTLS relay in Integrations → Email and verify the sending domain. After approval to test live delivery, set `ATLAS_EMAIL_MODE=live` and `ATLAS_EMAIL_LIVE_ENABLED=true`, allow the exact relay hostname in `ATLAS_SMTP_LIVE_HOSTS`, and enable approved live replies in the workspace. | Test connectivity. Link an Inbox conversation, contact, lead, and inquiry for an operational test contact. Approve a reply and verify receipt in the test mailbox. Disconnect Email and confirm a new approved execution is blocked. |
| Resend campaigns | Use a Resend account dedicated to campaign feedback. Save its key under Email. An administrator test from `onboarding@resend.dev` can confirm the sending key before any domain is verified. Register the sender domain with a full-access key, publish DNS records, and run verification. Set `ATLAS_CAMPAIGN_PUBLIC_URL` to the HTTPS API origin. Provide a separate, stable `ATLAS_CAMPAIGN_LINK_SECRET` for links and `ATLAS_RESEND_CAMPAIGN_WEBHOOK_SECRET` for signed feedback. | The administrator test stays separate from customer mail and campaigns. After approval, enable `ATLAS_CAMPAIGN_LIVE_ENABLED` alongside live email and send to one consented operational test contact. Confirm provider acceptance and delivery feedback. Unsubscribe from the delivered message and confirm the next audience preview excludes the contact. Disable the campaign gate and disconnect Email to stop new sends. |
| WhatsApp | Save Business Account ID, phone number ID, and access token in Integrations. Set separate `ATLAS_WHATSAPP_WEBHOOK_VERIFY_TOKEN` and `ATLAS_WHATSAPP_WEBHOOK_APP_SECRET` in the host environment. Use the workspace callback shown in Integrations and subscribe to messages. | Verify the connection and send a message from an allowed test recipient. While live messaging is off, an administrator can approve that recipient for one session reply from Meta's test number. The reply still requires approval, cannot use a template, and does not enable customer messaging. With separate approval, enable `ATLAS_WHATSAPP_LIVE_ENABLED` in a live email environment and approve one reply on a linked operational CRM record inside the service window. Verify receipt and status. Disconnect the integration and remove the Meta subscription if dedicated to this workspace. |
| n8n | Install the versioned workflow with the procedure in [deployment.md](deployment.md). Issue a signing key from Integrations and place it in the workflow credential store. | Create an operational test lead. Verify workflow execution, signed callback, and the resulting record. Disconnect or rotate the key and confirm the previous key cannot authorize new callbacks. |
| Chat and embeddings | Configure OpenAI or Groq for chat and OpenAI or Ollama for embeddings. Verify each connection. Match the existing embedding model and dimensions when retaining an index. | Upload a small reference document, let it index, and verify a cited answer from Setup. Disconnect or revoke the provider and confirm that its unavailable state is visible. |
| Google Calendar | Follow [Next milestone — Google Calendar OAuth](#next-milestone--google-calendar-oauth). The product already implements the connection, availability check, private event, cancellation, and disconnect. | Connect a dedicated test account from Integrations. Create a busy event in Google, verify ATLAS flags the conflict, then request and approve a free slot from a CRM lead with an inquiry. Confirm the private event, cancel it in ATLAS, and verify removal in Google before disconnecting and revoking the grant. |
| Stripe | Follow the [staging procedure](staging-readiness.md) with test-mode keys, an approved test price, and a signed webhook. | Complete a test checkout and verify subscription changes after the signed event. Check the customer portal, duplicate webhook handling, and cancellation. |

The [engineering handoff](ATLAS_ENGINEERING_HANDOFF.md) lists the required environment variables and startup commands. The [product backlog](product-completion-backlog.md) tracks which external checks still need evidence.

## Customer checklist

WhatsApp, Resend, Google Calendar, and Stripe stay inactive until the customer has the provider account and an operator has prepared the deployment. Values entered in Integrations or Billing do not enable live delivery.

| Service | Customer, in the product | Operator, on the deployment |
| --- | --- | --- |
| WhatsApp | Enter the Business Account ID, phone number ID, and access token, then test the connection. Give Meta the callback path shown in Integrations. Approve one test recipient only after that number has messaged the workspace and is on Meta's allowed recipient list. | Publish the API over HTTPS. Set `ATLAS_WHATSAPP_WEBHOOK_VERIFY_TOKEN` and `ATLAS_WHATSAPP_WEBHOOK_APP_SECRET`. Leave `ATLAS_WHATSAPP_LIVE_ENABLED` unset. A restricted test reply does not turn it on. |
| Resend | Save a sending key under Email. Approve the Resend account-owner address, then send the administrator test from `onboarding@resend.dev` to that address or an official Resend test recipient. Register a sending domain only with a full-access key, publish its DNS records, and run verification. | Set `ATLAS_CAMPAIGN_PUBLIC_URL`, `ATLAS_CAMPAIGN_LINK_SECRET`, and `ATLAS_RESEND_CAMPAIGN_WEBHOOK_SECRET`. Live campaigns also need `ATLAS_EMAIL_MODE=live`, `ATLAS_EMAIL_LIVE_ENABLED=true`, and `ATLAS_CAMPAIGN_LIVE_ENABLED=true`. A verified administrator test does not enable them. |
| Google Calendar | Choose Connect Google, grant Calendar access, and run Test connection. | Enable the Calendar API and create a web OAuth client. Set `ATLAS_GOOGLE_CALENDAR_CLIENT_ID`, `ATLAS_GOOGLE_CALENDAR_CLIENT_SECRET`, `ATLAS_GOOGLE_CALENDAR_WEB_ORIGIN`, and `ATLAS_GOOGLE_CALENDAR_REDIRECT_URI` ending in `/api/v1/calendar/google/callback`. |
| Stripe | On Billing, choose a plan after test mode is shown and complete checkout. | Provide a test-mode secret, an approved test price, and a signed webhook. Test checkout does not create a live charge. |

## Next milestone — Google Calendar OAuth

Use the existing Calendar connection. Do not add a second OAuth client, token store, or booking path. This procedure does not enable live email, WhatsApp, Resend, or Stripe.

The API treats Calendar as available only when public demo mode is off and all four settings are present. `ATLAS_CALENDAR_MODE` stays `simulation`; a saved Google connection is what changes the workspace from the local calendar to Google. The client secret is a deployment setting. Integrations does not accept it.

### Operator

1. In a Google Cloud project for this workspace, enable the Google Calendar API.
2. Configure the OAuth consent screen. While the app is in testing, add the dedicated Google account as a test user.
3. Create an OAuth client of type Web application.
4. Register one authorized redirect URI. For this local API it is `http://127.0.0.1:8000/api/v1/calendar/google/callback`. On another host, use that API origin with the same path. The value must use `https`, or `http` only when the host is `localhost`, `127.0.0.1`, or `::1`. It cannot include a username, password, query, or fragment, and the path must be exactly `/api/v1/calendar/google/callback`.
5. Set these deployment values and reload the API process so it reads them:
   - `ATLAS_GOOGLE_CALENDAR_CLIENT_ID` — the OAuth client id
   - `ATLAS_GOOGLE_CALENDAR_CLIENT_SECRET` — the OAuth client secret
   - `ATLAS_GOOGLE_CALENDAR_REDIRECT_URI` — the same redirect URI registered in Google
   - `ATLAS_GOOGLE_CALENDAR_WEB_ORIGIN` — `http://127.0.0.1:3000` for this local web app, or the web origin elsewhere, with an empty path
6. Keep the secret out of the repository, screenshots, and evidence notes.

### Customer

1. Sign in as an organization administrator and open Integrations in the same browser.
2. Google Calendar offers **Connect Google** once the four settings are loaded. Until then the card says an operator must register Google sign-in.
3. Choose **Connect Google** and grant every requested permission. The request asks for offline access and consent, and it is bound to this server session for 10 minutes. The Google account must own its primary calendar.
4. Google returns to the API, which redirects to `/integrations?calendar=connected`. **Cancelled** and **failed** use the same page with `calendar=cancelled` or `calendar=failed`. Start again from **Connect Google** after either result.
5. Choose **Test connection**. The check covers the next hour on the connected calendar.

### Acceptance

1. Put a busy event on the connected Google calendar.
2. Open a CRM lead that already has an inquiry and choose **Request appointment**.
3. Enter that busy interval and choose **Check availability**. The result must say **Busy** on Google Calendar and in ATLAS.
4. Enter a free interval, check availability, and choose **Request approval**.
5. On Approvals, approve the request and then choose **Execute**. Execution checks Google again and creates a private event. Approve alone does not create it.
6. Confirm the private event in Google, cancel the booking in ATLAS, and confirm that Google removed it.
7. Choose **Disconnect**. When the card says the grant is still present, remove ATLAS access from the Google account.

Editing that event directly in Google does not update the ATLAS booking. A later connection must be started by an administrator in the browser session that will receive the callback.

## Email callback contracts

- **Inbound gateway.** POST JSON to `/api/v1/organizations/{organization_id}/inbox/webhooks/inbound` with `message_id`, `sender`, `recipient`, `subject`, and `body`. Send Unix seconds in `X-Atlas-Inbox-Timestamp`. Set `X-Atlas-Inbox-Signature` to the hex HMAC-SHA256 of the UTF-8 prefix `v1.{organization_id}.{timestamp}.` followed by the exact body bytes. Use a stable provider message ID and re-sign each retry with a current timestamp. Upgrade gateways that still sign only the request body before forwarding mail.
- **Campaign feedback.** Subscribe to `email.delivered`, `email.bounced`, `email.complained`, and `email.failed` at `/api/v1/hooks/campaign-delivery/resend`. Preserve the exact body and Svix headers. When an event arrives before the send receipt is recorded, the endpoint requests a provider retry. An ambiguous send stays in review. Inspect the provider before attempting a replacement.
- **Preference links.** Forward `/api/v1/campaign-preferences/*` to the API and redact this path in proxy access logs. Preserve the link signing key across routine deployments. Verify both the confirmation page and the mailbox’s one-click unsubscribe on a real Resend test message. Confirm that the received DKIM signature covers both unsubscribe headers before qualifying the mailbox flow.

When changing an embedding model or vector width, use **Build replacement index** under Embeddings. Confirm progress, search while it builds, and verify a cited answer after activation. The provider endpoint must match the deployment’s configured embedding endpoint, the workspace’s existing endpoint, OpenAI’s standard endpoint, or Ollama on this machine.

Record the workspace, provider account, time, message or run ID, observed result, and disconnect result. Keep credentials and recipient preference URLs out of evidence files. Google Calendar checks current availability and writes and cancels ATLAS events on the connected primary calendar. Editing an ATLAS booking directly in Google is outside the synchronization supported here.
