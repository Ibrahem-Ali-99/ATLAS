"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, BadgeCheck, BriefcaseBusiness, Building2, CheckCircle2, ChevronRight, MessageSquareText, Plus, Search } from "lucide-react";
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
      {empty ? <EmptyWorkspace /> : <>
        <Kpis data={analytics.data} />
        <div className="overview-grid" data-testid="overview-top-content">
          <Pipeline data={analytics.data} />
          <Attention approvals={approvals.data?.items ?? []} pending={approvals.isPending} error={approvals.error} />
        </div>
        <ActivitySection data={analytics.data} leads={leads.data?.items ?? []} companies={companies.data?.items ?? []} />
        <div className="overview-grid" data-testid="overview-bottom-content">
          <InquirySection inquiries={inquiries.data?.items ?? []} leads={leads.data?.items ?? []} companies={companies.data?.items ?? []} pending={inquiries.isPending} />
          <PeriodSummary data={analytics.data} period={period} onPeriod={setPeriod} />
        </div>
      </>}
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

function PeriodSummary({ data, period, onPeriod }: { data: AnalyticsSnapshot; period: string; onPeriod: (value: string) => void }) {
  const sales = data.sales;
  const comparison = data.comparison;
  const money = sales?.currencies ?? [];
  return (
    <section className="panel" aria-label="Period performance" data-testid="overview-period">
      <div className="panel-header">
        <div>
          <h2>This period</h2>
          <p>{data.period ? `${formatDay(data.period.start)} to ${formatDay(data.period.end)}` : "Selected dates"}{comparison ? ` · previous ${formatDay(comparison.previous_period.start)} to ${formatDay(comparison.previous_period.end)}` : ""}</p>
        </div>
        <label className="field">Date range
          <select aria-label="Overview date range" value={period} onChange={(event) => onPeriod(event.target.value)}>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
          </select>
        </label>
      </div>
      <div className="grid gap-3 p-4 sm:grid-cols-2">
        <PeriodLink href="/crm?tab=leads" label="Leads created" value={comparison?.leads_created.current ?? 0} delta={comparison?.leads_created} />
        <PeriodLink href="/crm?tab=opportunities" label="Opportunities" value={sales?.opportunities_total ?? 0} delta={comparison?.opportunities_created} />
        <PeriodLink href="/inbox" label="Conversations" value={comparison?.conversations.current ?? 0} delta={comparison?.conversations} />
        <PeriodLink href="/workflows" label="Overdue tasks" value={sales?.tasks_overdue ?? 0} detail={`${sales?.tasks_completed ?? 0} completed in this period`} />
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div>
          <h3 className="text-sm font-medium">Pipeline value</h3>
          {money.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No opportunity amounts are stored for this period.</p> : (
            <ul className="mt-2 space-y-1 text-sm">{money.map((item) => <li key={item.currency} className="flex justify-between"><span>{item.currency}</span><span className="tabular-nums">{item.value == null ? "No amount stored" : item.value.toLocaleString()}</span></li>)}</ul>
          )}
          <p className="mt-2 text-xs text-muted-foreground">{sales?.win_rate == null ? "No won or lost opportunities in this period." : `${Math.round(sales.win_rate * 100)}% won, ${sales.loss_rate == null ? "" : `${Math.round(sales.loss_rate * 100)}% lost`}. Amounts stay in their own currency.`}</p>
          <Link className="mt-2 inline-block text-xs font-medium text-primary" href="/analytics">Open analytics</Link>
        </div>
        <div>
          <h3 className="text-sm font-medium">Appointments and approvals</h3>
          <p className="mt-2 text-sm">{data.calendar.booked} booked, {data.calendar.cancelled} cancelled.</p>
          <p className="mt-1 text-sm">{data.approvals.pending} approvals waiting now.</p>
          <div className="mt-2 flex flex-wrap gap-3 text-xs font-medium"><Link className="text-primary" href="/crm?tab=leads">Leads</Link><Link className="text-primary" href="/approvals">Approvals</Link><Link className="text-primary" href="/workflows">Workflows</Link></div>
        </div>
      </div>
    </section>
  );
}

function PeriodLink({ href, label, value, delta, detail }: { href: string; label: string; value: number; delta?: { delta: number; previous: number; change_rate: number | null }; detail?: string }) {
  const change = !delta ? null : delta.change_rate == null ? "No earlier activity" : `${delta.delta > 0 ? "+" : ""}${Math.round(delta.change_rate * 1000) / 10}% vs previous`;
  return <Link href={href} className="rounded-lg border border-border p-3 hover:bg-accent/40"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>{change ? <p className="mt-1 text-xs text-muted-foreground">{change}</p> : null}{detail ? <p className="mt-1 text-xs text-muted-foreground">{detail}</p> : null}</Link>;
}

function Kpis({ data }: { data: AnalyticsSnapshot }) {
  const active = data.lead_status.filter((item) => ["new", "contacted", "qualified"].includes(item.status)).reduce((sum, item) => sum + item.count, 0);
  return (
    <section className="metric-grid" aria-label="Workspace metrics" data-testid="overview-kpi-band">
      <Kpi href="/crm?tab=companies" testId="overview-kpi-companies" label="Companies" value={data.companies_total} detail="Total accounts" icon={Building2} />
      <Kpi href="/crm?tab=leads" testId="overview-kpi-active-leads" label="Active leads" value={active} detail={`${data.leads_total} total leads`} icon={BriefcaseBusiness} />
      <Kpi href="/crm?tab=inquiries" testId="overview-kpi-customer-requests" label="Open inquiries" value={data.open_inquiries} detail="Awaiting response" icon={MessageSquareText} />
      <Kpi href="/approvals" testId="overview-kpi-pending-approvals" label="Pending approvals" value={data.approvals.pending} detail="Needs review" icon={BadgeCheck} />
    </section>
  );
}

function Kpi({ href, testId, label, value, detail, icon: Icon }: { href: string; testId: string; label: string; value: number; detail?: string; icon: typeof Building2 }) {
  return (
    <Link data-testid={testId} href={href} className="metric-card">
      <span className="metric-icon"><Icon size={16} /></span>
      <span className="metric-copy">
        <span className="metric-label">{label}</span>
        <strong data-testid={`${testId}-value`}>{value}</strong>
        {detail ? <span className="metric-meta">{detail}</span> : null}
      </span>
      <ChevronRight className="metric-arrow" size={16} />
    </Link>
  );
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
        <div className="pipeline-list">
          {STAGES.map(([status, label, tone], index) => (
            <Link key={status} href={`/crm?tab=leads&status=${status}`} className="pipeline-row">
              <span className={`status-dot dot-${tone}`} />
              <span className="pipeline-label">{label}</span>
              <div className="bar-track"><span className={`bar-fill fill-${tone}`} style={{ width: `${Math.max(8, (counts[index] / largest) * 100)}%` }} /></div>
              <strong>{counts[index]}</strong>
              <ChevronRight size={14} />
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

function EmptyWorkspace() { return <section className="rounded-lg border border-dashed border-border bg-card px-5 py-8"><h2 className="text-lg font-semibold text-foreground">Your workspace is ready</h2><p className="mt-2 max-w-lg text-sm text-muted-foreground">Create your first company or lead to start tracking customer work here.</p><Link href="/crm?tab=companies" className="mt-4 inline-flex rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">Open CRM</Link></section>; }
function OverviewSkeleton() { return <div className="space-y-5"><Skeleton className="h-16 w-full" /><div className="grid gap-3 sm:grid-cols-4"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div><Skeleton className="h-64 w-full" /></div>; }
function timeGreeting(): string { const hour = new Date().getHours(); return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"; }
function formatDay(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return value;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
