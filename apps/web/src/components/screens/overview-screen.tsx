"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { DataScopeControl } from "@/components/data-scope";
import { RequestError } from "@/components/request-error";
import { Skeleton } from "@/components/ui/skeleton";
import type { Approval } from "@/lib/agent";
import { listApprovals } from "@/lib/agent-api";
import { getAnalytics, type AnalyticsSnapshot } from "@/lib/intelligence";
import { listCompanies, listInquiries, listLeads } from "@/lib/records-api";
import type { Company, Inquiry, Lead } from "@/lib/records";
import { isDataScope, type DataScope } from "@/lib/provenance";
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
  const organizationId = workspace.organizationId;
  const [scopeByOrganization, setScopeByOrganization] = useState<Record<string, DataScope>>({});
  const scope = organizationId ? scopeByOrganization[organizationId] ?? storedScope(organizationId) : "all";
  const analytics = useQuery({ queryKey: ["analytics", organizationId, scope], queryFn: () => getAnalytics(organizationId ?? "", scope), enabled: Boolean(organizationId) });
  const companies = useQuery({ queryKey: ["overview-companies", organizationId], queryFn: () => listCompanies(organizationId ?? "", { pageSize: 100 }), enabled: Boolean(organizationId) });
  const leads = useQuery({ queryKey: ["overview-leads", organizationId], queryFn: () => listLeads(organizationId ?? "", { pageSize: 100 }), enabled: Boolean(organizationId) });
  const inquiries = useQuery({ queryKey: ["overview-inquiries", organizationId], queryFn: () => listInquiries(organizationId ?? "", { pageSize: 100 }), enabled: Boolean(organizationId) });
  const approvals = useQuery({ queryKey: ["overview-approvals", organizationId], queryFn: () => listApprovals(organizationId ?? "", { status: "pending" }), enabled: Boolean(organizationId) });

  const selectScope = (next: DataScope) => {
    if (!organizationId) return;
    setScopeByOrganization((current) => ({ ...current, [organizationId]: next }));
    window.localStorage.setItem(`atlas.dashboard.scope.${organizationId}`, next);
  };

  if (analytics.isPending) return <OverviewSkeleton />;
  if (analytics.isError) return <RequestError error={analytics.error} />;
  if (!analytics.data) return null;
  const empty = analytics.data.companies_total === 0 && analytics.data.leads_total === 0 && analytics.data.inquiries_total === 0;

  return (
    <div className="mx-auto flex w-full max-w-[1118px] min-w-0 flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border/70 pb-4">
        <div><p className="text-xs text-muted-foreground">{workspace.organizationName ?? "Workspace"}</p><h1 className="mt-2 text-3xl font-semibold tracking-tight text-foreground">Overview</h1><p className="mt-2 text-sm text-muted-foreground">Here’s what needs your attention across the business.</p></div>
        <div className="flex flex-wrap items-center gap-2"><DataScopeControl value={scope} onChange={selectScope} advanced /><Link href="/crm?tab=leads" className="rounded-md bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm hover:opacity-90">+ New opportunity</Link></div>
      </header>
      {empty ? <EmptyWorkspace /> : <>
        <Kpis data={analytics.data} />
        <div className="grid gap-4 xl:grid-cols-[1.35fr_0.9fr]"><ActivitySection data={analytics.data} leads={leads.data?.items ?? []} companies={companies.data?.items ?? []} /><Pipeline data={analytics.data} /></div>
        <div className={approvals.isPending || (approvals.data?.items.length ?? 0) > 0 ? "grid gap-4 xl:grid-cols-[1.35fr_0.9fr]" : "grid gap-4"}><InquirySection inquiries={inquiries.data?.items ?? []} leads={leads.data?.items ?? []} companies={companies.data?.items ?? []} pending={inquiries.isPending} /><Attention approvals={approvals.data?.items ?? []} pending={approvals.isPending} /></div>
      </>}
    </div>
  );
}

function Kpis({ data }: { data: AnalyticsSnapshot }) {
  const active = data.lead_status.filter((item) => ["new", "contacted", "qualified"].includes(item.status)).reduce((sum, item) => sum + item.count, 0);
  return <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="CRM metrics"><Kpi href="/crm?tab=companies" label="Companies" value={data.companies_total} /><Kpi href="/crm?tab=leads" label="Active leads" value={active} detail={`${data.leads_total} total`} /><Kpi href="/crm?tab=inquiries" label="Open inquiries" value={data.open_inquiries} /><Kpi href="/approvals" label="Pending approvals" value={data.approvals.pending} attention={data.approvals.pending > 0} /></section>;
}

function Kpi({ href, label, value, detail, attention }: { href: string; label: string; value: number; detail?: string; attention?: boolean }) {
  const slug = label.toLowerCase().replaceAll(" ", "-");
  return <Link data-testid={`overview-kpi-${slug}`} href={href} className="rounded-lg border border-border bg-card px-4 py-4 shadow-sm transition-colors hover:border-primary/50 hover:bg-accent/30"><div className="flex items-center justify-between gap-2"><span className="text-xs font-medium text-muted-foreground">{label}</span>{attention ? <span className="size-2 rounded-full bg-warning" aria-label="Needs attention" /> : null}</div><p data-testid={`overview-kpi-${slug}-value`} className="mt-3 text-2xl font-semibold tabular-nums text-foreground">{value}</p>{detail ? <p className="mt-1 text-[11px] text-subtle">{detail}</p> : null}</Link>;
}

function ActivitySection({ data, leads, companies }: { data: AnalyticsSnapshot; leads: Lead[]; companies: Company[] }) {
  return <section className="rounded-lg border border-border/80 bg-card" aria-labelledby="recent-activity-title"><div className="flex items-center justify-between border-b border-border/70 px-4 py-3"><h2 id="recent-activity-title" className="text-sm font-semibold text-foreground">Recent customer activity</h2><Link href="/crm?tab=leads" className="text-xs text-primary">View CRM</Link></div>{data.recent_interactions.length === 0 ? <p className="px-4 py-6 text-sm text-muted-foreground">No customer activity recorded yet.</p> : <ul className="divide-y divide-border/60">{data.recent_interactions.map((item) => { const lead = leads.find((entry) => entry.id === item.lead_id); const company = lead ? companies.find((entry) => entry.id === lead.company_id) : undefined; return <li key={item.id} className="px-4 py-3"><Link href={`/crm?tab=leads&id=${item.lead_id}`} className="block rounded-md hover:bg-accent/30"><div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm font-medium text-foreground">{company?.name ?? "Customer activity"}</span><time className="text-[11px] text-subtle">{new Date(item.created_at).toLocaleString()}</time></div><p className="mt-1 text-xs text-muted-foreground">{item.kind} · {lead?.title ?? "Related lead"}</p><p className="mt-1 truncate text-xs text-subtle">{item.summary}</p></Link></li>; })}</ul>}</section>;
}

function Pipeline({ data }: { data: AnalyticsSnapshot }) {
  const counts = STAGES.map(([status]) => data.lead_status.find((item) => item.status === status)?.count ?? 0);
  const max = Math.max(1, ...counts);
  return <section className="rounded-lg border border-border/80 bg-card px-4 py-3" aria-labelledby="pipeline-title"><div className="flex items-center justify-between"><h2 id="pipeline-title" className="text-sm font-semibold text-foreground">Lead pipeline</h2><Link href="/crm?tab=leads" className="text-xs text-primary">All leads</Link></div><p className="mt-1 text-xs text-muted-foreground">{data.leads_total} total · {counts.slice(0, 3).reduce((a, b) => a + b, 0)} active</p><ul className="mt-5 space-y-3">{STAGES.map(([status, label, color], index) => <li key={status}><Link href={`/crm?tab=leads&status=${status}`} className="block"><div className="flex justify-between text-xs"><span>{label}</span><span className="tabular-nums text-muted-foreground">{counts[index]}</span></div><div className="mt-1.5 h-1.5 rounded-full bg-secondary"><span className={`block h-full rounded-full ${color}`} style={{ width: `${(counts[index] / max) * 100}%` }} /></div></Link></li>)}</ul></section>;
}

function InquirySection({ inquiries, leads, companies, pending }: { inquiries: Inquiry[]; leads: Lead[]; companies: Company[]; pending: boolean }) {
  return <section className="rounded-lg border border-border/80 bg-card" aria-labelledby="inquiries-title"><div className="flex items-center justify-between border-b border-border/70 px-4 py-3"><h2 id="inquiries-title" className="text-sm font-semibold text-foreground">Open inquiries</h2><Link href="/crm?tab=inquiries" className="text-xs text-primary">View all</Link></div>{pending ? <Skeleton className="m-4 h-12" /> : inquiries.length === 0 ? <p className="px-4 py-6 text-sm text-muted-foreground">No open inquiries.</p> : <ul className="divide-y divide-border/60">{inquiries.slice(0, 5).map((item) => { const lead = leads.find((entry) => entry.id === item.lead_id); const company = companies.find((entry) => entry.id === item.company_id); return <li key={item.id} className="px-4 py-3"><Link href={`/crm?tab=inquiries&id=${item.id}`} className="flex items-center justify-between gap-3 rounded-md hover:bg-accent/30"><div className="min-w-0"><p className="truncate text-sm font-medium text-foreground">{item.subject}</p><p className="mt-1 truncate text-xs text-muted-foreground">{company?.name ?? "Company"}{lead ? ` · ${lead.title}` : ""}</p></div><span className="shrink-0 text-[11px] text-warning">Open</span></Link></li>; })}</ul>}</section>;
}

function Attention({ approvals, pending }: { approvals: Approval[]; pending: boolean }) {
  if (!pending && approvals.length === 0) return null;
  return <section className="rounded-lg border border-border bg-card shadow-sm" aria-labelledby="attention-title"><div className="flex items-center justify-between border-b border-border/70 px-4 py-3"><h2 id="attention-title" className="text-sm font-semibold text-foreground">Attention required</h2><Link href="/approvals" className="text-xs text-primary">Approvals</Link></div>{pending ? <Skeleton className="m-4 h-12" /> : <ul className="divide-y divide-border/60">{approvals.slice(0, 4).map((approval) => <li key={approval.id} className="px-4 py-3"><Link href={`/approvals?approval=${approval.id}`} className="block rounded-md hover:bg-accent/30"><p className="truncate text-sm text-foreground">Review approval</p><p className="mt-1 text-xs text-muted-foreground">Awaiting your decision</p></Link></li>)}</ul>}</section>;
}

function EmptyWorkspace() { return <section className="rounded-lg border border-dashed border-border bg-card px-5 py-8"><h2 className="text-lg font-semibold text-foreground">Your workspace is ready</h2><p className="mt-2 max-w-lg text-sm text-muted-foreground">Create your first company or lead to start tracking customer work here.</p><Link href="/crm?tab=companies" className="mt-4 inline-flex rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">Open CRM</Link></section>; }
function OverviewSkeleton() { return <div className="space-y-5"><Skeleton className="h-16 w-full" /><div className="grid gap-3 sm:grid-cols-4"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div><Skeleton className="h-64 w-full" /></div>; }
function storedScope(id: string): DataScope { if (typeof window === "undefined") return "all"; const saved = window.localStorage.getItem(`atlas.dashboard.scope.${id}`); return isDataScope(saved) ? saved : "all"; }
