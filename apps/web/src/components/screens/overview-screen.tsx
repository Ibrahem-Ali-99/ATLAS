"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getHealth, getReady } from "@/lib/api";
import { getAnalytics, type AnalyticsSnapshot, type StatusCount } from "@/lib/intelligence";
import { useWorkspace } from "@/lib/use-workspace";

export function OverviewScreen() {
  const workspace = useWorkspace();
  const analytics = useQuery({
    queryKey: ["analytics", workspace.organizationId],
    queryFn: () => getAnalytics(workspace.organizationId ?? ""),
    enabled: Boolean(workspace.organizationId),
  });
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, retry: false });
  const ready = useQuery({ queryKey: ["ready"], queryFn: getReady, retry: false });

  return (
    <div className="flex w-full min-w-0 flex-col gap-8">
      <PageHeader title="Overview" eyebrow={workspace.organizationName ?? undefined}>
        Decisions waiting, recent failures, and the stored pipeline for this organization.
        {analytics.data ? ` ${analytics.data.synthetic_notice}` : ""}
      </PageHeader>
      {analytics.isPending ? <Skeleton className="h-28 w-full" /> : null}
      {analytics.isError ? <RequestError error={analytics.error} /> : null}
      {analytics.data ? <Operations data={analytics.data} /> : null}
      <section className="grid gap-3 text-sm text-muted-foreground md:grid-cols-2">
        <p>API {health.isError ? "unreachable" : health.data?.status ?? "checking"}.</p>
        <p>Database {ready.isError ? "not ready" : ready.data?.database ?? "checking"}.</p>
      </section>
    </div>
  );
}

function Operations({ data }: { data: AnalyticsSnapshot }) {
  const maxStatus = Math.max(1, ...data.lead_status.map((item) => item.count));
  const maxTrend = Math.max(1, ...data.lead_trend.map((item) => item.count));
  const conversion = data.conversion.rate === null ? "No closed leads" : `${Math.round(data.conversion.rate * 1000) / 10}% won`;
  return (
    <>
      <section className="grid gap-3 lg:grid-cols-3">
        <AttentionLink href="/approvals" label="Pending approvals" value={data.approvals.pending} detail="Waiting for a decision. Execute is the write." />
        <AttentionLink href="/approvals" label="Uncertain outcomes" value={data.approvals.needs_attention} detail="The result could not be confirmed. Do not treat these as done." />
        <AttentionLink href="/monitoring" label="Failed runs" value={data.failed_runs} detail="Stored agent failures. Open Monitoring for the trace." />
      </section>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(18rem,0.9fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Lead pipeline</CardTitle>
          </CardHeader>
          <CardContent>
            {data.lead_status.length === 0 ? (
              <p className="text-sm text-muted-foreground">No leads are stored yet.</p>
            ) : (
              <ul className="space-y-3">
                {data.lead_status.map((item) => (
                  <StatusBar key={item.status} item={item} max={maxStatus} />
                ))}
              </ul>
            )}
            <p className="mt-4 text-xs leading-5 text-muted-foreground">{data.qualification.definition}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {data.qualification.open} open, {data.qualification.qualified} qualified, {data.qualification.closed} closed.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Leads created</CardTitle>
          </CardHeader>
          <CardContent>
            <LeadTrend days={data.lead_trend} windowDays={data.window_days} max={maxTrend} />
          </CardContent>
        </Card>
      </div>
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Fact label="Inquiries" value={String(data.inquiries_total)} href="/crm" detail="Stored inquiries for this organization." />
        <Fact label="Conversion" value={conversion} href="/analytics" detail={data.conversion.definition} />
        <Fact
          label="Agent outcomes"
          value={data.agent_outcomes.map((item) => `${item.count} ${item.status.replaceAll("_", " ")}`).join(", ") || "None stored"}
          href="/agent-runs"
          detail="Counts from stored agent runs."
        />
        <Fact
          label="Automation"
          value={data.automation.success_rate === null ? "Unavailable" : `${Math.round(data.automation.success_rate * 1000) / 10}%`}
          href="/workflows"
          detail={`${data.automation.definition} Sandbox email sent: ${data.email.sandbox_sent}.`}
        />
      </section>
    </>
  );
}

function AttentionLink({ href, label, value, detail }: { href: string; label: string; value: number; detail: string }) {
  return (
    <Link href={href} className="rounded-xl border border-border bg-card p-4 transition-colors hover:bg-accent">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-2 text-3xl font-semibold tabular-nums whitespace-nowrap">{value}</p>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{detail}</p>
    </Link>
  );
}

function Fact({ href, label, value, detail }: { href: string; label: string; value: string; detail: string }) {
  return (
    <Link href={href} className="rounded-xl border border-border bg-card p-4 transition-colors hover:bg-accent">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-2 text-sm font-medium leading-6">{value}</p>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{detail}</p>
    </Link>
  );
}

function LeadTrend({
  days,
  windowDays,
  max,
}: {
  days: { day: string; count: number }[];
  windowDays: number;
  max: number;
}) {
  const active = days.filter((item) => item.count > 0);
  const quiet = days.length - active.length;
  return (
    <>
      <p className="text-xs leading-5 text-muted-foreground">
        {quiet === days.length
          ? `No leads were created in the last ${windowDays} days.`
          : `${quiet} of the last ${windowDays} days had no new leads. Days with new leads are listed.`}
      </p>
      {active.length > 0 ? (
        <ul className="mt-4 space-y-2">
          {active.map((item) => (
            <li key={item.day} className="grid grid-cols-[4.5rem_minmax(0,1fr)_2rem] items-center gap-3 text-xs">
              <span className="text-muted-foreground">{item.day.slice(5)}</span>
              <span className="h-1.5 rounded-full bg-secondary">
                <span className="block h-1.5 rounded-full bg-primary" style={{ width: `${(item.count / max) * 100}%` }} />
              </span>
              <span className="text-right tabular-nums">{item.count}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

function StatusBar({ item, max }: { item: StatusCount; max: number }) {
  return (
    <li>
      <div className="mb-1 flex items-center justify-between gap-3 text-sm">
        <span className="capitalize">{item.status.replaceAll("_", " ")}</span>
        <Badge variant="secondary">{item.count}</Badge>
      </div>
      <div className="h-1.5 rounded-full bg-secondary">
        <div className="h-1.5 rounded-full bg-primary" style={{ width: `${(item.count / max) * 100}%` }} />
      </div>
    </li>
  );
}
