const billingErrors: Record<string, string> = {
  billing_provider_unavailable:
    "Stripe test mode is not ready. An operator needs to add the test key, prices, and webhook secret.",
  billing_price_unavailable:
    "That plan is not available for checkout. Choose another plan or ask an operator to check the Stripe prices.",
  subscription_already_exists:
    "This workspace already has a Stripe subscription. Use Manage billing to change it.",
  checkout_already_open:
    "A checkout is already open. Finish that checkout, or wait for it to expire, before starting another.",
  billing_portal_unavailable: "The billing portal opens after Stripe confirms a subscription.",
  billing_provider_error: "Stripe could not complete that request. Wait a moment and try again.",
  entitlement_limit_reached: "This workspace has reached a plan limit.",
  forbidden: "Only an organization administrator can change billing.",
  network_error: "The API is unreachable. Start the backend and try again.",
};

export function billingErrorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "code" in error) {
    const code = error.code;
    if (typeof code === "string" && code in billingErrors) {
      return billingErrors[code];
    }
  }
  if (error instanceof Error && error.message) return error.message;
  return "Billing could not be updated.";
}
