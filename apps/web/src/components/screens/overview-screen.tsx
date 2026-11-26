"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Building2, Inbox, Plus, ShieldCheck, TrendingUp } from "lucide-react";
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
  ["new", "New", "bg-blue-400"],
  ["contacted", "Contacted", "bg-violet-400"],
  ["qualified", "Qualified", "bg-emerald-400"],
  ["won", "Won", "bg-teal-300"],
  ["lost", "Lost", "bg-slate-500"],
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

  return (
    <div className="flex w-full min-w-0 flex-col gap-5" data-testid="overview-workspace">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5" data-testid="overview-intro">
        <div>
          <p className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            <span className={`size-1.5 rounded-full ${demonstration ? "bg-primary" : "bg-success"}`} />
            {demonstration ? "Demonstration" : "Workspace"}
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-foreground sm:text-[30px]">{timeGreeting()}</h1>
          <p className="mt-2 text-[13px] text-muted-foreground">Here’s what needs your attention across {workspace.organizationName ?? "your workspace"}.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">{organizationId ? <NewOpportunity key={organizationId} organizationId={organizationId} companies={companies.data?.items ?? []} /> : null}</div>
      </header>
      {empty ? <EmptyWorkspace /> : <>
        <Kpis data={analytics.data} />
        <PeriodSummary data={analytics.data} period={period} onPeriod={setPeriod} />
        <div className="grid gap-4 xl:grid-cols-[1.35fr_0.9fr]" data-testid="overview-top-content">
          <Pipeline data={analytics.data} />
          <Attention approvals={approvals.data?.items ?? []} pending={approvals.isPending} error={approvals.error} />
        </div>
        <div className="grid gap-4" data-testid="overview-bottom-content">
          <ActivitySection data={analytics.data} leads={leads.data?.items ?? []} companies={companies.data?.items ?? []} />
          <InquirySection inquiries={inquiries.data?.items ?? []} leads={leads.data?.items ?? []} companies={companies.data?.items ?? []} pending={inquiries.isPending} />
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
          <Button><Plus className="size-4" aria-hidden="true" />New opportunity</Button>
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
    <section className="rounded-xl border border-border bg-card p-4" aria-label="Period performance" data-testid="overview-period">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">This period</h2>
          <p className="mt-1 text-xs text-muted-foreground">{data.period ? `${formatDay(data.period.start)} to ${formatDay(data.period.end)}` : "Selected dates"}{comparison ? ` · previous ${formatDay(comparison.previous_period.start)} to ${formatDay(comparison.previous_period.end)}` : ""}</p>
        </div>
        <label className="grid gap-1 text-sm">Date range
          <select aria-label="Overview date range" className="h-9 rounded-md border border-border bg-background px-2" value={period} onChange={(event) => onPeriod(event.target.value)}>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
          </select>
        </label>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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
  return <section className="grid grid-cols-2 overflow-hidden rounded-lg border border-border bg-card shadow-sm lg:grid-cols-4" aria-label="CRM metrics" data-testid="overview-kpi-band"><Kpi href="/crm?tab=companies" label="Companies" value={data.companies_total} detail="Active customer accounts" icon={Building2} /><Kpi href="/crm?tab=leads" label="Active leads" value={active} detail={`${data.leads_total} total leads`} icon={TrendingUp} /><Kpi href="/crm?tab=inquiries" label="Customer requests" value={data.open_inquiries} detail="Open inquiries" icon={Inbox} /><Kpi href="/approvals" label="AI actions ready" value={data.approvals.pending} detail="Awaiting human review" icon={ShieldCheck} attention={data.approvals.pending > 0} /></section>;
}

function Kpi({ href, label, value, detail, attention, icon: Icon }: { href: string; label: string; value: number; detail?: string; attention?: boolean; icon: typeof Building2 }) {
  const slug = label.toLowerCase().replaceAll(" ", "-");
  return <Link data-testid={`overview-kpi-${slug}`} href={href} className="group min-w-0 border-b border-border p-4 transition hover:bg-accent/40 lg:border-b-0 lg:border-r last:border-r-0"><div className="flex items-center justify-between gap-2"><span className="flex min-w-0 items-center gap-2 text-[11px] font-medium text-muted-foreground"><span className="grid size-7 shrink-0 place-items-center rounded-md bg-primary/10 text-primary"><Icon className="size-4" /></span><span className="leading-4">{label}</span></span><ArrowUpRight className="size-4 shrink-0 text-subtle transition group-hover:text-primary" aria-hidden="true" /></div><p data-testid={`overview-kpi-${slug}-value`} className="mt-4 text-2xl font-semibold tabular-nums tracking-tight text-foreground">{value}</p>{detail ? <p className="mt-1 truncate text-[11px] text-subtle">{detail}</p> : null}{attention ? <span className="mt-3 inline-flex items-center gap-1.5 text-[11px] font-medium text-warning"><span className="size-1.5 rounded-full bg-warning" />Needs review</span> : null}</Link>;
}

function ActivitySection({ data, leads, companies }: { data: AnalyticsSnapshot; leads: Lead[]; companies: Company[] }) {
  return <section className="rounded-xl border border-border bg-card" aria-labelledby="recent-activity-title" data-testid="overview-customer-activity"><div className="flex flex-col gap-2 border-b border-border/70 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><h2 id="recent-activity-title" className="text-base font-semibold text-foreground">Customer activity</h2><p className="mt-1 text-xs text-muted-foreground">Recent conversations and changes across your accounts.</p></div><Link href="/crm?tab=leads" className="self-start text-xs font-medium text-primary sm:shrink-0">View activity →</Link></div>{data.recent_interactions.length === 0 ? <p className="px-5 py-8 text-sm text-muted-foreground">No customer activity recorded yet.</p> : <ul className="divide-y divide-border/60">{data.recent_interactions.map((item) => { const lead = leads.find((entry) => entry.id === item.lead_id); const company = lead ? companies.find((entry) => entry.id === lead.company_id) : undefined; return <li key={item.id} className="px-5 py-4"><Link href={`/crm?tab=leads&id=${item.lead_id}`} className="block rounded-md hover:bg-accent/30"><div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm font-semibold text-foreground">{company?.name ?? "Customer activity"}</span><time className="text-[11px] text-subtle">{new Date(item.created_at).toLocaleString()}</time></div><p className="mt-1 text-sm text-muted-foreground">{lead?.title ?? "Related lead"}</p><p className="mt-1 truncate text-xs text-subtle">{item.kind.replaceAll("_", " ")} · {item.summary}</p></Link></li>; })}</ul>}</section>;
}

function Pipeline({ data }: { data: AnalyticsSnapshot }) {
  const counts = STAGES.map(([status]) => data.lead_status.find((item) => item.status === status)?.count ?? 0);
  const largest = Math.max(1, ...counts);
  const active = counts.slice(0, 3).reduce((sum, count) => sum + count, 0);

  return (
    <section className="rounded-xl border border-border bg-card" aria-labelledby="pipeline-title" data-testid="overview-pipeline">
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-border px-5 py-4">
        <div>
          <h2 id="pipeline-title" className="text-base font-semibold">Pipeline overview</h2>
          <p className="mt-1 text-xs text-muted-foreground">{data.leads_total} total leads · {active} active</p>
        </div>
        <Link href="/crm?tab=leads" className="text-xs font-medium text-primary">View leads</Link>
      </div>
      {data.leads_total ? (
        <ul className="divide-y divide-border px-5">
          {STAGES.map(([status, label, color], index) => (
            <li key={status}>
              <Link href={`/crm?tab=leads&status=${status}`} className="grid grid-cols-[5rem_minmax(0,1fr)_2rem] items-center gap-2 py-3 text-xs hover:bg-accent/30 sm:grid-cols-[6rem_minmax(0,1fr)_2rem]">
                <span className="flex items-center gap-2 font-medium"><span className={`size-2 rounded-full ${color}`} aria-hidden="true" />{label}</span>
                <span className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                  <span className={`block h-full rounded-full ${color}`} style={{ width: `${(counts[index] / largest) * 100}%` }} />
                </span>
                <span className="text-right tabular-nums text-muted-foreground">{counts[index]}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : <p className="px-5 py-8 text-sm text-muted-foreground">No leads are stored in this scope.</p>}
    </section>
  );
}

function InquirySection({ inquiries, leads, companies, pending }: { inquiries: Inquiry[]; leads: Lead[]; companies: Company[]; pending: boolean }) {
  return <section className="rounded-lg border border-border/80 bg-card" aria-labelledby="inquiries-title"><div className="flex items-center justify-between border-b border-border/70 px-4 py-3"><h2 id="inquiries-title" className="text-sm font-semibold text-foreground">Open inquiries</h2><Link href="/crm?tab=inquiries" className="text-xs text-primary">View all</Link></div>{pending ? <Skeleton className="m-4 h-12" /> : inquiries.length === 0 ? <p className="px-4 py-6 text-sm text-muted-foreground">No open inquiries.</p> : <ul className="divide-y divide-border/60">{inquiries.slice(0, 5).map((item) => { const lead = leads.find((entry) => entry.id === item.lead_id); const company = companies.find((entry) => entry.id === item.company_id); return <li key={item.id} className="px-4 py-3"><Link href={`/crm?tab=inquiries&id=${item.id}`} className="flex items-center justify-between gap-3 rounded-md hover:bg-accent/30"><div className="min-w-0"><p className="truncate text-sm font-medium text-foreground">{item.subject}</p><p className="mt-1 truncate text-xs text-muted-foreground">{company?.name ?? "Company"}{lead ? ` · ${lead.title}` : ""}</p></div><span className="shrink-0 text-[11px] text-warning">Open</span></Link></li>; })}</ul>}</section>;
}

function Attention({ approvals, pending, error }: { approvals: Approval[]; pending: boolean; error: Error | null }) {
  return (
    <section className="rounded-xl border border-border bg-card" aria-labelledby="attention-title">
      <div className="flex items-start justify-between gap-2 border-b border-border px-5 py-4">
        <div>
          <h2 id="attention-title" className="text-base font-semibold">Needs attention</h2>
          <p className="mt-1 text-xs text-muted-foreground">Requests waiting for a decision.</p>
        </div>
        <Link href="/approvals" className="text-xs font-medium text-primary">View approvals</Link>
      </div>
      {error ? <div className="p-4"><RequestError error={error} /></div> : pending ? (
        <Skeleton className="m-4 h-12" />
      ) : approvals.length ? (
        <ul className="divide-y divide-border">
          {approvals.slice(0, 4).map((approval) => (
            <li key={approval.id} className="px-5 py-3">
              <Link href={`/approvals?approval=${approval.id}`} className="flex items-center gap-3 rounded-md hover:bg-accent/30">
                <span className="grid size-8 shrink-0 place-items-center rounded-md bg-warning/10 text-warning"><ShieldCheck className="size-4" aria-hidden="true" /></span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium capitalize">{approval.action_type.replaceAll("_", " ")}</span>
                  <span className="block text-xs text-muted-foreground">Awaiting review</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : <p className="px-5 py-8 text-sm text-muted-foreground">No requests are waiting for approval.</p>}
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
