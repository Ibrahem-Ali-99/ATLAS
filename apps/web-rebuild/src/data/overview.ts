import { apiFetch } from "@/data/client";
import type { Tone } from "@/presentation/components";

type StatusCount = { status: string; count: number };
type Analytics = {
  companies_total: number;
  leads_total: number;
  open_inquiries: number;
  lead_status: StatusCount[];
  approvals: { pending: number };
  recent_interactions: { id: string; lead_id: string; kind: string; summary: string; created_at: string }[];
};
type Page<T> = { items: T[]; total: number };
type Company = { id: string; name: string };
type Lead = { id: string; company_id: string | null; title: string };
type Conversation = { unread_count: number };
type Approval = { id: string; action_type: string; payload: Record<string, unknown> };

export type ActivityItem = {
  id: string;
  company: string;
  initials: string;
  text: string;
  detail: string;
  time: string;
  tone: Tone;
};

export type ApprovalItem = {
  id: string;
  title: string;
  detail: string;
  request: string;
};

export type PipelineRow = { label: string; value: number; tone: Tone; width: string };

export type OverviewSnapshot = {
  companies: number;
  activeLeads: number;
  leadsTotal: number;
  openInquiries: number;
  pendingApprovals: number;
  pipeline: PipelineRow[];
  approvals: ApprovalItem[];
  activities: ActivityItem[];
  companyNames: string[];
};

export type NavCounts = { inbox?: number; approvals?: number; runs?: number };

const stages = [
  ["new", "New", "blue"],
  ["contacted", "Contacted", "purple"],
  ["qualified", "Qualified", "amber"],
  ["won", "Won", "green"],
  ["lost", "Lost", "red"],
] as const;

const tones: Tone[] = ["blue", "purple", "amber", "green"];

function org(id: string, path: string): string {
  return `/api/v1/organizations/${id}${path}`;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function initials(name: string): string {
  const letters = name
    .trim()
    .split(/\s+/)
    .filter((part) => /[A-Za-z0-9]/.test(part[0] ?? ""))
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "");
  return letters.join("") || "•";
}

function relativeTime(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return hours === 1 ? "1 hr ago" : `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

function approvalTitle(action: string): string {
  if (action === "create_lead") return "Create lead";
  if (action === "update_lead") return "Update lead";
  if (action === "prepare_customer_response") return "Prepare customer response";
  if (action === "request_appointment") return "Request appointment";
  return action.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function approvalDetail(payload: Record<string, unknown>): string {
  const company = text(payload.company_name) ?? text(payload.company);
  const contact = text(payload.contact_name) ?? text(payload.contact);
  const title = text(payload.title);
  if (contact && company) return `${contact} · ${company}`;
  if (title && company) return `${title} · ${company}`;
  if (company) return company;
  if (title) return title;
  if (contact) return contact;
  const status = text(payload.status);
  return status ? status.replaceAll("_", " ") : "Stored request";
}

function approvalRequest(action: string, payload: Record<string, unknown>): string {
  const status = text(payload.status);
  const notes = text(payload.notes);
  if (action === "update_lead" && status) {
    return `Set lead status to ${status.replaceAll("_", " ")}${notes ? ` and update its notes to “${notes}”` : ""}.`;
  }
  if (action === "create_lead") return `Create a new lead${status ? ` with status ${status.replaceAll("_", " ")}` : ""}.`;
  if (action === "prepare_customer_response") return "Prepare the proposed customer response for review.";
  if (action === "request_appointment") return "Prepare the proposed appointment for review.";
  return "Apply the stored proposal.";
}

export async function loadOverview(organizationId: string, period: string): Promise<OverviewSnapshot> {
  const query = new URLSearchParams({ scope: "all", period });
  const [analytics, companies, leads, approvals] = await Promise.all([
    apiFetch<Analytics>(org(organizationId, `/analytics?${query.toString()}`)),
    apiFetch<Page<Company>>(org(organizationId, "/companies?page=1&page_size=100")),
    apiFetch<Page<Lead>>(org(organizationId, "/leads?page=1&page_size=100")),
    apiFetch<Page<Approval>>(org(organizationId, "/approvals?page=1&status=pending")),
  ]);
  const companyName = new Map(companies.items.map((company) => [company.id, company.name]));
  const leadById = new Map(leads.items.map((lead) => [lead.id, lead]));
  const counts = stages.map(([status]) => analytics.lead_status.find((item) => item.status === status)?.count ?? 0);
  const largest = Math.max(1, ...counts);
  const activeLeads = analytics.lead_status
    .filter((item) => item.status === "new" || item.status === "contacted" || item.status === "qualified")
    .reduce((sum, item) => sum + item.count, 0);
  return {
    companies: analytics.companies_total,
    activeLeads,
    leadsTotal: analytics.leads_total,
    openInquiries: analytics.open_inquiries,
    pendingApprovals: analytics.approvals.pending,
    pipeline: stages.map(([, label, tone], index) => ({
      label,
      value: counts[index] ?? 0,
      tone,
      width: `${((counts[index] ?? 0) / largest) * 100}%`,
    })),
    approvals: approvals.items.map((approval) => ({
      id: approval.id,
      title: approvalTitle(approval.action_type),
      detail: approvalDetail(approval.payload),
      request: approvalRequest(approval.action_type, approval.payload),
    })),
    activities: analytics.recent_interactions.map((item, index) => {
      const lead = leadById.get(item.lead_id);
      const company = (lead?.company_id ? companyName.get(lead.company_id) : undefined) ?? "Customer";
      return {
        id: item.id,
        company,
        initials: initials(company),
        text: lead?.title ?? item.kind.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase()),
        detail: item.summary,
        time: relativeTime(item.created_at),
        tone: tones[index % tones.length] ?? "blue",
      };
    }),
    companyNames: companies.items.map((company) => company.name),
  };
}

export async function loadNavCounts(organizationId: string): Promise<NavCounts> {
  const [inbox, approvals, runs] = await Promise.allSettled([
    apiFetch<Conversation[]>(org(organizationId, "/inbox")),
    apiFetch<Page<unknown>>(org(organizationId, "/approvals?page=1&status=pending")),
    apiFetch<Page<unknown>>(org(organizationId, "/agent-runs?page=1&scope=all&status=running")),
  ]);
  return {
    inbox: inbox.status === "fulfilled" ? inbox.value.reduce((sum, item) => sum + item.unread_count, 0) : undefined,
    approvals: approvals.status === "fulfilled" ? approvals.value.total : undefined,
    runs: runs.status === "fulfilled" ? runs.value.total : undefined,
  };
}

export function createOpportunity(organizationId: string, title: string, companyId: string, stage: string): Promise<{ id: string }> {
  return apiFetch(org(organizationId, "/opportunities"), {
    method: "POST",
    body: JSON.stringify({ title, company_id: companyId, stage, currency: "USD" }),
  });
}

export function decideApproval(organizationId: string, approvalId: string): Promise<unknown> {
  return apiFetch(org(organizationId, `/approvals/${approvalId}/approve`), {
    method: "POST",
    body: JSON.stringify({ note: null }),
  });
}

export async function companyIdByName(organizationId: string, name: string): Promise<string | null> {
  const page = await apiFetch<Page<Company>>(org(organizationId, "/companies?page=1&page_size=100"));
  const match = page.items.find((company) => company.name.toLowerCase() === name.trim().toLowerCase());
  return match?.id ?? null;
}
