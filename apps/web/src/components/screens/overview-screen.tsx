"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, BadgeCheck, BriefcaseBusiness, Building2, CheckCircle2, ChevronRight, Filter, ListFilter, MessageSquareText, MoreHorizontal, Plus, Search, X } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { RequestError } from "@/components/request-error";
import { Skeleton } from "@/components/ui/skeleton";
import type { Approval } from "@/lib/agent";
import { decideApproval, listApprovals } from "@/lib/agent-api";
import { sessionQueryOptions } from "@/lib/api";
import { getAnalytics, type AnalyticsSnapshot } from "@/lib/intelligence";
import { createOpportunity, listPipelineStages } from "@/lib/opportunities";
import { actionLabel, proposalChange, proposalTarget } from "@/lib/approval-presentation";
import { listCompanies, listInquiries, listLeads } from "@/lib/records-api";
import type { Company, Inquiry, Lead } from "@/lib/records";
import { useWorkspace } from "@/lib/use-workspace";

function initials(name: string): string {
  const letters = name.trim().split(/\s+/).filter((part) => /[A-Za-z0-9]/.test(part[0] ?? "")).slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("");
  return letters || "•";
}

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
  const [period, setPeriod] = useState("30d");
  const analytics = useQuery({ queryKey: ["analytics", organizationId, "all", period], queryFn: () => getAnalytics(organizationId ?? "", "all", { period }), enabled: Boolean(organizationId) });
  const companies = useQuery({ queryKey: ["overview-companies", organizationId], queryFn: () => listCompanies(organizationId ?? "", { pageSize: 100 }), enabled: Boolean(organizationId) });
  const leads = useQuery({ queryKey: ["overview-leads", organizationId], queryFn: () => listLeads(organizationId ?? "", { pageSize: 100 }), enabled: Boolean(organizationId) });
  const inquiries = useQuery({ queryKey: ["overview-inquiries", organizationId], queryFn: () => listInquiries(organizationId ?? "", { pageSize: 100 }), enabled: Boolean(organizationId) });
  const approvals = useQuery({ queryKey: ["overview-approvals", organizationId], queryFn: () => listApprovals(organizationId ?? "", { status: "pending" }), enabled: Boolean(organizationId) });
  const [search, setSearch] = useState("");
  const [filterOpen, setFilterOpen] = useState(false);
  const [pipelineStage, setPipelineStage] = useState("All stages");
  const [selectedActivity, setSelectedActivity] = useState<ActivityRow | null>(null);
  const [reviewing, setReviewing] = useState<Approval | null>(null);

  if (analytics.isPending) return <OverviewSkeleton />;
  if (analytics.isError) return <RequestError error={analytics.error} />;
  if (!analytics.data) return null;
  const empty = analytics.data.companies_total === 0 && analytics.data.leads_total === 0 && analytics.data.inquiries_total === 0;
  const firstName = session.data?.user.full_name.split(" ")[0] ?? "";
  const active = analytics.data.lead_status.filter((item) => ["new", "contacted", "qualified"].includes(item.status)).reduce((sum, item) => sum + item.count, 0);

  return (
    <div data-testid="overview-workspace">
      <div className="page-heading" data-testid="overview-intro">
        <div>
          <div className="eyebrow"><span className="live-dot" />Live workspace</div>
          <h1>{timeGreeting()}{firstName ? `, ${firstName}` : ""}</h1>
          <p>Here’s what needs your attention across {workspace.organizationName ?? "your workspace"}.</p>
        </div>
        <div className="page-actions">
          <button type="button" className="button button-secondary button-md" onClick={() => setFilterOpen(true)}><Filter size={15} /> Filters</button>
          {organizationId ? <NewOpportunity key={organizationId} organizationId={organizationId} companies={companies.data?.items ?? []} /> : null}
        </div>
      </div>
      {empty ? <EmptyWorkspace /> : <>
        <section className="metric-grid" aria-label="Workspace metrics" data-testid="overview-kpi-band">
          <Metric href="/crm?tab=companies" testId="overview-kpi-companies" label="Companies" value={analytics.data.companies_total} meta="Total accounts" icon={Building2} />
          <Metric href="/crm?tab=leads" testId="overview-kpi-active-leads" label="Active leads" value={active} meta={`${analytics.data.leads_total} total leads`} icon={BriefcaseBusiness} />
          <Metric href="/crm?tab=inquiries" testId="overview-kpi-customer-requests" label="Open inquiries" value={analytics.data.open_inquiries} meta="Awaiting response" icon={MessageSquareText} />
          <Metric href="/approvals" testId="overview-kpi-pending-approvals" label="Pending approvals" value={analytics.data.approvals.pending} meta="Needs review" icon={BadgeCheck} />
        </section>
        <div className="overview-grid" data-testid="overview-top-content">
          <Pipeline data={analytics.data} stage={pipelineStage} onStage={setPipelineStage} />
          <Attention approvals={approvals.data?.items ?? []} pending={approvals.isPending} error={approvals.error} onReview={setReviewing} />
        </div>
        <ActivitySection data={analytics.data} leads={leads.data?.items ?? []} companies={companies.data?.items ?? []} search={search} onSearch={setSearch} onFilter={() => setFilterOpen(true)} onOpen={setSelectedActivity} />
        <InquirySection inquiries={(inquiries.data?.items ?? []).filter((item) => !item.archived_at)} leads={leads.data?.items ?? []} companies={companies.data?.items ?? []} pending={inquiries.isPending} />
      </>}
      {filterOpen ? (
        <>
          <button type="button" className="drawer-backdrop" aria-label="Close filters" onClick={() => setFilterOpen(false)} />
          <aside className="drawer" aria-label="Advanced filters">
            <div className="drawer-header"><div><h2>Advanced filters</h2><p>Refine the overview data.</p></div><button type="button" className="button button-ghost button-icon" aria-label="Close filters" onClick={() => setFilterOpen(false)}><X size={17} /></button></div>
            <div className="drawer-content">
              <label className="field"><span>Pipeline stage</span>
                <select value={pipelineStage} onChange={(event) => setPipelineStage(event.target.value)}>
                  <option>All stages</option>
                  {STAGES.map(([, label]) => <option key={label}>{label}</option>)}
                </select>
              </label>
              <label className="field"><span>Activity period</span>
                <select value={period} onChange={(event) => setPeriod(event.target.value)}>
                  <option value="7d">Last 7 days</option>
                  <option value="30d">Last 30 days</option>
                  <option value="90d">Last 90 days</option>
                </select>
              </label>
            </div>
            <div className="drawer-footer">
              <button type="button" className="button button-ghost button-md" onClick={() => { setPipelineStage("All stages"); setPeriod("30d"); }}>Reset</button>
              <button type="button" className="button button-primary button-md" onClick={() => setFilterOpen(false)}>Apply filters</button>
            </div>
          </aside>
        </>
      ) : null}
      {selectedActivity ? (
        <>
          <button type="button" className="drawer-backdrop" aria-label="Close activity" onClick={() => setSelectedActivity(null)} />
          <aside className="drawer" aria-label="Activity details">
            <div className="drawer-header">
              <div className="drawer-title-with-avatar"><span className="avatar avatar-blue">{initials(selectedActivity.name)}</span><div><h2>{selectedActivity.name}</h2><p>Customer activity</p></div></div>
              <button type="button" className="button button-ghost button-icon" aria-label="Close activity" onClick={() => setSelectedActivity(null)}><X size={17} /></button>
            </div>
            <div className="drawer-content">
              <div className="detail-status"><span className="badge badge-blue">Recent activity</span><span>{relativeTime(selectedActivity.item.created_at)}</span></div>
              <h3 className="detail-title">{selectedActivity.lead?.title ?? selectedActivity.item.kind.replaceAll("_", " ")}</h3>
              <p className="detail-copy">{selectedActivity.item.summary}</p>
            </div>
            <div className="drawer-footer">
              <button type="button" className="button button-secondary button-md" onClick={() => setSelectedActivity(null)}>Close</button>
              <Link href={`/crm?tab=leads&id=${selectedActivity.item.lead_id}`} className="button button-primary button-md">Open customer <ArrowRight size={14} /></Link>
            </div>
          </aside>
        </>
      ) : null}
      {reviewing && organizationId ? (
        <ReviewApproval organizationId={organizationId} approval={reviewing} onClose={() => setReviewing(null)} />
      ) : null}
    </div>
  );
}

function Metric({ href, testId, label, value, meta, icon: Icon }: {
  href: string; testId: string; label: string; value: number; meta: string; icon: typeof Building2;
}) {
  return (
    <Link data-testid={testId} href={href} className="metric-card">
      <span className="metric-icon"><Icon size={16} /></span>
      <span className="metric-copy">
        <span className="metric-label">{label}</span>
        <strong data-testid={`${testId}-value`}>{value}</strong>
        <span className="metric-meta">{meta}</span>
      </span>
      <ChevronRight className="metric-arrow" size={16} />
    </Link>
  );
}

type ActivityRow = { item: AnalyticsSnapshot["recent_interactions"][number]; lead: Lead | undefined; name: string };

function Pipeline({ data, stage, onStage }: { data: AnalyticsSnapshot; stage: string; onStage: (stage: string) => void }) {
  const counts = STAGES.map(([status]) => data.lead_status.find((item) => item.status === status)?.count ?? 0);
  const largest = Math.max(1, ...counts);
  return (
    <section className="panel pipeline-panel" aria-labelledby="pipeline-title" data-testid="overview-pipeline">
      <div className="panel-header">
        <div>
          <h2 id="pipeline-title">Lead pipeline</h2>
          <p>{data.leads_total} leads across five stages</p>
        </div>
        <Link href="/crm?tab=leads" className="text-button">View pipeline <ArrowRight size={14} /></Link>
      </div>
      {data.leads_total ? (
        <div className="pipeline-list">
          {STAGES.map(([status, label, tone], index) => (
            <button type="button" key={status} className={`pipeline-row${stage === label ? " pipeline-row-active" : ""}`} onClick={() => onStage(label)}>
              <span className={`status-dot dot-${tone}`} />
              <span className="pipeline-label">{label}</span>
              <div className="bar-track"><span className={`bar-fill fill-${tone}`} style={{ width: `${(counts[index] / largest) * 100}%` }} /></div>
              <strong>{counts[index]}</strong>
              <ChevronRight size={14} />
            </button>
          ))}
        </div>
      ) : <div className="empty-state"><strong>No leads yet</strong><p>New leads will appear across these stages.</p></div>}
    </section>
  );
}

function Attention({ approvals, pending, error, onReview }: { approvals: Approval[]; pending: boolean; error: Error | null; onReview: (approval: Approval) => void }) {
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
          {approvals.slice(0, 4).map((approval) => (
            <article className="approval-item" key={approval.id}>
              <div className="approval-icon"><AlertCircle size={16} /></div>
              <div>
                <h3>{actionLabel(approval.action_type)}</h3>
                <p>{proposalTarget(approval.payload)}</p>
                <div className="approval-actions">
                  <button type="button" className="button button-primary button-sm" onClick={() => onReview(approval)}>Review and approve</button>
                  <button type="button" className="button button-secondary button-sm" onClick={() => onReview(approval)}>View details</button>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : <div className="empty-state"><CheckCircle2 size={22} /><strong>All caught up</strong><p>There are no approvals waiting for review.</p></div>}
    </section>
  );
}

function ActivitySection({ data, leads, companies, search, onSearch, onFilter, onOpen }: {
  data: AnalyticsSnapshot; leads: Lead[]; companies: Company[]; search: string; onSearch: (value: string) => void;
  onFilter: () => void; onOpen: (row: ActivityRow) => void;
}) {
  const rows = useMemo(() => data.recent_interactions.map((item) => {
    const lead = leads.find((entry) => entry.id === item.lead_id);
    const company = lead ? companies.find((entry) => entry.id === lead.company_id) : undefined;
    return { item, lead, company, name: company?.name ?? "Customer" };
  }).filter((row) => `${row.name} ${row.lead?.title ?? ""} ${row.item.summary}`.toLowerCase().includes(search.trim().toLowerCase())), [data.recent_interactions, leads, companies, search]);
  return (
    <section className="panel activity-panel" aria-labelledby="recent-activity-title" data-testid="overview-customer-activity">
      <div className="panel-header activity-header">
        <div>
          <h2 id="recent-activity-title">Recent customer activity</h2>
          <p>Latest updates across your accounts</p>
        </div>
        <div className="table-tools">
          <label className="small-search">
            <Search size={14} />
            <input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Search activity" aria-label="Search activity" />
            {search ? <button type="button" aria-label="Clear search" onClick={() => onSearch("")}><X size={13} /></button> : null}
          </label>
          <button type="button" className="button button-secondary button-sm" onClick={onFilter}><ListFilter size={14} /> Filter</button>
        </div>
      </div>
      <div className="activity-table" role="table" aria-label="Recent customer activity">
        <div className="activity-row table-head" role="row"><span>Company</span><span>Activity</span><span>Time</span><span /></div>
        {rows.length === 0 ? (
          <div className="empty-state table-empty"><Search size={22} /><strong>No activity found</strong><p>{search ? "Try changing your search." : "Customer updates will appear here."}</p>{search ? <button type="button" className="button button-secondary button-sm" onClick={() => onSearch("")}>Clear search</button> : null}</div>
        ) : rows.map((row) => (
          <button type="button" className="activity-row" role="row" key={row.item.id} onClick={() => onOpen(row)}>
            <span className="company-cell"><span className="avatar avatar-blue avatar-sm">{initials(row.name)}</span><strong>{row.name}</strong></span>
            <span className="activity-copy"><strong>{row.lead?.title ?? row.item.kind.replaceAll("_", " ")}</strong><small>{row.item.summary}</small></span>
            <span className="time-cell">{relativeTime(row.item.created_at)}</span>
            <MoreHorizontal size={17} />
          </button>
        ))}
      </div>
    </section>
  );
}

function InquirySection({ inquiries, leads, companies, pending }: { inquiries: Inquiry[]; leads: Lead[]; companies: Company[]; pending: boolean }) {
  return (
    <section className="panel" aria-labelledby="inquiries-title" data-testid="overview-bottom-content" style={{ marginTop: 16 }}>
      <div className="panel-header">
        <div><h2 id="inquiries-title">Open inquiries</h2><p>Requests waiting on a reply</p></div>
        <Link href="/crm?tab=inquiries" className="text-button">View all <ArrowRight size={14} /></Link>
      </div>
      {pending ? <Skeleton className="m-4 h-12" /> : inquiries.length === 0 ? <div className="empty-state"><strong>No open inquiries</strong><p>New customer requests will show up here.</p></div> : (
        <div className="activity-table">
          {inquiries.slice(0, 6).map((item) => {
            const lead = leads.find((entry) => entry.id === item.lead_id);
            const company = companies.find((entry) => entry.id === item.company_id);
            const name = company?.name ?? "Company";
            return (
              <Link key={item.id} href={`/crm?tab=inquiries&id=${item.id}`} className="activity-row">
                <span className="company-cell"><span className="avatar avatar-blue avatar-sm">{initials(name)}</span><strong>{name}</strong></span>
                <span className="activity-copy"><strong>{item.subject}</strong><small>{lead?.title ?? "Inquiry"}</small></span>
                <span className="time-cell">{relativeTime(item.created_at)}</span>
                <ChevronRight size={16} />
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}

function ReviewApproval({ organizationId, approval, onClose }: { organizationId: string; approval: Approval; onClose: () => void }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: () => decideApproval(organizationId, approval.id, "approve", ""),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["overview-approvals", organizationId] });
      await client.invalidateQueries({ queryKey: ["nav-approvals-count", organizationId] });
      onClose();
    },
  });
  return (
    <div className="overlay" role="presentation" onMouseDown={() => { if (!save.isPending) onClose(); }}>
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="review-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-header">
          <div>
            <h2 id="review-title">{actionLabel(approval.action_type)}</h2>
            <p>Review the request details before confirming approval.</p>
          </div>
          <button type="button" className="button button-ghost button-icon" aria-label="Close dialog" onClick={onClose}><X size={17} /></button>
        </div>
        <div className="approval-review">
          <div className="review-callout"><AlertCircle size={17} /><span><strong>Review required</strong><p>Confirm the stored request before it can run.</p></span></div>
          <p className="detail-copy">{proposalChange(approval.action_type, approval.payload)}</p>
          {save.error ? <RequestError error={save.error} /> : null}
        </div>
        <div className="dialog-footer">
          <button type="button" className="button button-secondary button-md" onClick={onClose}>Cancel</button>
          <button type="button" className="button button-primary button-md" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Confirming…" : "Confirm approval"}</button>
        </div>
      </section>
    </div>
  );
}

function NewOpportunity({ organizationId, companies }: { organizationId: string; companies: Company[] }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [created, setCreated] = useState(false);
  const stages = useQuery({ queryKey: ["pipeline-stages", organizationId], queryFn: () => listPipelineStages(organizationId), enabled: open });
  const firstStage = stages.data?.[0]?.key;
  const save = useMutation({
    mutationFn: (stage: string) => createOpportunity(organizationId, { title: title.trim(), stage, ...(company ? { company_id: company } : {}) }),
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
      <button type="button" className="button button-primary button-md" onClick={() => { save.reset(); setOpen(true); }}>
        <Plus size={16} aria-hidden="true" /> New opportunity
      </button>
      {created ? <p role="status" className="text-xs text-success">Opportunity created. <Link href="/crm?tab=opportunities" className="underline">Open pipeline</Link></p> : null}
      {open ? (
        <div className="overlay" role="presentation" onMouseDown={() => { if (!save.isPending) setOpen(false); }}>
          <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="opportunity-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="dialog-header">
              <div>
                <h2 id="opportunity-title">New opportunity</h2>
                <p>Add an opportunity to your CRM pipeline.</p>
              </div>
              <button type="button" className="button button-ghost button-icon" aria-label="Close dialog" onClick={() => setOpen(false)}><X size={17} /></button>
            </div>
            <form onSubmit={(event) => { event.preventDefault(); if (firstStage && title.trim()) save.mutate(firstStage); }}>
              <div className="dialog-body">
                <label className="field"><span>Opportunity name</span><input autoFocus required maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Enterprise expansion" /></label>
                <label className="field"><span>Company</span>
                  <select value={company} onChange={(event) => setCompany(event.target.value)}>
                    <option value="">No company selected</option>
                    {companies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </label>
                {stages.error ? <RequestError error={stages.error} /> : null}
                {save.error ? <RequestError error={save.error} /> : null}
              </div>
              <div className="dialog-footer">
                <button type="button" className="button button-secondary button-md" onClick={() => setOpen(false)}>Cancel</button>
                <button type="submit" className="button button-primary button-md" disabled={!firstStage || !title.trim() || save.isPending}>{save.isPending ? "Creating…" : "Create opportunity"}</button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </>
  );
}

function EmptyWorkspace() { return <section className="panel"><div className="empty-state"><strong>Your workspace is ready</strong><p>Create your first company or lead to start tracking customer work here.</p><Link href="/crm?tab=companies" className="button button-primary button-md">Open CRM</Link></div></section>; }
function OverviewSkeleton() { return <div className="space-y-5"><Skeleton className="h-16 w-full" /><div className="metric-grid"><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div><Skeleton className="h-64 w-full" /></div>; }
function timeGreeting(): string { const hour = new Date().getHours(); return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"; }
function relativeTime(value: string): string {
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return value;
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}
