"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleGauge, CreditCard, FlaskConical } from "lucide-react";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  billingErrorMessage,
  changeBilling,
  getBilling,
  getBillingPlans,
  openBillingPortal,
  type BillingAttention,
  type BillingPlan,
  type BillingStatus,
} from "@/lib/billing";
import { useWorkspace } from "@/lib/use-workspace";

const CONFIRMATION_WAIT_MS = 30_000;

export function BillingScreen({
  checkout,
  portalReturn = false,
}: {
  checkout?: "success" | "canceled";
  portalReturn?: boolean;
}) {
  const { organizationId, role } = useWorkspace();
  return (
    <div className="min-w-0 space-y-6">
      <PageHeader title="Billing" eyebrow="Workspace subscription">
        Review your plan, usage, and billing access.
      </PageHeader>
      {checkout === "success" ? (
        <p role="status" className="rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
          Checkout finished. This page updates when the payment is confirmed. Your current plan stays in place until then.
        </p>
      ) : null}
      {checkout === "canceled" ? (
        <p role="status" className="rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
          Checkout was canceled. You can start again from your subscription.
        </p>
      ) : null}
      {portalReturn ? (
        <p role="status" className="rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
          The billing portal is closed. Plan, payment, and cancellation changes appear here after they are confirmed.
        </p>
      ) : null}
      {organizationId ? (
        <BillingCard
          key={organizationId}
          organizationId={organizationId}
          isAdmin={role === "admin"}
          watchProvider={checkout === "success" || portalReturn}
        />
      ) : null}
    </div>
  );
}

function BillingCard({
  organizationId,
  isAdmin,
  watchProvider,
}: {
  organizationId: string;
  isAdmin: boolean;
  watchProvider: boolean;
}) {
  const queryClient = useQueryClient();
  const billing = useQuery({ queryKey: ["billing", organizationId], queryFn: () => getBilling(organizationId) });
  const plans = useQuery({ queryKey: ["billing-plans", organizationId], queryFn: () => getBillingPlans(organizationId) });
  const [planChoice, setSelected] = useState("");
  const [intervalChoice, setInterval] = useState("");
  const [message, setMessage] = useState("");
  const [messageIsError, setMessageIsError] = useState(false);
  const [waitExpired, setWaitExpired] = useState(false);
  const current = billing.data?.subscription;
  const stripe = billing.data?.mode === "stripe";
  const portalAvailable = billing.data?.portal_available === true;
  const checkoutAvailable = billing.data?.checkout_available !== false;
  const paidPlans = (plans.data ?? []).filter((plan) => !stripe || plan.code !== "free");
  const selected = planChoice || (stripe && current?.plan_code === "free" ? paidPlans[0]?.code : current?.plan_code) || "";
  const interval = intervalChoice || current?.billing_interval || "monthly";
  const unchanged = selected === current?.plan_code && interval === (current?.billing_interval || "monthly");
  const report = (error: unknown, fallback: string) => {
    const text = billingErrorMessage(error);
    setMessage(text || fallback);
    setMessageIsError(true);
  };
  const save = useMutation({
    mutationFn: () => changeBilling(organizationId, selected, interval),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["billing", organizationId] });
      if (result.mode === "stripe") {
        window.location.assign(result.checkout_url);
        return;
      }
      setMessageIsError(false);
      setMessage("Subscription updated in sandbox mode.");
    },
    onError: (error) => report(error, "Billing update failed."),
  });
  const portal = useMutation({
    mutationFn: () => openBillingPortal(organizationId),
    onSuccess: ({ portal_url }) => {
      window.location.assign(portal_url);
    },
    onError: (error) => report(error, "Could not open the billing portal."),
  });
  useEffect(() => {
    if (!watchProvider) return;
    const refresh = window.setInterval(() => {
      void queryClient.invalidateQueries({ queryKey: ["billing", organizationId] });
    }, 2000);
    const timeout = window.setTimeout(() => {
      setWaitExpired(true);
      window.clearInterval(refresh);
    }, CONFIRMATION_WAIT_MS);
    return () => {
      window.clearTimeout(timeout);
      window.clearInterval(refresh);
    };
  }, [organizationId, queryClient, watchProvider]);
  if (billing.isPending) return <section className="rounded-xl border border-border bg-card p-5"><Skeleton className="h-20 w-full" /></section>;
  if (billing.isError) return <section className="rounded-xl border border-border bg-card p-5"><h2 className="mb-3 font-semibold">Billing</h2><RequestError error={billing.error} /></section>;
  const attention = billing.data.attention;
  const selectedPlan = plans.data?.find((plan) => plan.code === selected);
  return (
    <div className="grid min-w-0 gap-4">
      <div className="flex items-start gap-3 rounded-xl border border-border bg-card px-4 py-3" role="note">
        <FlaskConical className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
        <div>
          <p className="text-sm font-medium">{stripe ? "Stripe test mode" : "Sandbox billing"}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {stripe
              ? "Checkout uses a Stripe test account and does not create a live charge."
              : "Plan changes stay in this workspace until Stripe billing is connected."}
          </p>
        </div>
      </div>
      {attention ? <BillingAttentionNotice attention={attention} subscription={billing.data.subscription} /> : null}
      {watchProvider && waitExpired && current?.provider !== "stripe" ? (
        <p role="status" className="rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
          The payment has not been confirmed yet. Refresh this page after the receipt arrives. The current plan stays in place until then.
        </p>
      ) : null}
      <div className="billing-grid">
        <article className="settings-card current-plan" aria-labelledby="billing-heading">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <div className="grid size-9 place-items-center rounded-md bg-primary/10 text-primary"><CreditCard className="size-4" aria-hidden="true" /></div>
              <div>
                <h2 id="billing-heading" className="text-base font-semibold">Current subscription</h2>
                <p className="mt-1 text-xs capitalize text-muted-foreground">{current?.billing_interval ?? "Billing interval unavailable"}</p>
              </div>
            </div>
            <Badge variant="secondary" className="capitalize">{(current?.status ?? "Unavailable").replaceAll("_", " ")}</Badge>
          </div>
          <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-muted-foreground">Current plan</dt>
              <dd className="mt-1 font-medium capitalize">{current?.plan_code}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Limits in effect</dt>
              <dd className="mt-1 font-medium capitalize">{current?.entitled_plan_code}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Current period started</dt>
              <dd className="mt-1 font-medium"><BillingDate value={current?.current_period_start} /></dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Current period ends</dt>
              <dd className="mt-1 font-medium"><BillingDate value={current?.current_period_end} /></dd>
            </div>
          </dl>
          {stripe && current?.provider !== "stripe" ? (
            <p className="mt-4 text-xs text-muted-foreground">Checkout does not change this plan. The new plan starts after payment is confirmed.</p>
          ) : null}
          {isAdmin ? (
            <div className="mt-4 space-y-3 border-t border-border pt-4">
              {plans.isError ? <RequestError error={plans.error} /> : null}
              <div className="flex flex-wrap items-end gap-3">
                {checkoutAvailable ? (
                  <>
                    <label className="grid gap-1 text-xs font-medium">Billing plan
                      <select className="h-9 rounded-md border border-input bg-background px-2 text-sm" value={selected} onChange={(event) => setSelected(event.target.value)} disabled={!plans.data?.length || save.isPending}>
                        {(plans.data ?? []).map((plan) => <option key={plan.code} value={plan.code} disabled={stripe && plan.code === "free"}>{plan.name}</option>)}
                      </select>
                    </label>
                    <label className="grid gap-1 text-xs font-medium">Billing interval
                      <select className="h-9 rounded-md border border-input bg-background px-2 text-sm" value={interval} onChange={(event) => setInterval(event.target.value)} disabled={save.isPending}>
                        <option value="monthly">Monthly</option><option value="yearly">Yearly</option>
                      </select>
                    </label>
                    <Button
                      onClick={() => save.mutate()}
                      disabled={save.isPending || (stripe && (unchanged || selected === "free")) || !plans.data?.some((plan) => plan.code === selected)}
                    >
                      {save.isPending ? "Preparing…" : stripe ? (unchanged ? "Current plan" : "Continue to checkout") : "Choose plan"}
                    </Button>
                  </>
                ) : null}
                {portalAvailable ? (
                  <Button variant="outline" onClick={() => portal.mutate()} disabled={portal.isPending}>
                    {portal.isPending ? "Opening…" : "Manage billing"}
                  </Button>
                ) : null}
              </div>
              {checkoutAvailable && selectedPlan ? <p className="text-xs text-muted-foreground">{planSummary(selectedPlan)}</p> : null}
              {stripe && !checkoutAvailable && portalAvailable ? (
                <p className="text-xs text-muted-foreground">Use Manage billing to change the plan, update the payment method, review invoices, or cancel at the end of the period.</p>
              ) : null}
            </div>
          ) : (
            <p className="mt-4 border-t border-border pt-4 text-xs text-muted-foreground">An administrator changes the plan and opens the billing portal.</p>
          )}
          {message ? (
            <p className={`mt-3 text-xs ${messageIsError ? "text-destructive" : "text-muted-foreground"}`} role={messageIsError ? "alert" : "status"}>{message}</p>
          ) : null}
        </article>
        <BillingUsage billing={billing.data} />
      </div>
    </div>
  );
}

function BillingDate({ value }: { value: string | null | undefined }) {
  if (!value) return "Unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unavailable";
  return <time dateTime={value}>{date.toLocaleDateString()}</time>;
}

function BillingAttentionNotice({
  attention,
  subscription,
}: {
  attention: BillingAttention;
  subscription: BillingStatus["subscription"];
}) {
  const ended = subscription.current_period_end ? new Date(subscription.current_period_end).toLocaleDateString() : null;
  const copy: Record<BillingAttention, string> = {
    payment_failed: `The last payment failed. This workspace is using Free limits until the payment succeeds. The selected plan is still ${subscription.plan_code}. Open Manage billing to update the payment method.`,
    canceled: "This subscription is canceled. The workspace is on Free limits. An administrator can choose a plan to subscribe again.",
    expired: "This subscription expired before payment was confirmed. The workspace is on Free limits.",
    payment_unconfirmed: "Payment has not been confirmed. The workspace stays on Free limits until the subscription is active.",
    cancels_at_period_end: ended
      ? `This subscription cancels on ${ended}. Paid access stays in place until then.`
      : "This subscription cancels at the end of the current period. Paid access stays in place until then.",
    period_lapsed: "The paid period has ended. The workspace is on Free limits until the renewal is confirmed.",
  };
  const alert = attention === "payment_failed" || attention === "expired" || attention === "period_lapsed";
  return (
    <p role={alert ? "alert" : "status"} className={alert
      ? "rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-foreground"
      : "rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-foreground"}>
      {copy[attention]}
    </p>
  );
}

function planSummary(plan: BillingPlan): string | null {
  const seats = plan.entitlements.seats;
  const requests = plan.entitlements.ai_requests;
  const storage = plan.entitlements.knowledge_storage_bytes;
  const workflows = plan.entitlements.active_workflows;
  if (typeof seats !== "number" || typeof requests !== "number" || typeof storage !== "number" || typeof workflows !== "number") {
    return null;
  }
  return `${plan.name} includes ${seats} seats, ${requests.toLocaleString()} AI requests, ${formatUsage(storage, true)} of knowledge storage, and ${workflows} active workflow runs.`;
}

const limits = [
  { key: "seats", label: "Workspace seats" },
  { key: "ai_requests", label: "AI requests this period" },
  { key: "knowledge_storage_bytes", label: "Knowledge storage" },
  { key: "active_workflows", label: "Active workflow runs" },
] as const;

function formatUsage(value: number, bytes: boolean) {
  if (!bytes) return value.toLocaleString();
  if (value >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toLocaleString(undefined, { maximumFractionDigits: 1 })} GB`;
  }
  return `${(value / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 2 })} MB`;
}

function BillingUsage({ billing }: { billing: BillingStatus }) {
  return (
    <section className="settings-card" aria-labelledby="billing-usage">
      <h2 id="billing-usage" className="flex items-center gap-2 text-base font-semibold"><CircleGauge className="size-4 text-primary" aria-hidden="true" />Usage availability</h2>
      <p className="mt-1 text-xs text-muted-foreground">Workspace usage and the limits applied by your plan.</p>
      <dl className="mt-4 grid gap-4">
        {limits.map(({ key, label }) => {
          const used = billing.usage[key];
          const limit = billing.plan[key];
          const bytes = key === "knowledge_storage_bytes";
          const reported = typeof used === "number" && typeof limit === "number";
          const over = reported && limit >= 0 && used > limit;
          return (
            <div key={key}>
              <div className="flex flex-wrap items-center justify-between gap-1 text-xs">
                <dt className="font-medium">{label}</dt>
                <dd className={over ? "tabular-nums text-destructive" : "tabular-nums text-muted-foreground"}>
                  {reported ? `${formatUsage(used, bytes)} / ${formatUsage(limit, bytes)}` : "Unavailable"}
                  {over ? " · Over the current limit" : ""}
                </dd>
              </div>
              {reported && limit > 0 ? (
                <div
                  className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"
                  role="meter"
                  aria-label={label}
                  aria-valuemin={0}
                  aria-valuemax={limit}
                  aria-valuenow={used}
                >
                  <div className={`h-full rounded-full ${over ? "bg-destructive" : "bg-primary"}`} style={{ width: `${Math.min(100, (used / limit) * 100)}%` }} />
                </div>
              ) : null}
            </div>
          );
        })}
      </dl>
    </section>
  );
}
