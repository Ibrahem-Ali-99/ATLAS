/**
 * Public pricing copy.
 *
 * Amounts and limits mirror `PLAN_DEFINITIONS` in
 * `apps/api/app/domains/billing/service.py` and `TEST_PRICES` in
 * `apps/api/app/domains/billing/test_catalog.py`. Amounts are US cents.
 * Free has no Stripe price.
 */

export type PublicInterval = "monthly" | "yearly";

export type PublicPlan = {
  code: "free" | "starter" | "pro" | "business";
  name: string;
  seats: number;
  assistantRequests: number;
  knowledgeBytes: number;
  activeWorkflows: number;
  monthlyCents: number | null;
  yearlyCents: number | null;
};

export const publicPlans: readonly PublicPlan[] = [
  {
    code: "free",
    name: "Free",
    seats: 2,
    assistantRequests: 100,
    knowledgeBytes: 1_000_000_000,
    activeWorkflows: 2,
    monthlyCents: null,
    yearlyCents: null,
  },
  {
    code: "starter",
    name: "Starter",
    seats: 5,
    assistantRequests: 1_000,
    knowledgeBytes: 10_000_000_000,
    activeWorkflows: 10,
    monthlyCents: 1_900,
    yearlyCents: 19_000,
  },
  {
    code: "pro",
    name: "Pro",
    seats: 20,
    assistantRequests: 5_000,
    knowledgeBytes: 100_000_000_000,
    activeWorkflows: 50,
    monthlyCents: 4_900,
    yearlyCents: 49_000,
  },
  {
    code: "business",
    name: "Business",
    seats: 100,
    assistantRequests: 25_000,
    knowledgeBytes: 1_000_000_000_000,
    activeWorkflows: 200,
    monthlyCents: 9_900,
    yearlyCents: 99_000,
  },
];

export function formatCatalogUsd(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

export function formatKnowledgeBytes(bytes: number): string {
  if (bytes >= 1_000_000_000_000) {
    return `${bytes / 1_000_000_000_000} TB`;
  }
  if (bytes >= 1_000_000_000) {
    return `${bytes / 1_000_000_000} GB`;
  }
  return `${bytes.toLocaleString("en-US")} bytes`;
}

export function planPrice(plan: PublicPlan, interval: PublicInterval): string {
  if (plan.monthlyCents === null || plan.yearlyCents === null) {
    return "Included";
  }
  return formatCatalogUsd(interval === "monthly" ? plan.monthlyCents : plan.yearlyCents);
}
