# Stripe test-mode activation

Use this procedure when an operator is ready to qualify billing against a Stripe test account. Test mode does not create a live charge. Do not put a live secret key in the deployment. `sk_live_` and `rk_live_` are rejected.

The running application stays in sandbox billing until these settings are loaded by an API process. Checkout does not change the workspace plan. Paid limits apply only after a signed webhook retrieves an active Stripe subscription.

## Prices

ATLAS has four plans. Free has no Stripe price. The paid plans require these six prices, one Stripe price id for each map key. Both intervals of a plan belong on that plan's product. All six prices must use the same currency, or the billing portal cannot switch among them.

| Plan | Map key | Stripe interval | Amount |
| --- | --- | --- | --- |
| Starter | `starter:monthly` | month, count 1 | USD 19.00 |
| Starter | `starter:yearly` | year, count 1 | USD 190.00 |
| Pro | `pro:monthly` | month, count 1 | USD 49.00 |
| Pro | `pro:yearly` | year, count 1 | USD 490.00 |
| Business | `business:monthly` | month, count 1 | USD 99.00 |
| Business | `business:yearly` | year, count 1 | USD 990.00 |

`python -m app.scripts.stripe_test_prices` reads `ATLAS_STRIPE_SECRET_KEY` from the process environment and creates or reuses these prices. It prints the price map and does not print the key. The same command with `--write-env` updates only the billing lines in `.env` and leaves every other integration setting in place. A second run reuses a test product whose metadata is `atlas_plan` plus `atlas_catalog=test`, and a price whose lookup key is `atlas_{plan}_{interval}`, when the amount, currency, and interval still match. A different amount is left untouched.

Checkout checks the shape of a price. Each price must be:

- A test-mode price, with `livemode` false
- Recurring, with `interval_count` of 1
- `month` for a monthly plan, or `year` for a yearly plan
- A positive `unit_amount` in USD
- Without `trial_period_days`

A zero-amount price or a price with a trial is rejected, because either one can mark a subscription active before a card payment.

Use each price id in exactly one map entry. The JSON object is `ATLAS_STRIPE_PRICE_IDS`:

```json
{"starter:monthly":"price_...","starter:yearly":"price_...","pro:monthly":"price_...","pro:yearly":"price_...","business:monthly":"price_...","business:yearly":"price_..."}
```

The portal can offer plan changes for at most 10 products. Keeping both intervals on the same product leaves three products.

## Deployment settings

Set these on the API process. The names are the `ATLAS_` settings. Staging Compose reads the `STAGING_` names in `infrastructure/staging/.env` and passes them through.

| Setting | Value |
| --- | --- |
| `ATLAS_BILLING_PROVIDER` | `stripe` |
| `ATLAS_STRIPE_SECRET_KEY` | `sk_test_...` or a restricted `rk_test_...` |
| `ATLAS_STRIPE_WEBHOOK_SECRET` | The signing secret for this endpoint, `whsec_...` |
| `ATLAS_STRIPE_PRICE_IDS` | The JSON map above, as one line |
| `ATLAS_BILLING_PUBLIC_URL` | The web origin customers use, with no path |

`ATLAS_BILLING_PUBLIC_URL` must be the exact origin of the Billing page. `http://127.0.0.1:3000` and `http://localhost:3000` are different sites. Checkout returns to `{origin}/billing?checkout=success` or `{origin}/billing?checkout=canceled`. The billing portal returns to `{origin}/billing?portal=return`.

A restricted key needs Customers, Checkout Sessions, Prices, Subscriptions, and Billing Portal configurations and sessions.

Reload the API process after the values are present. Until all of `ATLAS_BILLING_PROVIDER=stripe`, a test secret, the webhook secret, and the public URL are set, Billing stays unavailable and reports `billing_provider_unavailable`. An empty or invalid price map reports `billing_price_unavailable` when an administrator chooses a plan.

## Webhook

Register one endpoint:

`{API origin}/api/v1/billing/webhooks/stripe`

Subscribe to:

- `checkout.session.completed`
- `checkout.session.async_payment_succeeded`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.paid`
- `invoice.payment_failed`

Send the raw body and the `Stripe-Signature` header. The signature must be current within Stripe's five-minute tolerance. Events with `livemode` true are rejected. The handler reads the live test subscription after verifying the signature, so a delayed older event cannot put a replaced plan back.

The same event id and body returns `already_processed` and does not apply twice. The same event id with a different body returns `409 webhook_event_conflict`. A failure while reading Stripe rolls the receipt back, and the provider can retry that event.

### Local forwarding with the Stripe CLI

The local API from `scripts/start-dev.ps1` listens at `http://127.0.0.1:8000`. Forward only test-mode events to that process. Do not forward to a live-mode endpoint, and do not put the signing secret in the repository.

Install the CLI once. On this Windows host it is not already on `PATH`:

```powershell
winget install --id Stripe.StripeCli -e --accept-package-agreements --disable-interactivity
```

Open a new shell so `stripe` resolves. Sign the CLI into the same Stripe test account that owns the secret key. `stripe login` opens a browser. It does not belong in a script or a commit.

Start the forwarder in its own window. Leave the existing API process running. The forwarder is a separate process:

```powershell
stripe listen `
  --events checkout.session.completed,checkout.session.async_payment_succeeded,customer.subscription.created,customer.subscription.updated,customer.subscription.deleted,invoice.paid,invoice.payment_failed `
  --forward-to http://127.0.0.1:8000/api/v1/billing/webhooks/stripe
```

The CLI prints a `whsec_` signing secret for this listener. Put that value in `ATLAS_STRIPE_WEBHOOK_SECRET` for the API process, together with the test secret key, `ATLAS_BILLING_PROVIDER=stripe`, the price map, and `ATLAS_BILLING_PUBLIC_URL=http://127.0.0.1:3000` when the browser uses that origin. Reload the API after those values are present. Events that arrive before the reload are rejected, because sandbox mode does not accept Stripe webhooks.

Stop the forwarder with Ctrl+C. Stopping it does not cancel a Stripe subscription. A new `stripe listen` session prints a new `whsec_` value. The API must use the secret from the listener that is running.

## What the customer sees

An administrator opens Billing.

- Sandbox mode still changes the plan inside the workspace. That path is unchanged.
- Stripe test mode shows the test-mode notice. Choosing a paid plan opens Checkout and leaves the current plan in place. The page tells the administrator that Stripe confirms the subscription after payment.
- After confirmation, Manage billing opens the customer portal. The portal shows invoices, allows a payment-method update, and updates the customer name, email, and address. Plan changes and cancellation are part of that portal session.
- Upgrades are invoiced immediately. The higher plan is stored only after Stripe reports the new price on an active subscription. Downgrades, and a change from yearly to monthly, wait until the end of the paid period. Cancellation also waits until the end of that period, and the paid limits stay until then.
- A failed invoice moves the subscription to past due. The recorded plan remains visible, and the workspace uses Free limits until a later event shows the subscription active again. Update the card from Manage billing. A second checkout is not offered while the payment is past due.
- Trialing, incomplete, expired, and canceled subscriptions use Free limits. Trialing waits for an active subscription. Canceled and expired subscriptions can start Checkout again. The portal remains available for invoices.
- If the recorded period ends and no renewal arrives within two hours, paid limits stop until Stripe confirms the new period. Sandbox plans are not expired by that rule.
- Usage for AI requests counts from the current period start. Seats, knowledge storage, and active workflow runs use the limits of the plan currently in effect.
- A staff member can read Billing. Only an administrator can choose a plan or open the portal.

## Acceptance

Use a disposable organization and the test cards below. Do not use a live card.

1. Billing shows Stripe test mode before checkout.
2. Complete Checkout for one paid price with `4242 4242 4242 4242`, any future expiry, and any CVC. Before the webhook arrives, the plan and limits stay where they were.
3. After the signed event, the plan, interval, period, and limits match that price. Manage billing is available.
4. Send the same signed event again. The response is `already_processed`, and the plan does not change a second time.
5. Open Manage billing. Confirm invoice history and the return to `/billing?portal=return`.
6. Schedule a downgrade or a cancellation at period end. The current paid limits remain, and Billing says when the cancellation takes effect.
7. Start an upgrade. The higher limits appear only after Stripe confirms the paid invoice.
8. Cause a failed renewal. Card `4000 0000 0000 0341` attaches and then fails later invoice charges. Past due Billing uses Free limits and keeps the recorded plan. After the invoice is paid, the paid limits return.
9. Card `4000 0000 0000 9995` declines. Checkout does not grant the paid plan.
10. After cancellation, Billing shows Free limits and offers a new Checkout. The old subscription does not stay entitled.

Record the workspace, the test-mode customer, the time, and the observed plan before and after each event. Leave the secret key, webhook secret, and price ids out of the evidence notes.
