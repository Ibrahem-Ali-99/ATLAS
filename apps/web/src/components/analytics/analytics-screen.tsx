"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { DataScopeControl } from "@/components/data-scope";
import { RequestError } from "@/components/request-error";
import { Skeleton } from "@/components/ui/skeleton";
import { getAnalytics, type AnalyticsSnapshot, type StatusCount } from "@/lib/intelligence";
import { isDataScope, type DataScope } from "@/lib/provenance";
import { useWorkspace } from "@/lib/use-workspace";

export function AnalyticsScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const [scopeByOrganization, setScopeByOrganization] = useState<Record<string, DataScope>>({});
  const scope = organizationId ? scopeByOrganization[organizationId] ?? storedScope(organizationId) : "all";
  const selectScope = (next: DataScope) => {
    if (organizationId) {
      setScopeByOrganization((current) => ({ ...current, [organizationId]: next }));
      window.localStorage.setItem(`atlas.dashboard.scope.${organizationId}`, next);
    }
  };
  const analytics = useQuery({
    queryKey: ["analytics", organizationId, scope],
    queryFn: () => getAnalytics(organizationId ?? "", scope),
    enabled: Boolean(organizationId),
  });
  if (!organizationId || analytics.isPending) {
    return <Skeleton className="h-40 w-full" />;
  }
  if (analytics.isError) {
    return <RequestError error={analytics.error} />;
  }
  return <AnalyticsBody data={analytics.data} scope={scope} onScope={selectScope} />;
}

function AnalyticsBody({
  data,
  scope,
  onScope,
}: {
  data: AnalyticsSnapshot;
  scope: DataScope;
  onScope: (scope: DataScope) => void;
}) {
  const rate = data.conversion.rate === null ? "Not enough closed leads" : `${Math.round(data.conversion.rate * 1000) / 10}%`;
  const automation =
    data.automation.success_rate === null ? "No completed or failed runs" : `${Math.round(data.automation.success_rate * 1000) / 10}%`;
  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <div>
        <h1 className="text-[31px] leading-none text-foreground">Analytics</h1>
        <DataScopeControl value={scope} onChange={onScope} advanced />
        <details className="mt-3 max-w-3xl text-xs leading-5 text-subtle">
          <summary className="cursor-pointer">About this view</summary>
          <p className="mt-2">{data.provenance_notice}</p>
        </details>
        <p className="mt-2 max-w-3xl text-xs leading-5 text-subtle">
          Lead creation counts use the last {data.window_days} days, including days with zero. The window is fixed by the API.
        </p>
      </div>
      {data.leads_total === 0 && data.inquiries_total === 0 ? (
        <p className="rounded-[10px] bg-muted p-4 text-sm text-muted-foreground">
          No leads or inquiries are stored in this scope.
        </p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Active companies" value={String(data.companies_total)} detail="Customer accounts in the selected scope." />
        <Metric label="Leads" value={String(data.leads_total)} detail="Leads in the selected scope." />
        <Metric label="Open inquiries" value={String(data.open_inquiries)} detail="Customer requests in the selected scope." />
        <Metric
          label="Won or lost"
          value={rate}
          detail={`${data.conversion.won} won, ${data.conversion.lost} lost. ${data.conversion.definition}`}
        />
        <Metric label="Automation" value={automation} detail={data.automation.definition} />
      </div>
      <section className="rounded-[10px] bg-muted p-4">
        <h2 className="text-base text-foreground">Lead pipeline</h2>
        <p className="mt-2 text-xs leading-5 text-subtle">{data.qualification.definition}</p>
        <p className="mt-2 text-sm text-muted-foreground">
          Qualified {data.qualification.qualified}. Unqualified {data.qualification.unqualified}. Open {data.qualification.open}. Closed {data.qualification.closed}.
        </p>
        {data.lead_status.length === 0 ? (
          <p className="mt-4 text-sm text-muted-foreground">No lead statuses are stored.</p>
        ) : (
          <ul className="mt-4 space-y-3">
            {data.lead_status.map((item) => (
              <PipelineRow key={item.status} item={item} max={Math.max(...data.lead_status.map((row) => row.count), 1)} />
            ))}
          </ul>
        )}
        <Link className="mt-4 inline-block text-sm text-primary underline" href="/crm?tab=leads">
          Open leads
        </Link>
      </section>
      <section className="rounded-[10px] bg-muted p-4">
        <h2 className="text-base text-foreground">Leads created</h2>
        <p className="mt-2 text-xs leading-5 text-subtle">Daily stored counts. A flat line is a real zero, not a missing chart.</p>
        {data.lead_trend.every((row) => row.count === 0) ? (
          <p className="mt-2 text-sm text-muted-foreground">No leads were created in this window.</p>
        ) : null}
        <div className="mt-4 h-56 min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.lead_trend}>
              <XAxis dataKey="day" tickFormatter={shortDay} minTickGap={28} tick={{ fill: "#a2b1c4", fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} width={28} tick={{ fill: "#a2b1c4", fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={chartTooltip} />
              <Line type="monotone" dataKey="count" stroke="#6099ff" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
      <div className="grid gap-3 md:grid-cols-3">
        <Metric
          label="Approvals"
          value={String(data.approvals.pending)}
          detail={`${data.approvals.pending} pending, ${data.approvals.approved} approved, ${data.approvals.completed} completed, ${data.approvals.needs_attention} need attention.`}
        />
        <Metric
          label="Follow-ups"
          value={String(data.follow_ups.approval_requests)}
          detail={`${data.follow_ups.interactions} interactions stored.`}
        />
        <Metric
          label="Delivery"
          value={String(data.email.sandbox_sent)}
          detail={`${data.email.sandbox_sent} sandbox emails, ${data.email.live_sent} live emails, ${data.email.failed} failed. Calendar booked ${data.calendar.booked}, cancelled ${data.calendar.cancelled}. ${data.calendar.notice}`}
        />
      </div>
      <p className="text-xs leading-5 text-subtle">
        Lead scores stay on each lead after Score lead. This page does not roll them up, because no distribution is stored here.
      </p>
    </div>
  );
}

function PipelineRow({ item, max }: { item: StatusCount; max: number }) {
  return (
    <li>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span>{item.status}</span>
        <span className="tabular-nums text-muted-foreground">{item.count}</span>
      </div>
      <div className="mt-2 h-1.5 rounded-full bg-secondary">
        <div className="h-1.5 rounded-full bg-primary" style={{ width: `${Math.max(4, Math.round((item.count / max) * 100))}%` }} />
      </div>
    </li>
  );
}

const chartTooltip = {
  background: "#111925",
  border: "none",
  borderRadius: 10,
  color: "#f3f7fc",
};

function shortDay(value: string): string {
  return value.length >= 10 ? value.slice(5) : value;
}

function storedScope(organizationId: string): DataScope {
  if (typeof window === "undefined") return "all";
  const saved = window.localStorage.getItem(`atlas.dashboard.scope.${organizationId}`);
  return isDataScope(saved) ? saved : "all";
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  const slug = label.toLowerCase().replaceAll(" ", "-");
  return (
    <section data-testid={`analytics-metric-${slug}`} className="rounded-[10px] bg-muted p-4">
      <p className="text-xs uppercase tracking-[0.12em] text-subtle">{label}</p>
      <p data-testid={`analytics-metric-${slug}-value`} className="mt-3 text-2xl tabular-nums text-foreground">{value}</p>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{detail}</p>
    </section>
  );
}
