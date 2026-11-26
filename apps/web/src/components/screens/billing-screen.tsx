"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleGauge, CreditCard, FlaskConical } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { changeBilling, getBilling, getBillingPlans, openBillingPortal, type BillingStatus } from "@/lib/billing";
import { useWorkspace } from "@/lib/use-workspace";

export function BillingScreen({ checkout }: { checkout?: "success" | "canceled" }) {
  const { organizationId, role } = useWorkspace();
  return (
    <div className="min-w-0 space-y-6">
      <PageHeader title="Billing" eyebrow="Workspace subscription">
        Review your plan, usage, and billing access.
      </PageHeader>
      {checkout ? (
        <p role="status" className="rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
          {checkout === "success"
            ? "Checkout finished. The subscription updates when Stripe confirms it."
            : "Checkout was canceled. You can start again from your subscription."}
        </p>
      ) : null}
      {organizationId ? <BillingCard key={organizationId} organizationId={organizationId} isAdmin={role === "admin"} /> : null}
    </div>
  );
}

function BillingCard({ organizationId, isAdmin }: { organizationId: string; isAdmin: boolean }) {
  const queryClient = useQueryClient();
  const billing = useQuery({ queryKey: ["billing", organizationId], queryFn: () => getBilling(organizationId) });
  const plans = useQuery({ queryKey: ["billing-plans", organizationId], queryFn: () => getBillingPlans(organizationId) });
  const [planChoice, setSelected] = useState("");
  const [intervalChoice, setInterval] = useState("");
  const [message, setMessage] = useState("");
  const current = billing.data?.subscription;
  const stripe = billing.data?.mode === "stripe";
  const portalAvailable = stripe && billing.data?.portal_available === true;
  const selected = planChoice || current?.plan_code || "";
  const interval = intervalChoice || current?.billing_interval || "monthly";
  const save = useMutation({
    mutationFn: () => changeBilling(organizationId, selected, interval),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["billing", organizationId] });
      if (result.mode === "stripe") {
        window.location.assign(result.checkout_url);
      } else {
        setMessage("Subscription updated in sandbox mode.");
      }
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "Billing update failed."),
  });
  const portal = useMutation({
    mutationFn: () => openBillingPortal(organizationId),
    onSuccess: ({ portal_url }) => {
      window.location.assign(portal_url);
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "Could not open the billing portal."),
  });
  if (billing.isPending) return <section className="rounded-xl border border-border bg-card p-5"><Skeleton className="h-20 w-full" /></section>;
  if (billing.isError) return <section className="rounded-xl border border-border bg-card p-5"><h2 className="mb-3 font-semibold">Billing</h2><RequestError error={billing.error} /></section>;
  return (
  <div className="grid min-w-0 gap-4">
    <div className="flex items-start gap-3 rounded-xl border border-border bg-card px-4 py-3" role="note">
      <FlaskConical className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
      <div><p className="text-sm font-medium">{stripe ? "Stripe test mode" : "Sandbox billing"}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{stripe ? "Checkout uses a Stripe test account and does not create a live charge." : "Plan changes stay in this workspace. Stripe appears after an operator adds a test key, an approved test price, and a signed webhook."}</p></div>
    </div>
    <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[1.25fr_1fr]">
    <section className="min-w-0 rounded-xl border border-border bg-card p-5" aria-labelledby="billing-heading">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex items-start gap-3">
        <div className="grid size-9 place-items-center rounded-md bg-primary/10 text-primary"><CreditCard className="size-4" aria-hidden="true" /></div>
        <div>
          <h2 id="billing-heading" className="text-base font-semibold">Current subscription</h2>
          <p className="mt-1 text-xs text-muted-foreground capitalize">{current?.billing_interval ?? "Billing interval unavailable"}</p>
        </div>
      </div>
      <Badge variant="secondary" className="capitalize">{current?.status ?? "Unavailable"}</Badge>
    </div>
    <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
      <div><dt className="text-xs text-muted-foreground">Current plan</dt><dd className="mt-1 font-medium capitalize">{current?.plan_code}</dd></div>
      <div><dt className="text-xs text-muted-foreground">Current period ends</dt><dd className="mt-1 font-medium">
        {current?.current_period_end ? <time dateTime={current.current_period_end}>{new Date(current.current_period_end).toLocaleDateString()}</time> : "Unavailable"}
      </dd></div>
    </dl>
    {isAdmin ? (
      <div className="mt-4 space-y-3 border-t border-border pt-4">
        {plans.isError ? <RequestError error={plans.error} /> : null}
        <div className="flex flex-wrap items-end gap-3">
          {!portalAvailable ? <><label className="grid gap-1 text-xs font-medium">Billing plan
            <select className="h-9 rounded-md border border-input bg-background px-2 text-sm" value={selected} onChange={(e) => setSelected(e.target.value)} disabled={!plans.data?.length || save.isPending}>
              {(plans.data ?? []).map((plan) => <option key={plan.code} value={plan.code} disabled={stripe && plan.code === "free"}>{plan.name}</option>)}
            </select>
          </label>
          <label className="grid gap-1 text-xs font-medium">Billing interval
            <select className="h-9 rounded-md border border-input bg-background px-2 text-sm" value={interval} onChange={(e) => setInterval(e.target.value)} disabled={save.isPending}>
              <option value="monthly">Monthly</option><option value="yearly">Yearly</option>
            </select>
          </label>
          <Button onClick={() => save.mutate()} disabled={save.isPending || (stripe && selected === "free") || !plans.data?.some((plan) => plan.code === selected)}>{save.isPending ? "Preparing…" : "Choose plan"}</Button>
          </> : <Button variant="outline" onClick={() => portal.mutate()} disabled={portal.isPending}>Manage billing</Button>}
        </div>
      </div>
    ) : null}
    {message ? <p className="mt-3 text-xs text-muted-foreground" role="status">{message}</p> : null}
    </section>
    <BillingUsage billing={billing.data} />
    </div>
  </div>
  );
}

const limits = [
  { key: "seats", label: "Workspace seats" },
  { key: "ai_requests", label: "AI requests this period" },
  { key: "knowledge_storage_bytes", label: "Knowledge storage" },
  { key: "active_workflows", label: "Active workflow runs" },
] as const;

function BillingUsage({ billing }: { billing: BillingStatus }) {
  const format = (value: number, bytes: boolean) => bytes
    ? value >= 1_000_000_000
      ? `${(value / 1_000_000_000).toLocaleString(undefined, { maximumFractionDigits: 1 })} GB`
      : `${(value / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 2 })} MB`
    : value.toLocaleString();

  return (
    <section className="rounded-xl border border-border bg-card p-5" aria-labelledby="billing-usage">
      <h2 id="billing-usage" className="flex items-center gap-2 text-base font-semibold"><CircleGauge className="size-4 text-primary" aria-hidden="true" />Usage availability</h2>
      <p className="mt-1 text-xs text-muted-foreground">Workspace usage and the limits applied by your plan.</p>
      <dl className="mt-4 grid gap-4">
        {limits.map(({ key, label }) => {
          const used = billing.usage[key];
          const limit = billing.plan[key];
          const bytes = key === "knowledge_storage_bytes";
          const reported = typeof used === "number" && typeof limit === "number";
          return (
            <div key={key}>
              <div className="flex flex-wrap items-center justify-between gap-1 text-xs">
                <dt className="font-medium">{label}</dt>
                <dd className="tabular-nums text-muted-foreground">{reported ? `${format(used, bytes)} / ${format(limit, bytes)}` : "Unavailable"}</dd>
              </div>
              {reported && limit > 0 ? <div aria-hidden="true" className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, used / limit * 100)}%` }} />
              </div> : null}
            </div>
          );
        })}
      </dl>
    </section>
  );
}
