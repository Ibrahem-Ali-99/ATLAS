"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { DataScopeControl } from "@/components/data-scope";
import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { sessionQueryOptions } from "@/lib/api";
import { isDemoSession } from "@/lib/demo-session";
import { downloadAnalyticsReport, getAnalytics, type AnalyticsSnapshot, type PeriodDelta, type StatusCount } from "@/lib/intelligence";
import { listTeam } from "@/lib/organization";
import { isDataScope, type DataScope } from "@/lib/provenance";
import { useWorkspace } from "@/lib/use-workspace";

export function AnalyticsScreen() {
  const { organizationId } = useWorkspace();
  return organizationId ? <AnalyticsWorkspace key={organizationId} organizationId={organizationId} /> : null;
}

function AnalyticsWorkspace({ organizationId }: { organizationId: string }) {
  const session = useQuery(sessionQueryOptions);
  const demonstration = isDemoSession(session.data);
  const [scope, setScope] = useState<DataScope>(() => storedScope(organizationId));
  const recordScope = demonstration ? "all" : scope;
  const [period, setPeriod] = useState("30d");
  const [channel, setChannel] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [ownerUserId, setOwnerUserId] = useState("");
  const [report, setReport] = useState("opportunities");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<Error | null>(null);
  const team = useQuery({ queryKey: ["analytics-team", organizationId], queryFn: () => listTeam(organizationId) });
  const custom = period === "custom";
  const span = (Date.parse(endDate) - Date.parse(startDate)) / 86_400_000;
  const valid = !custom || (Boolean(startDate && endDate) && span >= 0 && span <= 365);
  const filters = { period, channel, startDate: custom ? startDate : "", endDate: custom ? endDate : "", ownerUserId };
  const analytics = useQuery({
    queryKey: ["analytics", organizationId, recordScope, filters],
    queryFn: () => getAnalytics(organizationId, recordScope, filters),
    enabled: valid,
  });

  return (
    <div className="flex w-full min-w-0 flex-col gap-5">
      <PageHeader title="Analytics" eyebrow="Business activity">Review customer activity, pipeline movement, and operational outcomes.</PageHeader>
      <section className="analytics-filters panel" aria-label="Analytics filters">
        <div className="flex flex-wrap items-end gap-3 [&_label]:grid [&_label]:gap-1 [&_label]:text-sm [&_select]:h-9 [&_select]:rounded-md [&_select]:border [&_select]:border-border [&_select]:bg-background [&_select]:px-2">
          <label>Date range
            <select aria-label="Analytics date range" value={period} onChange={(event) => setPeriod(event.target.value)}>
              <option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="90d">Last 90 days</option><option value="custom">Custom range</option>
            </select>
          </label>
          {custom ? <>
            <label>Start date<input className="h-9 rounded-md border border-border bg-background px-2" aria-label="Analytics start date" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
            <label>End date<input className="h-9 rounded-md border border-border bg-background px-2" aria-label="Analytics end date" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
          </> : null}
          <label>Channel
            <select aria-label="Analytics channel" value={channel} onChange={(event) => setChannel(event.target.value)}>
              <option value="">All channels</option><option value="email">Email</option><option value="whatsapp">WhatsApp</option><option value="webchat">Website chat</option>
            </select>
          </label>
          <label>Opportunity owner
            <select aria-label="Analytics opportunity owner" value={ownerUserId} onChange={(event) => setOwnerUserId(event.target.value)}>
              <option value="">All owners</option>{team.data?.filter((item) => item.is_active).map((item) => <option key={item.user_id} value={item.user_id}>{item.full_name}</option>)}
            </select>
          </label>
          <label>Export
            <select aria-label="Analytics report" value={report} onChange={(event) => setReport(event.target.value)}>
              <option value="opportunities">Opportunities</option>
              <option value="leads">Leads</option>
              <option value="conversations">Conversations</option>
              <option value="tasks">Tasks</option>
              <option value="appointments">Appointments</option>
              <option value="campaigns">Campaigns</option>
              <option value="workflows">Workflows</option>
              <option value="approvals">Approvals</option>
            </select>
          </label>
          <Button type="button" variant="outline" disabled={!valid || exporting} onClick={() => {
            setExporting(true);
            setExportError(null);
            void downloadAnalyticsReport(organizationId, recordScope, report, filters)
              .catch((error: unknown) => setExportError(error instanceof Error ? error : new Error("Export failed")))
              .finally(() => setExporting(false));
          }}>{exporting ? "Exporting…" : "Download CSV"}</Button>
        </div>
        {exportError ? <RequestError error={exportError} /> : null}
        {demonstration ? null : <DataScopeControl value={scope} onChange={(next) => {
          setScope(next);
          window.localStorage.setItem(`atlas.dashboard.scope.${organizationId}`, next);
        }} />}
      </section>
      {!valid ? <p role="status" className="text-sm text-muted-foreground">Choose a start and end date for a range of up to 366 days.</p> :
        analytics.isPending ? <Skeleton className="h-40 w-full" /> :
          analytics.isError ? <RequestError error={analytics.error} /> : <AnalyticsBody data={analytics.data} />}
    </div>
  );
}

function AnalyticsBody({ data }: { data: AnalyticsSnapshot }) {
  const rate = data.conversion.rate === null ? "Not enough closed leads" : `${Math.round(data.conversion.rate * 1000) / 10}%`;
  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <details className="max-w-3xl text-xs leading-5 text-muted-foreground">
        <summary className="cursor-pointer">About this view</summary>
        <p className="mt-2">{data.provenance_notice} Activity trends cover {data.window_days} days.</p>
      </details>
      {data.leads_total === 0 && data.inquiries_total === 0 ? (
        <p className="rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">
          No leads or inquiries are stored in this scope.
        </p>
      ) : null}
      <div className="kpi-band">
        <Metric label="Active companies" value={String(data.companies_total)} detail="Customer accounts in this view." href="/crm?tab=companies" />
        <Metric label="Leads" value={String(data.leads_total)} detail="Leads in this view." href="/crm?tab=leads" />
        <Metric label="Open inquiries" value={String(data.open_inquiries)} detail="Customer requests in this view." href="/crm?tab=inquiries" />
        <Metric
          label="Won or lost"
          value={rate}
          detail={`${data.conversion.won} won, ${data.conversion.lost} lost.`}
          href="/crm?tab=leads"
        />
      </div>
      {data.comparison ? <Comparison comparison={data.comparison} /> : null}
      <div className="bi-layout">
        {data.customer_activity ? <CustomerActivity rows={data.customer_activity} /> : null}
        <LeadPipeline data={data} />
      </div>
      {data.sales ? <OpportunityAnalytics sales={data.sales} /> : null}
      {data.support ? <div className="grid gap-3 md:grid-cols-2"><Metric label="First response" value={data.support.average_first_response_seconds === null ? "Unavailable" : responseTime(data.support.average_first_response_seconds)} detail={`${data.support.first_response_sample_size} conversations with a persisted response.`} href="/inbox" /><Metric label="Resolution" value={data.support.average_resolution_seconds == null ? "Unavailable" : responseTime(data.support.average_resolution_seconds)} detail={data.support.resolution_definition ?? "No resolved conversations in this period."} href="/inbox" /></div> : null}
      {data.sales ? <TrendSection title="Pipeline value by stage and currency" rows={data.sales.stage_trend.filter((item) => item.value != null).map((item) => ({ day: item.day, label: `${item.stage} · ${item.currency}`, value: item.value ?? 0 }))} unit="value" /> : null}
      {data.support ? <TrendSection title="Conversation volume by channel" rows={data.support.volume_trend.map((item) => ({ day: item.day, label: item.channel, value: item.count }))} unit="conversations" /> : null}
      {data.ai ? <TrendSection title="AI requests and failures" rows={data.ai.trend.map((item) => ({ day: item.day, label: item.status, value: item.count }))} unit="requests" /> : null}
      {data.workflow_performance ? <section className="rounded-xl border border-border bg-card p-4" aria-label="Workflow performance"><h2 className="text-base text-foreground">Workflow performance</h2><div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3"><Metric label="Executions" value={String(data.workflow_performance.total)} detail={`${data.workflow_performance.pending} pending · ${data.workflow_performance.running} running.`} /><Metric label="Workflow success" value={data.workflow_performance.success_rate === null ? "Unavailable" : `${Math.round(data.workflow_performance.success_rate * 100)}%`} detail={`${data.workflow_performance.successful} successful / ${data.workflow_performance.denominator} terminal executions.`} /><Metric label="Failed workflows" value={String(data.workflow_performance.failed)} detail="Failed and needs-attention terminal runs." /></div><TrendSection title="Successful versus failed executions" rows={data.workflow_performance.trend.filter((item) => ["completed", "failed", "needs_attention"].includes(item.status)).map((item) => ({ day: item.day, label: item.status, value: item.count }))} unit="runs" /></section> : null}
      {data.support || data.ai || data.evaluation ? <div className="grid gap-3 md:grid-cols-3">{data.support ? <Metric label="Human handoffs" value={String(data.support.handoffs)} detail={`${data.support.by_channel.length} channel/status groups.`} /> : null}{data.ai ? <Metric label="AI requests" value={String(data.ai.requests)} detail={data.ai.failure_rate === null ? "No recorded AI operations." : `${Math.round(data.ai.failure_rate * 1000) / 10}% failed`} /> : null}{data.evaluation ? <Metric label="Evaluation pass rate" value={data.evaluation.pass_rate === null ? "Unavailable" : `${Math.round(data.evaluation.pass_rate * 1000) / 10}%`} detail={`${data.evaluation.passed} of ${data.evaluation.executed} cases passed.`} /> : null}</div> : null}
      <section className="chart-panel" aria-label="Leads created">
        <h2 className="text-base text-foreground">Leads created</h2>
        <p className="mt-2 text-xs leading-5 text-subtle">New CRM leads by day in the selected period.</p>
        {data.lead_trend.every((row) => row.count === 0) ? (
          <p className="mt-2 text-sm text-muted-foreground">No leads were created in this window.</p>
        ) : null}
        <div className="mt-4 h-56 min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.lead_trend}>
              <XAxis dataKey="day" tickFormatter={shortDay} minTickGap={28} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} width={28} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={chartTooltip} />
              <Legend />
              <Line type="monotone" dataKey="count" name="Leads" stroke="var(--primary)" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
      {data.qualification_trend ? <QualificationTrend rows={data.qualification_trend} /> : null}
      {data.campaigns ? <Campaigns campaigns={data.campaigns} /> : null}
      <div className="grid gap-3 md:grid-cols-3">
        <Metric
          label="Approvals"
          value={String(data.approvals.pending)}
          detail={`${data.approvals.pending} pending now. ${data.approval_activity ? `${data.approval_activity.created} created in this period. ${data.approval_activity.definition}` : ""}`}
          href="/approvals"
        />
        <Metric
          label="Follow-ups"
          value={String(data.follow_ups.approval_requests)}
          detail={`${data.follow_ups.interactions} interactions stored.`}
        />
        <Metric
          label="Delivery"
          value={String(data.email.sandbox_sent)}
          detail={`${data.email.sandbox_sent} sandbox emails, ${data.email.live_sent} live emails, ${data.email.failed} failed in this period. Appointments booked ${data.calendar.booked}, cancelled ${data.calendar.cancelled}. ${data.calendar.notice}`}
          href="/crm?tab=leads"
        />
      </div>
      <p className="text-xs leading-5 text-subtle">
        Lead scores stay on each lead after Score lead. This page does not roll them up, because no distribution is stored here.
      </p>
    </div>
  );
}


function LeadPipeline({ data }: { data: AnalyticsSnapshot }) {
  return (
      <section className="panel pipeline-distribution">
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
  );
}

function CustomerActivity({ rows }: { rows: NonNullable<AnalyticsSnapshot["customer_activity"]> }) {
  const hasActivity = rows.some(({ inquiries, interactions }) => inquiries > 0 || interactions > 0);
  return (
    <section className="panel analytics-trend" aria-labelledby="customer-activity-heading">
      <h2 id="customer-activity-heading" className="font-semibold">Customer activity trend</h2>
      <p className="mt-1 text-sm text-muted-foreground">Inquiries and interactions by day</p>
      {hasActivity ? (
        <>
          <div className="mt-4 flex flex-wrap gap-4 text-xs text-muted-foreground" aria-hidden="true">
            <span className="flex items-center gap-2"><span className="w-4 border-t-2 border-primary" /> Inquiries</span>
            <span className="flex items-center gap-2"><span className="w-4 border-t-2 border-dashed border-muted-foreground" /> Interactions</span>
          </div>
          <div className="mt-4 h-56 min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows}>
                <XAxis dataKey="day" tickFormatter={shortDay} minTickGap={28} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} width={32} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={chartTooltip} />
                <Line type="monotone" dataKey="inquiries" name="Inquiries" stroke="var(--primary)" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="interactions" name="Interactions" stroke="var(--muted-foreground)" strokeDasharray="4 4" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <details className="mt-4 text-sm">
            <summary className="cursor-pointer font-medium">View daily counts</summary>
            <div className="mt-3 max-h-64 overflow-auto">
              <table className="w-full text-left text-sm tabular-nums">
                <caption className="sr-only">Daily customer activity</caption>
                <thead className="sticky top-0 bg-card"><tr><th className="py-2">Day</th><th>Inquiries</th><th>Interactions</th></tr></thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.day} className="border-t border-border">
                      <td className="py-2"><time dateTime={row.day}>{row.day}</time></td>
                      <td>{row.inquiries}</td><td>{row.interactions}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : <p className="mt-4 text-sm text-muted-foreground">No inquiries or interactions were recorded in this period.</p>}
    </section>
  );
}

function OpportunityAnalytics({ sales }: { sales: NonNullable<AnalyticsSnapshot["sales"]> }) {
  const conversion = sales.lead_to_opportunity;
  const won = new Map<string, { count: number; value: number }>();
  for (const item of sales.stage_trend) {
    if (item.stage !== "won" || item.value == null) continue;
    const currency = won.get(item.currency) ?? { count: 0, value: 0 };
    won.set(item.currency, { count: currency.count + item.count, value: currency.value + item.value });
  }
  return (
    <section className="min-w-0 rounded-xl border border-border bg-card p-5" aria-label="Sales analytics">
      <h2 className="font-semibold">Opportunity pipeline</h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <Metric label="Opportunities" value={String(sales.opportunities_total)} detail={`${sales.won.count} won · ${sales.lost.count} lost`} />
        <Metric label="Win rate" value={sales.win_rate === null ? "Unavailable" : `${Math.round(sales.win_rate * 100)}%`} detail={sales.loss_rate == null ? "No won or lost opportunities in this period." : `${Math.round(sales.loss_rate * 100)}% lost. Won divided by won plus lost. Open opportunities are excluded.`} href="/crm?tab=opportunities" />
        <Metric label="Lead conversion" value={conversion.rate === null ? "Unavailable" : `${Math.round(conversion.rate * 100)}%`} detail={`${conversion.converted_leads} of ${conversion.eligible_leads} eligible leads converted.`} href="/crm?tab=leads" />
      </div>
      <p className="mt-3 text-sm text-muted-foreground">{sales.tasks_overdue} overdue tasks now. {sales.tasks_completed} completed in this period. <Link className="text-primary underline" href="/workflows">Open tasks</Link></p>
      {sales.tasks_definition ? <p className="mt-1 text-xs text-muted-foreground">{sales.tasks_definition}</p> : null}
      {sales.by_stage.length ? (
        <ul className="mt-4 divide-y divide-border">
          {sales.by_stage.map((stage) => (
            <li key={`${stage.stage}-${stage.currency}`} className="flex justify-between gap-3 py-2 text-sm">
              <Link className="capitalize text-primary underline" href="/crm?tab=opportunities">{stage.stage.replaceAll("_", " ")} · {stage.currency}</Link>
              <span className="tabular-nums text-muted-foreground">{stage.count}{stage.value == null ? "" : ` · ${stage.value.toLocaleString()}`}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {sales.currencies.length ? (
        <div className="mt-4 overflow-x-auto border-t border-border pt-4">
          <table className="w-full text-left text-sm tabular-nums">
            <caption className="mb-2 text-left text-sm font-semibold">Opportunity value by currency</caption>
            <thead><tr><th className="py-2 pr-3">Currency</th><th className="pr-3">Total</th><th className="pr-3">Won</th><th>Average won</th></tr></thead>
            <tbody>
              {sales.currencies.map(({ currency, value }) => {
                const totals = won.get(currency);
                return (
                  <tr key={currency} className="border-t border-border">
                    <td className="py-2 pr-3 font-medium">{currency}</td><td className="pr-3">{value == null ? "No amount stored" : value.toLocaleString()}</td>
                    <td className="pr-3">{(totals?.value ?? 0).toLocaleString()}</td>
                    <td>{totals?.count ? (totals.value / totals.count).toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
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
        <div className="h-1.5 rounded-full bg-primary" style={{ width: `${Math.round((item.count / max) * 100)}%` }} />
      </div>
    </li>
  );
}

function TrendSection({ title, rows, unit }: { title: string; rows: { day: string; label: string; value: number }[]; unit: string }) {
  const max = Math.max(...rows.map((row) => row.value), 0);
  return <section className="rounded-xl border border-border bg-card p-4" aria-label={title}><h2 className="text-base text-foreground">{title}</h2>{rows.length === 0 ? <p className="mt-3 text-sm text-muted-foreground">No persisted data is available for this period.</p> : <div className="mt-4 space-y-3">{rows.slice(-30).map((row, index) => <div key={`${row.day}-${row.label}-${index}`}><div className="flex justify-between gap-3 text-xs"><span>{row.day} · {row.label}</span><span className="tabular-nums text-muted-foreground">{row.value.toLocaleString()} {unit}</span></div><div className="mt-1 h-2 rounded-full bg-secondary"><div className="h-2 rounded-full bg-primary" style={{ width: `${max ? (row.value / max) * 100 : 0}%` }} /></div></div>)}</div>}</section>;
}

const chartTooltip = {
  background: "var(--card)",
  border: "none",
  borderRadius: 10,
  color: "var(--foreground)",
};

function responseTime(seconds: number): string {
  return seconds < 60 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`;
}

function shortDay(value: string): string {
  return value.length >= 10 ? value.slice(5) : value;
}

function formatDay(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return value;
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function storedScope(organizationId: string): DataScope {
  if (typeof window === "undefined") return "all";
  const saved = window.localStorage.getItem(`atlas.dashboard.scope.${organizationId}`);
  return isDataScope(saved) ? saved : "all";
}

function Metric({ label, value, detail, href }: { label: string; value: string; detail: string; href?: string }) {
  const slug = label.toLowerCase().replaceAll(" ", "-");
  return (
    <section data-testid={`analytics-metric-${slug}`} className="insight-card">
      <header><span>{label}</span></header>
      <strong data-testid={`analytics-metric-${slug}-value`}>{value}</strong>
      <small>{detail}</small>
      {href ? <Link className="text-xs font-medium text-primary" href={href}>Open records</Link> : null}
    </section>
  );
}

function Comparison({ comparison }: { comparison: NonNullable<AnalyticsSnapshot["comparison"]> }) {
  const rows = [
    ["Leads created", comparison.leads_created],
    ["Opportunities", comparison.opportunities_created],
    ["Conversations", comparison.conversations],
    ["Opportunities won", comparison.opportunities_won],
  ] as const;
  return (
    <section className="compare-strip" aria-label="Period comparison">
      <h2 className="text-base font-semibold text-foreground">Compared with the previous period</h2>
      <p className="mt-1 text-xs text-muted-foreground">{formatDay(comparison.previous_period.start)} to {formatDay(comparison.previous_period.end)}</p>
      <ul>
        {rows.map(([label, item]) => <ComparisonItem key={label} label={label} item={item} />)}
      </ul>
    </section>
  );
}

function ComparisonItem({ label, item }: { label: string; item: PeriodDelta }) {
  const change = item.change_rate == null ? "No earlier activity" : `${item.delta > 0 ? "+" : ""}${Math.round(item.change_rate * 1000) / 10}%`;
  const previous = item.change_rate == null ? "" : ` · previous ${item.previous}`;
  const tone = item.change_rate == null ? "" : item.delta < 0 ? "down" : "up";
  const span = Math.max(item.current, item.previous, 1);
  return (
    <li className="compare-cell">
      <span>{label}</span>
      <strong>{item.current}</strong>
      <small className={tone}>{change}{previous}</small>
      <div className="stage-meter" aria-hidden="true"><b style={{ width: `${Math.max(8, (item.current / span) * 100)}%` }} /></div>
    </li>
  );
}

function QualificationTrend({ rows }: { rows: NonNullable<AnalyticsSnapshot["qualification_trend"]> }) {
  const empty = rows.every((row) => row.created === 0);
  return (
    <section className="chart-panel" aria-label="Qualification trend">
      <h2 className="text-base text-foreground">Lead acquisition and qualification</h2>
      <p className="mt-1 text-xs text-muted-foreground">Leads created each day, and how many of those leads are currently qualified. This is not a history of status changes.</p>
      {empty ? <p className="mt-3 text-sm text-muted-foreground">No leads were created in this period.</p> : (
        <div className="mt-4 h-56 min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows}>
              <XAxis dataKey="day" tickFormatter={shortDay} minTickGap={28} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} width={28} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={chartTooltip} />
              <Legend />
              <Line type="monotone" dataKey="created" name="Created" stroke="var(--primary)" strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="qualified" name="Currently qualified" stroke="var(--muted-foreground)" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <Link className="mt-3 inline-block text-sm text-primary underline" href="/crm?tab=leads">Open leads</Link>
    </section>
  );
}

function Campaigns({ campaigns }: { campaigns: NonNullable<AnalyticsSnapshot["campaigns"]> }) {
  return (
    <section className="rounded-xl border border-border bg-card p-4" aria-label="Campaign delivery">
      <h2 className="text-base text-foreground">Campaign delivery</h2>
      <p className="mt-1 text-xs text-muted-foreground">{campaigns.definition}</p>
      <p className="mt-3 text-sm">{campaigns.campaigns} campaigns created in this period.</p>
      {campaigns.deliveries.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No delivery outcomes are stored.</p> : (
        <ul className="mt-3 space-y-2 text-sm">{campaigns.deliveries.map((item) => <li key={item.status} className="flex justify-between"><span className="capitalize">{item.status}</span><span className="tabular-nums">{item.count}</span></li>)}</ul>
      )}
      <Link className="mt-3 inline-block text-sm text-primary underline" href="/campaigns">Open campaigns</Link>
    </section>
  );
}
