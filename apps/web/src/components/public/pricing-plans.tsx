"use client";

import { useState } from "react";

import {
  formatKnowledgeBytes,
  planPrice,
  publicPlans,
  type PublicInterval,
} from "@/lib/public-catalog";

export function PricingPlans() {
  const [interval, setInterval] = useState<PublicInterval>("monthly");

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <div role="group" aria-label="Billing interval" className="inline-flex rounded-lg border border-border bg-card p-1">
          {(["monthly", "yearly"] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={interval === value}
              className={`rounded-md px-3 py-1.5 text-sm font-medium ${interval === value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}
              onClick={() => setInterval(value)}
            >
              {value === "monthly" ? "Monthly" : "Yearly"}
            </button>
          ))}
        </div>
        <p className="text-sm text-muted-foreground">Yearly amounts are the catalog prices, charged once per year.</p>
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {publicPlans.map((plan) => (
          <article key={plan.code} className="flex flex-col rounded-xl border border-border bg-card p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
            <h3 className="text-lg font-semibold">{plan.name}</h3>
            <p className="mt-3 text-3xl font-semibold tracking-tight">
              {planPrice(plan, interval)}
              {plan.monthlyCents !== null ? (
                <span className="ml-1 text-sm font-normal text-muted-foreground">
                  / {interval === "monthly" ? "month" : "year"}
                </span>
              ) : null}
            </p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {plan.code === "free"
                ? "Created with the workspace. No Stripe price."
                : "Stripe test price. Entitlements change after the provider confirms the subscription."}
            </p>
            <ul className="mt-5 grid gap-2 text-sm leading-6">
              <li>{plan.seats} seats</li>
              <li>{plan.assistantRequests.toLocaleString("en-US")} assistant requests</li>
              <li>{formatKnowledgeBytes(plan.knowledgeBytes)} knowledge storage</li>
              <li>{plan.activeWorkflows} active workflows</li>
            </ul>
          </article>
        ))}
      </div>
      <div className="mt-6 overflow-x-auto rounded-xl border border-border">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <caption className="sr-only">Plan limits and catalog prices</caption>
          <thead className="bg-muted text-muted-foreground">
            <tr>
              <th scope="col" className="px-4 py-3 font-medium">Limit</th>
              {publicPlans.map((plan) => (
                <th key={plan.code} scope="col" className="px-4 py-3 font-medium">{plan.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <PriceRow label="Monthly catalog price" values={publicPlans.map((plan) => plan.monthlyCents === null ? "None" : planPrice(plan, "monthly"))} />
            <PriceRow label="Yearly catalog price" values={publicPlans.map((plan) => plan.yearlyCents === null ? "None" : planPrice(plan, "yearly"))} />
            <PriceRow label="Seats" values={publicPlans.map((plan) => String(plan.seats))} />
            <PriceRow label="Assistant requests" values={publicPlans.map((plan) => plan.assistantRequests.toLocaleString("en-US"))} />
            <PriceRow label="Knowledge storage" values={publicPlans.map((plan) => `${formatKnowledgeBytes(plan.knowledgeBytes)} (${plan.knowledgeBytes.toLocaleString("en-US")} bytes)`)} />
            <PriceRow label="Active workflows" values={publicPlans.map((plan) => String(plan.activeWorkflows))} />
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PriceRow({ label, values }: { label: string; values: string[] }) {
  return (
    <tr className="border-t border-border">
      <th scope="row" className="px-4 py-3 font-medium">{label}</th>
      {values.map((value, index) => (
        <td key={`${label}-${index}`} className="px-4 py-3 text-muted-foreground">{value}</td>
      ))}
    </tr>
  );
}
