import { apiFetch } from "@/lib/api";
import { billingErrorMessage } from "@/lib/billing-error";

export { billingErrorMessage };

export type BillingAttention =
  | "payment_failed"
  | "canceled"
  | "expired"
  | "payment_unconfirmed"
  | "cancels_at_period_end"
  | "period_lapsed";

export type BillingStatus = {
  mode: "sandbox" | "stripe";
  portal_available: boolean;
  checkout_available: boolean;
  attention: BillingAttention | null;
  subscription: {
    plan_code: string;
    entitled_plan_code: string;
    billing_interval: string;
    status: string;
    provider: string;
    cancels_at_period_end: boolean;
    current_period_start: string | null;
    current_period_end: string | null;
  };
  plan: Record<string, number | string>;
  usage: Record<string, number>;
};

export type BillingPlan = { code: string; name: string; entitlements: Record<string, number | string> };

export function getBilling(id: string) {
  return apiFetch<BillingStatus>(`/api/v1/organizations/${id}/billing`);
}

export function getBillingPlans(id: string) {
  return apiFetch<BillingPlan[]>(`/api/v1/organizations/${id}/billing/plans`);
}

export function changeBilling(id: string, plan_code: string, billing_interval: string) {
  return apiFetch<{ checkout_url: string; mode: string; status: string }>(
    `/api/v1/organizations/${id}/billing/checkout`,
    { method: "POST", body: JSON.stringify({ plan_code, billing_interval }) },
  );
}

export function openBillingPortal(id: string) {
  return apiFetch<{ portal_url: string }>(`/api/v1/organizations/${id}/billing/portal`, { method: "POST" });
}
