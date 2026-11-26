"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { DataScopeControl } from "@/components/data-scope";
import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Skeleton } from "@/components/ui/skeleton";
import { getAnalytics, type AnalyticsSnapshot, type StatusCount } from "@/lib/intelligence";
import { listTeam } from "@/lib/organization";
import { isDataScope, type DataScope } from "@/lib/provenance";
import { useWorkspace } from "@/lib/use-workspace";

export function AnalyticsScreen() {
  const { organizationId } = useWorkspace();
  return organizationId ? <AnalyticsWorkspace key={organizationId} organizationId={organizationId} /> : null;
}

function AnalyticsWorkspace({ organizationId }: { organizationId: string }) {
  const [scope, setScope] = useState<DataScope>(() => storedScope(organizationId));
  const [period, setPeriod] = useState("30d");
  const [channel, setChannel] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [ownerUserId, setOwnerUserId] = useState("");
  const team = useQuery({ queryKey: ["analytics-team", organizationId], queryFn: () => listTeam(organizationId) });
  const custom = period === "custom";
  const span = (Date.parse(endDate) - Date.parse(startDate)) / 86_400_000;
  const valid = !custom || (Boolean(startDate && endDate) && span >= 0 && span <= 365);
  const filters = { period, channel, startDate: custom ? startDate : "", endDate: custom ? endDate : "", ownerUserId };
  const analytics = useQuery({
    queryKey: ["analytics", organizationId, scope, filters],
    queryFn: () => getAnalytics(organizationId, scope, filters),
    enabled: valid,
  });

  return (
    <div className="flex w-full min-w-0 flex-col gap-5">
      <PageHeader title="Analytics" eyebrow="Business activity">Review customer activity, pipeline movement, and operational outcomes.</PageHeader>
      <section aria-label="Analytics filters" className="space-y-3 rounded-xl border border-border bg-card p-4">
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
        </div>
        <DataScopeControl value={scope} advanced onChange={(next) => {
          setScope(next);
          window.localStorage.setItem(`atlas.dashboard.scope.${organizationId}`, next);
        }} />
      </section>
      {!valid ? <p role="status" className="text-sm text-muted-foreground">Choose a start and end date for a range of up to 366 days.</p> :
        analytics.isPending ? <Skeleton className="h-40 w-full" /> :
          analytics.isError ? <RequestError error={analytics.error} /> : <AnalyticsBody data={analytics.data} />}
    </div>
  );
}

function AnalyticsBody({ data }: { data: AnalyticsSnapshot }) {
  const rate = data.conversion.rate === null ? "Not enough closed leads" : `${Math.round(data.conversion.rate * 1000) / 10}%`;
  const automation =
    data.automation.success_rate === null ? "—" : `${Math.round(data.automation.success_rate * 1000) / 10}%`;
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
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Active companies" value={String(data.companies_total)} detail="Customer accounts in the selected scope." />
        <Metric label="Leads" value={String(data.leads_total)} detail="Leads in the selected scope." />
        <Metric label="Open inquiries" value={String(data.open_inquiries)} detail="Customer requests in the selected scope." />
        <Metric
          label="Won or lost"
          value={rate}
          detail={`${data.conversion.won} won, ${data.conversion.lost} lost. ${data.conversion.definition}`}
        />
        <Metric label="Automation" value={automation} detail={data.automation.success_rate === null ? "No completed or failed runs" : data.automation.definition} />
      </div>
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        {data.customer_activity ? <CustomerActivity rows={data.customer_activity} /> : null}
        <LeadPipeline data={data} />
      </div>
      {data.sales ? <OpportunityAnalytics sales={data.sales} /> : null}
      {data.support ? <Metric label="First response" value={data.support.average_first_response_seconds === null ? "Unavailable" : responseTime(data.support.average_first_response_seconds)} detail={`${data.support.first_response_sample_size} conversations with a persisted response.`} /> : null}
      {data.sales ? <TrendSection title="Pipeline value by stage and currency" rows={data.sales.stage_trend.map((item) => ({ day: item.day, label: `${item.stage} · ${item.currency}`, value: item.value }))} unit="value" /> : null}
      {data.support ? <TrendSection title="Conversation volume by channel" rows={data.support.volume_trend.map((item) => ({ day: item.day, label: item.channel, value: item.count }))} unit="conversations" /> : null}
      {data.ai ? <TrendSection title="AI requests and failures" rows={data.ai.trend.map((item) => ({ day: item.day, label: item.status, value: item.count }))} unit="requests" /> : null}
      {data.workflow_performance ? <section className="rounded-xl border border-border bg-card p-4" aria-label="Workflow performance"><h2 className="text-base text-foreground">Workflow performance</h2><div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3"><Metric label="Executions" value={String(data.workflow_performance.total)} detail={`${data.workflow_performance.pending} pending · ${data.workflow_performance.running} running.`} /><Metric label="Workflow success" value={data.workflow_performance.success_rate === null ? "Unavailable" : `${Math.round(data.workflow_performance.success_rate * 100)}%`} detail={`${data.workflow_performance.successful} successful / ${data.workflow_performance.denominator} terminal executions.`} /><Metric label="Failed workflows" value={String(data.workflow_performance.failed)} detail="Failed and needs-attention terminal runs." /></div><TrendSection title="Successful versus failed executions" rows={data.workflow_performance.trend.filter((item) => ["completed", "failed", "needs_attention"].includes(item.status)).map((item) => ({ day: item.day, label: item.status, value: item.count }))} unit="runs" /></section> : null}
      {data.support || data.ai || data.evaluation ? <div className="grid gap-3 md:grid-cols-3">{data.support ? <Metric label="Human handoffs" value={String(data.support.handoffs)} detail={`${data.support.by_channel.length} channel/status groups.`} /> : null}{data.ai ? <Metric label="AI requests" value={String(data.ai.requests)} detail={data.ai.failure_rate === null ? "No recorded AI operations." : `${Math.round(data.ai.failure_rate * 1000) / 10}% failed`} /> : null}{data.evaluation ? <Metric label="Evaluation pass rate" value={data.evaluation.pass_rate === null ? "Unavailable" : `${Math.round(data.evaluation.pass_rate * 1000) / 10}%`} detail={`${data.evaluation.passed} of ${data.evaluation.executed} cases passed.`} /> : null}</div> : null}
      <section className="rounded-xl border border-border bg-card p-4">
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
              <Line type="monotone" dataKey="count" stroke="var(--primary)" strokeWidth={2} dot={false} isAnimationActive={false} />
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


function LeadPipeline({ data }: { data: AnalyticsSnapshot }) {
  return (
      <section className="rounded-xl border border-border bg-card p-4">
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
    <section className="min-w-0 rounded-xl border border-border bg-card p-5" aria-labelledby="customer-activity-heading">
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
    if (item.stage !== "won") continue;
    const currency = won.get(item.currency) ?? { count: 0, value: 0 };
    won.set(item.currency, { count: currency.count + item.count, value: currency.value + item.value });
  }
  return (
    <section className="min-w-0 rounded-xl border border-border bg-card p-5" aria-label="Sales analytics">
      <h2 className="font-semibold">Opportunity pipeline</h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <Metric label="Opportunities" value={String(sales.opportunities_total)} detail={`${sales.won.count} won · ${sales.lost.count} lost`} />
        <Metric label="Win rate" value={sales.win_rate === null ? "Unavailable" : `${Math.round(sales.win_rate * 100)}%`} detail="Won opportunities as a share of all opportunities created in this period." />
        <Metric label="Lead conversion" value={conversion.rate === null ? "Unavailable" : `${Math.round(conversion.rate * 100)}%`} detail={`${conversion.converted_leads} of ${conversion.eligible_leads} eligible leads converted.`} />
      </div>
      {sales.by_stage.length ? (
        <ul className="mt-4 divide-y divide-border">
          {sales.by_stage.map((stage) => (
            <li key={stage.stage} className="flex justify-between gap-3 py-2 text-sm">
              <span className="capitalize">{stage.stage.replaceAll("_", " ")}</span>
              <span className="tabular-nums text-muted-foreground">{stage.count}</span>
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
                    <td className="py-2 pr-3 font-medium">{currency}</td><td className="pr-3">{value.toLocaleString()}</td>
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

function storedScope(organizationId: string): DataScope {
  if (typeof window === "undefined") return "all";
  const saved = window.localStorage.getItem(`atlas.dashboard.scope.${organizationId}`);
  return isDataScope(saved) ? saved : "all";
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  const slug = label.toLowerCase().replaceAll(" ", "-");
  return (
    <section data-testid={`analytics-metric-${slug}`} className="rounded-xl border border-border bg-card p-4">
      <p className="text-xs uppercase tracking-[0.12em] text-subtle">{label}</p>
      <p data-testid={`analytics-metric-${slug}-value`} className="mt-3 text-2xl tabular-nums text-foreground">{value}</p>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{detail}</p>
    </section>
  );
}
