"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { DataScopeControl } from "@/components/data-scope";
import { RequestError } from "@/components/request-error";
import { Skeleton } from "@/components/ui/skeleton";
import { getAnalytics, type AnalyticsSnapshot, type StatusCount } from "@/lib/intelligence";
import { listTeam } from "@/lib/organization";
import { isDataScope, type DataScope } from "@/lib/provenance";
import { useWorkspace } from "@/lib/use-workspace";

export function AnalyticsScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const [scopeByOrganization, setScopeByOrganization] = useState<Record<string, DataScope>>({});
  const [period, setPeriod] = useState("30d");
  const [channel, setChannel] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [ownerUserId, setOwnerUserId] = useState("");
  const team = useQuery({ queryKey: ["analytics-team", organizationId], queryFn: () => listTeam(organizationId ?? ""), enabled: Boolean(organizationId) });
  const scope = organizationId ? scopeByOrganization[organizationId] ?? storedScope(organizationId) : "all";
  const selectScope = (next: DataScope) => {
    if (organizationId) {
      setScopeByOrganization((current) => ({ ...current, [organizationId]: next }));
      window.localStorage.setItem(`atlas.dashboard.scope.${organizationId}`, next);
    }
  };
  const analytics = useQuery({
    queryKey: ["analytics", organizationId, scope, period, channel, startDate, endDate, ownerUserId],
    queryFn: () => getAnalytics(organizationId ?? "", scope, { period, channel, startDate, endDate, ownerUserId }),
    enabled: Boolean(organizationId),
  });
  if (!organizationId || analytics.isPending) {
    return <Skeleton className="h-40 w-full" />;
  }
  if (analytics.isError) {
    return <RequestError error={analytics.error} />;
  }
  return <AnalyticsBody data={analytics.data} scope={scope} onScope={selectScope} period={period} onPeriod={setPeriod} channel={channel} onChannel={setChannel} ownerUserId={ownerUserId} onOwner={setOwnerUserId} team={team.data ?? []} startDate={startDate} endDate={endDate} onStartDate={setStartDate} onEndDate={setEndDate} />;
}

function AnalyticsBody({
  data,
  scope,
  onScope,
  period, onPeriod, channel, onChannel, ownerUserId, onOwner, team, startDate, endDate, onStartDate, onEndDate,
}: {
  data: AnalyticsSnapshot;
  scope: DataScope;
  onScope: (scope: DataScope) => void;
  period: string; onPeriod: (value: string) => void; channel: string; onChannel: (value: string) => void; ownerUserId: string; onOwner: (value: string) => void; team: { user_id: string; full_name: string; is_active: boolean }[]; startDate: string; endDate: string; onStartDate: (value: string) => void; onEndDate: (value: string) => void;
}) {
  const rate = data.conversion.rate === null ? "Not enough closed leads" : `${Math.round(data.conversion.rate * 1000) / 10}%`;
  const automation =
    data.automation.success_rate === null ? "No completed or failed runs" : `${Math.round(data.automation.success_rate * 1000) / 10}%`;
  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <div>
        <h1 className="text-[31px] leading-none text-foreground">Analytics</h1>
        <DataScopeControl value={scope} onChange={onScope} advanced />
        <div className="mt-3 flex flex-wrap gap-2"><select aria-label="Analytics date range" className="h-9 rounded-md bg-secondary px-3 text-sm" value={period} onChange={(e) => onPeriod(e.target.value)}><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="90d">Last 90 days</option><option value="custom">Custom range</option></select><select aria-label="Analytics channel" className="h-9 rounded-md bg-secondary px-3 text-sm" value={channel} onChange={(e) => onChannel(e.target.value)}><option value="">All channels</option><option value="email">Email</option><option value="whatsapp">WhatsApp</option><option value="webchat">Web chat</option></select><select aria-label="Analytics opportunity owner" className="h-9 rounded-md bg-secondary px-3 text-sm" value={ownerUserId} onChange={(e) => onOwner(e.target.value)}><option value="">All owners</option>{team.filter((item) => item.is_active).map((item) => <option key={item.user_id} value={item.user_id}>{item.full_name}</option>)}</select>{period === "custom" ? <><input aria-label="Analytics start date" type="date" value={startDate} onChange={(e) => onStartDate(e.target.value)} /><input aria-label="Analytics end date" type="date" value={endDate} onChange={(e) => onEndDate(e.target.value)} /></> : null}</div>
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
      {data.sales ? <section className="rounded-[10px] bg-muted p-4" aria-label="Sales analytics"><h2 className="text-base text-foreground">Opportunity pipeline</h2><div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-5"><Metric label="Opportunities" value={String(data.sales.opportunities_total)} detail={`${data.sales.won.count} won · ${data.sales.lost.count} lost`} /><Metric label="Win rate" value={data.sales.win_rate === null ? "Unavailable" : `${Math.round(data.sales.win_rate * 100)}%`} detail="Won opportunities / all opportunities in period." /><Metric label="Won value" value={data.sales.won.value.toLocaleString()} detail="Persisted value; currency totals remain separate below." /><Metric label="Avg won value" value={data.sales.average_won_value === null ? "Unavailable" : data.sales.average_won_value.toLocaleString()} detail="Average among won opportunities." /><Metric label="Lead conversion" value={data.sales.lead_to_opportunity.rate === null ? "Unavailable" : `${Math.round(data.sales.lead_to_opportunity.rate * 100)}%`} detail={`${data.sales.lead_to_opportunity.converted_leads}/${data.sales.lead_to_opportunity.eligible_leads} distinct leads.`} /></div><ul className="mt-4 space-y-2">{data.sales.by_stage.map((stage) => <li key={stage.stage} className="flex justify-between text-sm"><span>{stage.stage}</span><span className="tabular-nums text-muted-foreground">{stage.count} · {stage.value.toLocaleString()}</span></li>)}</ul></section> : null}
      {data.support ? <Metric label="First response" value={data.support.average_first_response_seconds === null ? "Unavailable" : `${Math.round(data.support.average_first_response_seconds / 60)} min`} detail={`${data.support.first_response_sample_size} conversations with a persisted response.`} /> : null}
      {data.sales ? <TrendSection title="Pipeline value by stage and currency" rows={data.sales.stage_trend.map((item) => ({ day: item.day, label: `${item.stage} · ${item.currency}`, value: item.value }))} unit="value" /> : null}
      {data.support ? <TrendSection title="Conversation volume by channel" rows={data.support.volume_trend.map((item) => ({ day: item.day, label: item.channel, value: item.count }))} unit="conversations" /> : null}
      {data.ai ? <TrendSection title="AI requests and failures" rows={data.ai.trend.map((item) => ({ day: item.day, label: item.status, value: item.count }))} unit="requests" /> : null}
      {data.workflow_performance ? <section className="rounded-[10px] bg-muted p-4" aria-label="Workflow performance"><h2 className="text-base text-foreground">Workflow performance</h2><div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3"><Metric label="Executions" value={String(data.workflow_performance.total)} detail={`${data.workflow_performance.pending} pending · ${data.workflow_performance.running} running.`} /><Metric label="Workflow success" value={data.workflow_performance.success_rate === null ? "Unavailable" : `${Math.round(data.workflow_performance.success_rate * 100)}%`} detail={`${data.workflow_performance.successful} successful / ${data.workflow_performance.denominator} terminal executions.`} /><Metric label="Failed workflows" value={String(data.workflow_performance.failed)} detail="Failed and needs-attention terminal runs." /></div><TrendSection title="Successful versus failed executions" rows={data.workflow_performance.trend.filter((item) => ["completed", "failed", "needs_attention"].includes(item.status)).map((item) => ({ day: item.day, label: item.status, value: item.count }))} unit="runs" /></section> : null}
      {data.support || data.ai || data.evaluation ? <div className="grid gap-3 md:grid-cols-3">{data.support ? <Metric label="Human handoffs" value={String(data.support.handoffs)} detail={`${data.support.by_channel.length} channel/status groups.`} /> : null}{data.ai ? <Metric label="AI requests" value={String(data.ai.requests)} detail={data.ai.failure_rate === null ? "No recorded AI operations." : `${Math.round(data.ai.failure_rate * 1000) / 10}% failed`} /> : null}{data.evaluation ? <Metric label="Evaluation pass rate" value={data.evaluation.pass_rate === null ? "Unavailable" : `${Math.round(data.evaluation.pass_rate * 1000) / 10}%`} detail={`${data.evaluation.passed} of ${data.evaluation.executed} cases passed.`} /> : null}</div> : null}
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

function TrendSection({ title, rows, unit }: { title: string; rows: { day: string; label: string; value: number }[]; unit: string }) {
  const max = Math.max(...rows.map((row) => row.value), 0);
  return <section className="rounded-[10px] bg-muted p-4" aria-label={title}><h2 className="text-base text-foreground">{title}</h2>{rows.length === 0 ? <p className="mt-3 text-sm text-muted-foreground">No persisted data is available for this period.</p> : <div className="mt-4 space-y-3">{rows.slice(-30).map((row, index) => <div key={`${row.day}-${row.label}-${index}`}><div className="flex justify-between gap-3 text-xs"><span>{row.day} · {row.label}</span><span className="tabular-nums text-muted-foreground">{row.value.toLocaleString()} {unit}</span></div><div className="mt-1 h-2 rounded-full bg-secondary"><div className="h-2 rounded-full bg-primary" style={{ width: `${max ? Math.max(4, (row.value / max) * 100) : 0}%` }} /></div></div>)}</div>}</section>;
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
