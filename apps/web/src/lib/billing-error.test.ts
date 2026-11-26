import assert from "node:assert/strict";
import test from "node:test";

// @ts-expect-error Node's strip-types test runner requires explicit TypeScript extensions.
import { billingErrorMessage } from "./billing-error.ts";

test("stripe configuration errors stay customer-facing", () => {
  assert.equal(
    billingErrorMessage({
      code: "billing_provider_unavailable",
      message: "Stripe test-mode billing is not configured",
    }),
    "Stripe test mode is not ready. An operator needs to add the test key, prices, and webhook secret.",
  );
  assert.equal(
    billingErrorMessage({
      code: "subscription_already_exists",
      message: "Manage your subscription in the billing portal",
    }),
    "This workspace already has a Stripe subscription. Use Manage billing to change it.",
  );
});

test("an unknown billing error keeps the API message", () => {
  const error = new Error("The payment provider returned an invalid period");
  Object.assign(error, { code: "billing_period_unavailable" });
  assert.equal(billingErrorMessage(error), "The payment provider returned an invalid period");
});

test("a non-api failure has a stable billing message", () => {
  assert.equal(billingErrorMessage(null), "Billing could not be updated.");
});
