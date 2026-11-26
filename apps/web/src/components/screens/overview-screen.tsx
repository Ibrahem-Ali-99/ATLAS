"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, CheckCircle2, ChevronRight, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { Approval } from "@/lib/agent";
import { listApprovals } from "@/lib/agent-api";
import { sessionQueryOptions } from "@/lib/api";
import { isDemoSession } from "@/lib/demo-session";
import { getAnalytics, type AnalyticsSnapshot } from "@/lib/intelligence";
import { createOpportunity, listPipelineStages } from "@/lib/opportunities";
import { listCompanies, listInquiries, listLeads } from "@/lib/records-api";
import type { Company, Inquiry, Lead } from "@/lib/records";
import { useWorkspace } from "@/lib/use-workspace";

const STAGES = [
  ["new", "New", "blue"],
  ["contacted", "Contacted", "purple"],
  ["qualified", "Qualified", "amber"],
  ["won", "Won", "green"],
  ["lost", "Lost", "red"],
] as const;

export function OverviewScreen() {
  const workspace = useWorkspace();
  const session = useQuery(sessionQueryOptions);
  const organizationId = workspace.organizationId;
  const demonstration = isDemoSession(session.data);
  const [period, setPeriod] = useState("30d");
  const scope = "all";
  const analytics = useQuery({ queryKey: ["analytics", organizationId, scope, period], queryFn: () => getAnalytics(organizationId ?? "", scope, { period }), enabled: Boolean(organizationId) });
  const companies = useQuery({ queryKey: ["overview-companies", organizationId], queryFn: () => listCompanies(organizationId ?? "", { pageSize: 100 }), enabled: Boolean(organizationId) });
  const leads = useQuery({ queryKey: ["overview-leads", organizationId], queryFn: () => listLeads(organizationId ?? "", { pageSize: 100 }), enabled: Boolean(organizationId) });
  const inquiries = useQuery({ queryKey: ["overview-inquiries", organizationId], queryFn: () => listInquiries(organizationId ?? "", { pageSize: 100 }), enabled: Boolean(organizationId) });
  const approvals = useQuery({ queryKey: ["overview-approvals", organizationId], queryFn: () => listApprovals(organizationId ?? "", { status: "pending" }), enabled: Boolean(organizationId) });

  if (analytics.isPending) return <OverviewSkeleton />;
  if (analytics.isError) return <RequestError error={analytics.error} />;
  if (!analytics.data) return null;
  const empty = analytics.data.companies_total === 0 && analytics.data.leads_total === 0 && analytics.data.inquiries_total === 0;
  const firstName = session.data?.user.full_name.split(" ")[0] ?? "";

  return (
    <div data-testid="overview-workspace">
      <div className="page-heading" data-testid="overview-intro">
        <div>
          <div className="eyebrow"><span className="live-dot" />{demonstration ? "Demonstration" : "Live workspace"}</div>
          <h1>{timeGreeting()}{firstName ? `, ${firstName}` : ""}</h1>
          <p>Here’s what needs your attention across {workspace.organizationName ?? "your workspace"}.</p>
        </div>
        <div className="page-actions">{organizationId ? <NewOpportunity key={organizationId} organizationId={organizationId} companies={companies.data?.items ?? []} /> : null}</div>
      </div>
      {empty ? <EmptyWorkspace /> : <div className="saas-overview">
        <Kpis data={analytics.data} period={period} onPeriod={setPeriod} />
        <div className="saas-split" data-testid="overview-top-content">
          <Pipeline data={analytics.data} />
          <div className="saas-stack">
            <Attention approvals={approvals.data?.items ?? []} pending={approvals.isPending} error={approvals.error} />
            <Recommendations data={analytics.data} />
          </div>
        </div>
        <div className="saas-split" data-testid="overview-bottom-content">
          <ActivitySection data={analytics.data} leads={leads.data?.items ?? []} companies={companies.data?.items ?? []} />
          <div className="saas-stack">
            <InquirySection inquiries={inquiries.data?.items ?? []} leads={leads.data?.items ?? []} companies={companies.data?.items ?? []} pending={inquiries.isPending} />
            <Appointments data={analytics.data} />
          </div>
        </div>
      </div>}
    </div>
  );
}

function NewOpportunity({ organizationId, companies }: { organizationId: string; companies: Company[] }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [created, setCreated] = useState(false);
  const stages = useQuery({
    queryKey: ["pipeline-stages", organizationId],
    queryFn: () => listPipelineStages(organizationId),
    enabled: open,
  });
  const firstStage = stages.data?.[0]?.key;
  const save = useMutation({
    mutationFn: (stage: string) => createOpportunity(organizationId, {
      title: title.trim(), stage, ...(company ? { company_id: company } : {}),
    }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["opportunities", organizationId] });
      setTitle("");
      setCompany("");
      setCreated(true);
      setOpen(false);
    },
  });

  return (
    <>
      <Dialog open={open} onOpenChange={(next) => {
        if (save.isPending) return;
        if (next) save.reset();
        setOpen(next);
      }}>
        <DialogTrigger asChild>
          <Button className="button button-primary button-md"><Plus size={16} aria-hidden="true" />New opportunity</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New opportunity</DialogTitle>
            <DialogDescription>Add an opportunity to your CRM pipeline.</DialogDescription>
          </DialogHeader>
          <form className="mt-4 grid gap-4" onSubmit={(event) => {
            event.preventDefault();
            if (firstStage && title.trim()) save.mutate(firstStage);
          }}>
            <label className="grid gap-1.5 text-sm">Opportunity name
              <Input required maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-sm">Company
              <select value={company} onChange={(event) => setCompany(event.target.value)} className="h-9 rounded-md border border-input bg-background px-2">
                <option value="">No company selected</option>
                {companies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
            {stages.error ? <RequestError error={stages.error} /> : null}
            {save.error ? <RequestError error={save.error} /> : null}
            <Button type="submit" disabled={!firstStage || !title.trim() || save.isPending}>
              {save.isPending ? "Creating…" : "Create opportunity"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
      {created ? <p role="status" className="text-xs text-success">Opportunity created. <Link href="/crm?tab=opportunities" className="underline">Open pipeline</Link></p> : null}
    </>
  );
}

function Kpis({ data, period, onPeriod }: { data: AnalyticsSnapshot; period: string; onPeriod: (value: string) => void }) {
  const active = data.lead_status.filter((item) => ["new", "contacted", "qualified"].includes(item.status)).reduce((sum, item) => sum + item.count, 0);
  const inquirySeries = (data.customer_activity ?? []).map((row) => row.inquiries);
  const leadSeries = data.lead_trend.map((row) => row.count);
  return (
    <section aria-label="Workspace metrics" data-testid="overview-kpi-band">
      <div className="flex items-center justify-end" style={{ marginBottom: 8 }}>
        <label className="toolbar-select">Date range
          <select aria-label="Overview date range" value={period} onChange={(event) => onPeriod(event.target.value)}>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
          </select>
        </label>
      </div>
      <div className="kpi-band">
        <Kpi href="/crm?tab=companies" testId="overview-kpi-companies" label="Companies" value={data.companies_total} detail="Accounts in this workspace" />
        <Kpi href="/crm?tab=leads" testId="overview-kpi-active-leads" label="Active leads" value={active} detail={`${data.leads_total} total leads`} series={leadSeries} delta={data.comparison?.leads_created} />
        <Kpi href="/crm?tab=inquiries" testId="overview-kpi-customer-requests" label="Open inquiries" value={data.open_inquiries} detail="Waiting on a reply" series={inquirySeries} />
        <Kpi href="/approvals" testId="overview-kpi-pending-approvals" label="Pending approvals" value={data.approvals.pending} detail="Decisions still open" />
      </div>
    </section>
  );
}

function Kpi({ href, testId, label, value, detail, series, delta }: {
  href: string; testId: string; label: string; value: number; detail: string;
  series?: number[]; delta?: { delta: number; change_rate: number | null };
}) {
  const tone = !delta || delta.change_rate == null ? "flat" : delta.delta < 0 ? "down" : "up";
  const change = !delta || delta.change_rate == null ? "No earlier period" : `${delta.delta > 0 ? "+" : ""}${Math.round(delta.change_rate * 1000) / 10}% vs previous`;
  return (
    <Link data-testid={testId} href={href} className="kpi-card">
      <header><span>{label}</span></header>
      <strong data-testid={`${testId}-value`}>{value}</strong>
      <div className="kpi-foot">
        <div><small>{detail}</small><div className={`kpi-delta ${tone}`}>{change}</div></div>
        {series && series.some((point) => point > 0) ? <Sparkline points={sparkPoints(series)} /> : null}
      </div>
    </Link>
  );
}

function sparkPoints(points: number[]): number[] {
  if (points.length <= 12) return points;
  const size = Math.ceil(points.length / 12);
  const buckets: number[] = [];
  for (let index = 0; index < points.length; index += size) {
    buckets.push(points.slice(index, index + size).reduce((sum, point) => sum + point, 0));
  }
  return buckets;
}

function Sparkline({ points }: { points: number[] }) {
  const max = Math.max(...points, 1);
  const width = 108;
  const height = 36;
  const path = points.map((point, index) => {
    const x = points.length === 1 ? width : (index / (points.length - 1)) * width;
    const y = height - 3 - (point / max) * (height - 8);
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return <svg className="spark" viewBox={`0 0 ${width} ${height}`} aria-hidden="true"><path d={path} /></svg>;
}

function ActivitySection({ data, leads, companies }: { data: AnalyticsSnapshot; leads: Lead[]; companies: Company[] }) {
  return (
    <section className="panel activity-panel" aria-labelledby="recent-activity-title" data-testid="overview-customer-activity">
      <div className="panel-header activity-header">
        <div>
          <h2 id="recent-activity-title">Recent customer activity</h2>
          <p>Latest updates across your accounts</p>
        </div>
        <Link href="/crm?tab=leads" className="text-button">View activity <ArrowRight size={14} /></Link>
      </div>
      {data.recent_interactions.length === 0 ? (
        <div className="empty-state"><Search size={22} /><strong>No activity yet</strong><p>Customer updates will appear here.</p></div>
      ) : (
        <div className="activity-table" role="table" aria-label="Recent customer activity">
          <div className="activity-row table-head" role="row"><span>Company</span><span>Activity</span><span>Time</span><span /></div>
          {data.recent_interactions.map((item) => {
            const lead = leads.find((entry) => entry.id === item.lead_id);
            const company = lead ? companies.find((entry) => entry.id === lead.company_id) : undefined;
            const name = company?.name ?? "Customer";
            return (
              <Link className="activity-row" role="row" key={item.id} href={`/crm?tab=leads&id=${item.lead_id}`}>
                <span className="company-cell"><span className="avatar avatar-blue avatar-sm">{name.slice(0, 2).toUpperCase()}</span><strong>{name}</strong></span>
                <span className="activity-copy"><strong>{lead?.title ?? "Related lead"}</strong><small>{item.summary}</small></span>
                <span className="time-cell">{new Date(item.created_at).toLocaleString()}</span>
                <ChevronRight size={16} />
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}

function Pipeline({ data }: { data: AnalyticsSnapshot }) {
  const counts = STAGES.map(([status]) => data.lead_status.find((item) => item.status === status)?.count ?? 0);
  const largest = Math.max(1, ...counts);
  const active = counts.slice(0, 3).reduce((sum, count) => sum + count, 0);

  return (
    <section className="panel pipeline-panel" aria-labelledby="pipeline-title" data-testid="overview-pipeline">
      <div className="panel-header">
        <div>
          <h2 id="pipeline-title">Lead pipeline</h2>
          <p>{data.leads_total} leads · {active} active</p>
        </div>
        <Link href="/crm?tab=opportunities" className="text-button">View pipeline <ArrowRight size={14} /></Link>
      </div>
      {data.leads_total ? (
        <div className="stage-board">
          {STAGES.map(([status, label, tone], index) => (
            <Link key={status} href={`/crm?tab=leads&status=${status}`} className="stage-col">
              <header><span className={`status-dot dot-${tone}`} /><span>{label}</span><strong>{counts[index]}</strong></header>
              <div className="stage-meter" aria-hidden="true"><b className={`fill-${tone}`} style={{ width: `${Math.max(8, (counts[index] / largest) * 100)}%` }} /></div>
            </Link>
          ))}
        </div>
      ) : <div className="empty-state"><strong>No leads yet</strong><p>New leads will appear across these stages.</p></div>}
    </section>
  );
}

function InquirySection({ inquiries, leads, companies, pending }: { inquiries: Inquiry[]; leads: Lead[]; companies: Company[]; pending: boolean }) {
  return (
    <section className="panel" aria-labelledby="inquiries-title">
      <div className="panel-header">
        <div><h2 id="inquiries-title">Open inquiries</h2><p>Requests waiting on a reply</p></div>
        <Link href="/crm?tab=inquiries" className="text-button">View all <ArrowRight size={14} /></Link>
      </div>
      {pending ? <Skeleton className="m-4 h-12" /> : inquiries.length === 0 ? <div className="empty-state"><strong>No open inquiries</strong><p>New customer requests will show up here.</p></div> : (
        <div className="activity-table">
          {inquiries.slice(0, 5).map((item) => {
            const lead = leads.find((entry) => entry.id === item.lead_id);
            const company = companies.find((entry) => entry.id === item.company_id);
            return (
              <Link key={item.id} href={`/crm?tab=inquiries&id=${item.id}`} className="activity-row">
                <span className="company-cell"><strong>{company?.name ?? "Company"}</strong></span>
                <span className="activity-copy"><strong>{item.subject}</strong><small>{lead?.title ?? "Inquiry"}</small></span>
                <span className="time-cell">Open</span>
                <ChevronRight size={16} />
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}

function Attention({ approvals, pending, error }: { approvals: Approval[]; pending: boolean; error: Error | null }) {
  return (
    <section className="panel attention-panel" aria-labelledby="attention-title">
      <div className="panel-header">
        <div>
          <h2 id="attention-title">Needs attention</h2>
          <p>Priority items for today</p>
        </div>
        <span className="badge badge-amber">{approvals.length} pending</span>
      </div>
      {error ? <div className="p-4"><RequestError error={error} /></div> : pending ? (
        <Skeleton className="m-4 h-12" />
      ) : approvals.length ? (
        <div className="approval-list">
          {approvals.slice(0, 3).map((approval) => (
            <article className="approval-item" key={approval.id}>
              <div className="approval-icon"><AlertCircle size={16} /></div>
              <div>
                <h3 className="capitalize">{approval.action_type.replaceAll("_", " ")}</h3>
                <p>Waiting for a decision</p>
                <div className="approval-actions">
                  <Link href={`/approvals?approval=${approval.id}`} className="button button-primary button-sm">Review</Link>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : <div className="empty-state"><CheckCircle2 size={22} /><strong>All caught up</strong><p>There are no approvals waiting for review.</p></div>}
    </section>
  );
}

function Recommendations({ data }: { data: AnalyticsSnapshot }) {
  const items = [
    data.approvals.pending > 0 ? { href: "/approvals", title: `${data.approvals.pending} approval${data.approvals.pending === 1 ? "" : "s"} waiting`, detail: "A decision is required before the stored action can run." } : null,
    data.open_inquiries > 0 ? { href: "/crm?tab=inquiries", title: `${data.open_inquiries} open inquiries`, detail: "These customer requests do not have a recorded resolution." } : null,
    (data.sales?.tasks_overdue ?? 0) > 0 ? { href: "/workflows", title: `${data.sales?.tasks_overdue} overdue tasks`, detail: "Follow-ups that are past their due date." } : null,
    data.comparison && data.comparison.leads_created.delta < 0 ? { href: "/analytics", title: "Fewer new leads than the previous period", detail: `${data.comparison.leads_created.current} created, ${data.comparison.leads_created.previous} in the previous window.` } : null,
  ].filter((item) => item !== null);
  return (
    <section className="panel" aria-label="Recommendations">
      <div className="panel-header"><div><h2>Recommended next</h2><p>From the records in this period</p></div></div>
      {items.length === 0 ? <div className="empty-state"><strong>Nothing urgent</strong><p>No overdue tasks, open inquiries, or waiting approvals are stored.</p></div> : (
        <div className="reco-list">{items.map((item) => (
          <Link key={item.href + item.title} href={item.href}><span className="status-dot dot-amber" /><span><strong>{item.title}</strong><small>{item.detail}</small></span><ChevronRight size={14} /></Link>
        ))}</div>
      )}
    </section>
  );
}

function Appointments({ data }: { data: AnalyticsSnapshot }) {
  return (
    <section className="panel" aria-label="Appointments">
      <div className="panel-header"><div><h2>Appointments</h2><p>Booked in the selected period</p></div><Link href="/crm?tab=leads" className="text-button">Open leads</Link></div>
      <div className="appt-list">
        <div><span className="status-dot dot-green" /><span><strong>{data.calendar.booked} booked</strong><small>{data.calendar.cancelled} cancelled in the same window</small></span></div>
        <div><span className="status-dot dot-blue" /><span><strong>{data.approvals.pending} approvals still open</strong><small>Review them before a reserved time is confirmed.</small></span><Link href="/approvals">Review</Link></div>
      </div>
    </section>
  );
}

function EmptyWorkspace() { return <section className="rounded-lg border border-dashed border-border bg-card px-5 py-8"><h2 className="text-lg font-semibold text-foreground">Your workspace is ready</h2><p className="mt-2 max-w-lg text-sm text-muted-foreground">Create your first company or lead to start tracking customer work here.</p><Link href="/crm?tab=companies" className="mt-4 inline-flex rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">Open CRM</Link></section>; }
function OverviewSkeleton() { return <div className="space-y-5"><Skeleton className="h-16 w-full" /><div className="grid gap-3 sm:grid-cols-4"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div><Skeleton className="h-64 w-full" /></div>; }
function timeGreeting(): string { const hour = new Date().getHours(); return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"; }
