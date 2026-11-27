import { ApiError, apiFetch, apiStream } from "@/data/client";
import { workspace } from "@/presentation/appConfig";

export function orgPath(path: string): string {
  return `/api/v1/organizations/${workspace.organizationId}${path}`;
}

export function failureMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "The request failed.";
}

type Page<T> = { items: T[]; total: number };

async function page<T>(path: string): Promise<T[]> {
  const result = await apiFetch<Page<T>>(orgPath(path));
  return result.items;
}

export function relativeTime(value: string): string {
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days}d ago`;
  return new Date(value).toLocaleDateString();
}

function label(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export type CrmRecord = {
  id: string;
  name: string;
  detail: string;
  status: string;
  owner: string;
  updated: string;
  company?: string;
  contact?: string;
  stage?: string;
  archived?: boolean;
  leadId?: string;
};

export type CrmSection =
  | "Companies"
  | "Contacts"
  | "Leads"
  | "Customer inquiries"
  | "Opportunities"
  | "Tasks"
  | "Customer interactions";

type Company = { id: string; name: string; industry: string | null; website: string | null; archived_at: string | null; updated_at: string };
type Contact = { id: string; full_name: string; email: string | null; title: string | null; company_id: string | null; archived_at: string | null; updated_at: string };
type Lead = { id: string; title: string; status: string; source: string | null; company_id: string | null; contact_id: string | null; owner_user_id: string; archived_at: string | null; updated_at: string };
type Inquiry = { id: string; subject: string; body: string; company_id: string | null; archived_at: string | null; created_at: string };
type Opportunity = { id: string; title: string; stage: string; company_id: string | null; archived_at?: string | null; owner_user_id: string };
type Task = { id: string; title: string; description: string | null; status: string; lead_id: string | null; assignee_user_id: string | null; updated_at: string };
type Interaction = { id: string; lead_id: string; kind: string; body: string; created_at: string };
type Member = { user_id: string; full_name: string; email: string; role: "admin" | "staff"; is_active: boolean; membership_id: string };

export async function loadCrm(): Promise<Record<CrmSection, CrmRecord[]>> {
  const [companies, contacts, leads, inquiries, opportunities, tasks, members] = await Promise.all([
    page<Company>("/companies?page=1&page_size=100&include_archived=true"),
    page<Contact>("/contacts?page=1&page_size=100&include_archived=true"),
    page<Lead>("/leads?page=1&page_size=100&include_archived=true"),
    page<Inquiry>("/inquiries?page=1&page_size=100&include_archived=true"),
    apiFetch<Opportunity[]>(orgPath("/opportunities?include_archived=true")),
    apiFetch<Task[]>(orgPath("/workflow-tasks")),
    apiFetch<Member[]>(orgPath("/members")),
  ]);
  const companyName = new Map(companies.map((item) => [item.id, item.name]));
  const contactName = new Map(contacts.map((item) => [item.id, item.full_name]));
  const ownerName = new Map(members.map((item) => [item.user_id, item.full_name]));
  const interactions = (await Promise.all(leads.slice(0, 40).map(async (lead) => {
    try {
      return await apiFetch<Interaction[]>(orgPath(`/leads/${lead.id}/interactions`));
    } catch {
      return [];
    }
  }))).flat();

  return {
    Companies: companies.map((item) => ({
      id: item.id,
      name: item.name,
      detail: [item.industry, item.website].filter(Boolean).join(" · ") || "Company",
      status: item.archived_at ? "Archived" : "Active",
      owner: "Unassigned",
      updated: relativeTime(item.updated_at),
      archived: Boolean(item.archived_at),
    })),
    Contacts: contacts.map((item) => ({
      id: item.id,
      name: item.full_name,
      detail: [item.title, item.email].filter(Boolean).join(" · ") || "Contact",
      status: item.title || "Contact",
      owner: "Unassigned",
      updated: relativeTime(item.updated_at),
      company: item.company_id ? companyName.get(item.company_id) : undefined,
      archived: Boolean(item.archived_at),
    })),
    Leads: leads.map((item) => ({
      id: item.id,
      name: item.title,
      detail: item.source || "Lead",
      status: label(item.status),
      owner: ownerName.get(item.owner_user_id) || "Unassigned",
      updated: relativeTime(item.updated_at),
      company: item.company_id ? companyName.get(item.company_id) : undefined,
      contact: item.contact_id ? contactName.get(item.contact_id) : undefined,
      archived: Boolean(item.archived_at),
    })),
    "Customer inquiries": inquiries.map((item) => ({
      id: item.id,
      name: item.subject,
      detail: item.body,
      status: item.archived_at ? "Archived" : "Open",
      owner: "Unassigned",
      updated: relativeTime(item.created_at),
      company: item.company_id ? companyName.get(item.company_id) : undefined,
      archived: Boolean(item.archived_at),
    })),
    Opportunities: opportunities.map((item) => ({
      id: item.id,
      name: item.title,
      detail: item.company_id ? companyName.get(item.company_id) || "Opportunity" : "Opportunity",
      status: label(item.stage),
      stage: label(item.stage),
      owner: ownerName.get(item.owner_user_id) || "Unassigned",
      updated: "",
      company: item.company_id ? companyName.get(item.company_id) : undefined,
      archived: Boolean(item.archived_at),
    })),
    Tasks: tasks.map((item) => ({
      id: item.id,
      name: item.title,
      detail: item.description || "Task",
      status: label(item.status),
      owner: item.assignee_user_id ? ownerName.get(item.assignee_user_id) || "Unassigned" : "Unassigned",
      updated: relativeTime(item.updated_at),
      company: item.lead_id ? leads.find((lead) => lead.id === item.lead_id)?.title : undefined,
      leadId: item.lead_id || undefined,
    })),
    "Customer interactions": interactions.map((item) => ({
      id: item.id,
      name: label(item.kind),
      detail: item.body,
      status: label(item.kind),
      owner: "Recorded",
      updated: relativeTime(item.created_at),
      company: leads.find((lead) => lead.id === item.lead_id)?.title,
      leadId: item.lead_id,
    })),
  };
}

export async function saveCrm(section: CrmSection, record: { id?: string; name: string; company?: string; status: string }, companies: CrmRecord[], leads: CrmRecord[]): Promise<void> {
  const companyId = companies.find((item) => item.name === record.company)?.id ?? null;
  const status = record.status.toLowerCase().replaceAll(" ", "_");
  if (section === "Companies") {
    const body = { name: record.name };
    await apiFetch(orgPath(record.id ? `/companies/${record.id}` : "/companies"), { method: record.id ? "PATCH" : "POST", body: JSON.stringify(body) });
    return;
  }
  if (section === "Contacts") {
    const body = { full_name: record.name, company_id: companyId };
    await apiFetch(orgPath(record.id ? `/contacts/${record.id}` : "/contacts"), { method: record.id ? "PATCH" : "POST", body: JSON.stringify(body) });
    return;
  }
  if (section === "Leads") {
    const body = { title: record.name, status, company_id: companyId };
    await apiFetch(orgPath(record.id ? `/leads/${record.id}` : "/leads"), { method: record.id ? "PATCH" : "POST", body: JSON.stringify(body) });
    return;
  }
  if (section === "Customer inquiries") {
    const body = { subject: record.name, body: record.company || "Recorded from the workspace.", company_id: companyId };
    await apiFetch(orgPath(record.id ? `/inquiries/${record.id}` : "/inquiries"), { method: record.id ? "PATCH" : "POST", body: JSON.stringify(body) });
    return;
  }
  if (section === "Opportunities") {
    const body = { title: record.name, stage: status, company_id: companyId };
    await apiFetch(orgPath(record.id ? `/opportunities/${record.id}` : "/opportunities"), { method: record.id ? "PATCH" : "POST", body: JSON.stringify(body) });
    return;
  }
  if (section === "Tasks") {
    if (record.id) {
      await apiFetch(orgPath(`/workflow-tasks/${record.id}`), { method: "PATCH", body: JSON.stringify({ status }) });
      return;
    }
    const lead = leads.find((item) => item.name === record.company);
    await apiFetch(orgPath("/workflow-tasks"), { method: "POST", body: JSON.stringify({ title: record.name, lead_id: lead?.id }) });
    return;
  }
  const lead = leads.find((item) => item.name === record.company) || leads[0];
  if (!lead) throw new ApiError(400, "lead_required", "Add a lead before recording an interaction.");
  await apiFetch(orgPath(`/leads/${lead.id}/interactions`), { method: "POST", body: JSON.stringify({ kind: status === "call" || status === "email" ? status : "note", body: record.name }) });
}

export async function archiveCrm(section: CrmSection, id: string): Promise<void> {
  const path = section === "Companies" ? `/companies/${id}` : section === "Contacts" ? `/contacts/${id}` : section === "Leads" ? `/leads/${id}` : section === "Customer inquiries" ? `/inquiries/${id}` : section === "Opportunities" ? `/opportunities/${id}` : "";
  if (!path) throw new ApiError(400, "not_archivable", "This record type cannot be archived.");
  await apiFetch(orgPath(path), { method: "DELETE" });
}

export async function restoreCrm(section: CrmSection, id: string): Promise<void> {
  const path = section === "Companies" ? `/companies/${id}/restore` : section === "Contacts" ? `/contacts/${id}/restore` : section === "Leads" ? `/leads/${id}/restore` : section === "Customer inquiries" ? `/inquiries/${id}/restore` : section === "Opportunities" ? `/opportunities/${id}/restore` : "";
  if (!path) throw new ApiError(400, "not_restorable", "This record type cannot be restored.");
  await apiFetch(orgPath(path), { method: "POST" });
}

export type InboxItem = {
  id: string;
  customer: string;
  initials: string;
  company: string;
  subject: string;
  preview: string;
  time: string;
  channel: "Website chat" | "Email" | "WhatsApp";
  status: "Open" | "Pending" | "Resolved";
  assignee: string;
  unread: boolean;
  email?: string | null;
  messages: { id: string; author: string; body: string; time: string; direction: "in" | "out"; state?: "sent" | "delivered" | "failed" | "pending" }[];
};

function channelLabel(value: string): InboxItem["channel"] {
  if (value === "email") return "Email";
  if (value === "whatsapp") return "WhatsApp";
  return "Website chat";
}

function statusLabel(value: string): InboxItem["status"] {
  if (value === "resolved" || value === "closed") return "Resolved";
  if (value === "pending" || value === "waiting") return "Pending";
  return "Open";
}

export async function loadInbox(): Promise<InboxItem[]> {
  const rows = await apiFetch<{ id: string; subject: string; channel: string; status: string; unread_count: number; assignee_name?: string | null; updated_at: string; customer_name?: string | null; company_name?: string | null; preview?: string | null }[]>(orgPath("/inbox"));
  return rows.map((row) => ({
    id: row.id,
    customer: row.customer_name || "Unknown customer",
    initials: (row.customer_name || "?").split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase(),
    company: row.company_name || "No company",
    subject: row.subject,
    preview: row.preview || row.subject,
    time: relativeTime(row.updated_at),
    channel: channelLabel(row.channel),
    status: statusLabel(row.status),
    assignee: row.assignee_name || "Unassigned",
    unread: row.unread_count > 0,
    messages: [],
  }));
}

export async function loadInboxThread(id: string): Promise<Pick<InboxItem, "messages" | "email" | "customer" | "company">> {
  const detail = await apiFetch<{ customer_name?: string | null; company_name?: string | null; customer?: { email?: string | null; name?: string | null; company_name?: string | null } | null; messages: { id: string; sender: string; body: string; direction: string; delivery_status: string; created_at: string }[] }>(orgPath(`/inbox/${id}`));
  return {
    customer: detail.customer?.name || detail.customer_name || "Unknown customer",
    company: detail.customer?.company_name || detail.company_name || "No company",
    email: detail.customer?.email ?? null,
    messages: detail.messages.map((message) => ({
      id: message.id,
      author: message.sender,
      body: message.body,
      time: relativeTime(message.created_at),
      direction: message.direction === "outbound" || message.direction === "out" ? "out" : "in",
      state: message.delivery_status === "failed" ? "failed" : message.delivery_status === "delivered" ? "delivered" : "sent",
    })),
  };
}

export function submitInboxReply(id: string, recipient: string, subject: string, body: string) {
  return apiFetch<{ approval_id: string; status: string }>(orgPath(`/inbox/${id}/submit-for-approval`), { method: "POST", body: JSON.stringify({ recipient, subject, body }) });
}

export function draftInbox(id: string) {
  return apiFetch<{ subject: string; body: string }>(orgPath(`/inbox/${id}/draft-with-ai`), { method: "POST", body: JSON.stringify({}) });
}

export function inboxAssignees() {
  return apiFetch<{ user_id: string; full_name: string }[]>(orgPath("/inbox/assignees"));
}

export function assignInbox(id: string, userId: string | null) {
  return apiFetch(orgPath(`/inbox/${id}/assignment`), { method: "PATCH", body: JSON.stringify({ user_id: userId }) });
}

export function updateInboxStatus(id: string, status: string) {
  return apiFetch(orgPath(`/inbox/${id}/status?status=${encodeURIComponent(status)}`), { method: "PATCH" });
}

export function archiveInbox(id: string) {
  return apiFetch(orgPath(`/inbox/${id}/archive`), { method: "POST" });
}

export function restoreInbox(id: string) {
  return apiFetch(orgPath(`/inbox/${id}/restore`), { method: "POST" });
}

export function takeOverInbox(id: string) {
  return apiFetch(orgPath(`/inbox/${id}/takeover`), { method: "POST" });
}

export function getWidget() {
  return apiFetch<{ welcome_message: string; operating_mode: string; allowed_domains: string[]; enabled: boolean } | null>(orgPath("/inbox/widget"));
}

export function saveWidget(body: { welcome_message: string; operating_mode: string; allowed_domains: string[] }) {
  return apiFetch(orgPath("/inbox/widget"), { method: "PUT", body: JSON.stringify(body) });
}

export type AssistantSource = {
  kind: "document" | "crm";
  title: string;
  excerpt: string;
  document_id?: string | null;
  chunk_id?: string | null;
  page_number?: number | null;
  record_type?: string | null;
  record_id?: string | null;
};

export type AssistantProposal = {
  id: string;
  kind: "follow_up" | "appointment" | "task";
  status: "proposed" | "submitted" | "dismissed";
  title: string;
  summary: string;
  result_label: string;
  lead_id?: string | null;
  contact_id?: string | null;
  inquiry_id?: string | null;
  approval_id?: string | null;
  approval_status?: string | null;
  task_id?: string | null;
  run_id?: string | null;
};

export type AssistantStep = {
  tool_name: string;
  status: "succeeded" | "failed" | "recovered";
  duration_ms: number;
  detail: string;
};

export type AssistantMessage = {
  id: string;
  role: "user" | "assistant";
  body: string;
  sources: AssistantSource[];
  proposals: AssistantProposal[];
  steps: AssistantStep[];
};

export type AssistantThread = {
  id: string;
  title: string;
  updatedAt: string;
  messages: AssistantMessage[];
};

export type AssistantReply = {
  conversation_id: string;
  message: AssistantMessage;
  document_search: "ready" | "empty" | "unconfigured" | "unavailable" | "skipped";
};

type MessageRow = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: AssistantSource[];
  proposals?: AssistantProposal[];
  steps?: AssistantStep[];
};

function mapMessage(row: MessageRow): AssistantMessage {
  return {
    id: row.id,
    role: row.role,
    body: row.content,
    sources: row.sources ?? [],
    proposals: row.proposals ?? [],
    steps: row.steps ?? [],
  };
}

export type AssistantConversationRow = {
  id: string;
  title: string;
  updated_at: string;
  archived_at?: string | null;
};

export function listAssistantConversations(query = "", retention: "active" | "archived" = "active") {
  const params = new URLSearchParams({ retention });
  const trimmed = query.trim();
  if (trimmed) params.set("q", trimmed);
  return apiFetch<AssistantConversationRow[]>(orgPath(`/conversations?${params.toString()}`));
}

export function createAssistantConversation() {
  return apiFetch<AssistantConversationRow>(orgPath("/conversations"), { method: "POST", body: JSON.stringify({}) });
}

export function renameAssistantConversation(id: string, title: string) {
  return apiFetch<AssistantConversationRow>(orgPath(`/conversations/${id}`), {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export function archiveAssistantConversation(id: string) {
  return apiFetch<AssistantConversationRow>(orgPath(`/conversations/${id}/archive`), { method: "POST" });
}

export function restoreAssistantConversation(id: string) {
  return apiFetch<AssistantConversationRow>(orgPath(`/conversations/${id}/restore`), { method: "POST" });
}

export function getAssistantConversation(id: string) {
  return apiFetch<{ id: string; title: string; updated_at: string; messages: MessageRow[] }>(orgPath(`/conversations/${id}`)).then((detail) => ({
    id: detail.id,
    title: detail.title,
    updatedAt: detail.updated_at,
    messages: detail.messages.map(mapMessage),
  }));
}

type ReplyRow = {
  conversation_id: string;
  document_search: AssistantReply["document_search"];
  message: MessageRow;
};

export function streamAssistantMessage(
  id: string,
  content: string,
  onToken: (text: string) => void,
  onPhase: (phase: string) => void,
  signal?: AbortSignal,
) {
  return apiStream<ReplyRow>(orgPath(`/conversations/${id}/messages/stream`), { content }, onToken, onPhase, signal).then((reply) => ({
    conversation_id: reply.conversation_id,
    document_search: reply.document_search,
    message: mapMessage(reply.message),
  }));
}

export function submitProposal(conversationId: string, proposalId: string, times?: { starts_at: string; ends_at: string }) {
  return apiFetch<AssistantProposal>(orgPath(`/conversations/${conversationId}/proposals/${proposalId}/submit`), {
    method: "POST",
    body: JSON.stringify(times ?? {}),
  });
}

export function dismissProposal(conversationId: string, proposalId: string) {
  return apiFetch<AssistantProposal>(orgPath(`/conversations/${conversationId}/proposals/${proposalId}/dismiss`), { method: "POST" });
}

export type KnowledgeDoc = { id: string; title: string; filename: string; status: string; byte_size: number; error_message: string | null; updated_at: string; media_type: string; archived_at?: string | null };

export function listKnowledge(includeArchived = false) {
  return page<KnowledgeDoc>(`/documents?page=1&page_size=100&include_archived=${includeArchived ? "true" : "false"}`);
}

export function uploadKnowledge(file: File) {
  const body = new FormData();
  body.append("file", file);
  body.append("origin", "operational");
  return apiFetch<KnowledgeDoc>(orgPath("/documents"), { method: "POST", body });
}

export function retryKnowledge(id: string) {
  return apiFetch(orgPath(`/documents/${id}/job/retry`), { method: "POST" });
}

export function archiveKnowledge(id: string) {
  return apiFetch(orgPath(`/documents/${id}/archive`), { method: "POST" });
}

export function restoreKnowledge(id: string) {
  return apiFetch(orgPath(`/documents/${id}/restore`), { method: "POST" });
}

export function previewKnowledge(id: string) {
  return apiFetch<{ excerpt: string; filename: string }>(orgPath(`/documents/${id}/preview`));
}

export function chunksKnowledge(id: string) {
  return apiFetch<{ items: { content: string; page_number: number | null; chunk_index: number }[] }>(orgPath(`/documents/${id}/chunks`));
}

export function searchKnowledge(q: string) {
  return apiFetch<{ items: { document_id: string; document_title: string; page_number: number | null; content: string; score: number }[] }>(orgPath(`/documents/search?q=${encodeURIComponent(q)}`));
}

export type ApprovalRow = { id: string; status: string; action_type: string; payload: Record<string, unknown>; created_at: string; decision_note: string | null; execution_error: string | null; requested_by: string };

export function listApprovalRows() {
  return apiFetch<{ items: ApprovalRow[] }>(orgPath("/approvals?page=1")).then((pageResult) => pageResult.items);
}

export function decideApprovalRow(id: string, decision: "approve" | "reject", note: string) {
  return apiFetch(orgPath(`/approvals/${id}/${decision}`), { method: "POST", body: JSON.stringify({ note: note.trim() || null }) });
}

export function executeApprovalRow(id: string) {
  return apiFetch(orgPath(`/approvals/${id}/execute`), { method: "POST" });
}

export type WorkflowAction = { type: string; title?: string; note?: string; status?: string; priority?: string };
export type WorkflowGraph = {
  trigger: string;
  actions: WorkflowAction[];
  conditions?: { field: string; operator: string; value: string }[];
  interval_seconds?: number;
};
export type WorkflowRow = {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  active: boolean;
  version: number;
  definition: WorkflowGraph;
  updated_at: string;
  archived_at: string | null;
  last_run_at: string | null;
};

export function workflowDefinition(name: string, trigger: string, intervalSeconds = 86400): WorkflowGraph {
  const mapped = trigger === "Schedule" ? "schedule" : trigger === "Status changed" ? "lead_status_changed" : trigger === "Record created" ? "lead_created" : "manual";
  const definition: WorkflowGraph = {
    trigger: mapped,
    actions: [
      { type: "require_approval", note: name.slice(0, 500) },
      { type: "create_task", title: name.slice(0, 200), priority: "normal" },
    ],
  };
  if (mapped === "schedule") definition.interval_seconds = intervalSeconds;
  if (mapped === "lead_status_changed") {
    definition.conditions = [{ field: "lead_status", operator: "equals", value: "qualified" }];
  }
  return definition;
}

function workflowSlug(name: string): string {
  const base = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
  return `${base.length >= 3 ? base : "workflow"}-${crypto.randomUUID().slice(0, 8)}`;
}

export function createWorkflowRow(name: string, trigger: string, intervalSeconds = 86400) {
  return apiFetch<WorkflowRow>(orgPath("/workflow-definitions"), {
    method: "POST",
    body: JSON.stringify({ name, slug: workflowSlug(name), description: name, definition: workflowDefinition(name, trigger, intervalSeconds) }),
  });
}

export function updateWorkflowRow(row: Pick<WorkflowRow, "id" | "slug" | "version">, name: string, trigger: string, intervalSeconds = 86400) {
  return apiFetch<WorkflowRow>(orgPath(`/workflow-definitions/${row.id}`), {
    method: "PATCH",
    body: JSON.stringify({
      name,
      slug: row.slug,
      description: name,
      definition: workflowDefinition(name, trigger, intervalSeconds),
      expected_version: row.version,
    }),
  });
}

export function listWorkflows() {
  return apiFetch<WorkflowRow[]>(orgPath("/workflow-definitions"));
}

export function workflowCommand(id: string, action: "activate" | "pause" | "duplicate") {
  return apiFetch(orgPath(`/workflow-definitions/${id}/${action}`), { method: "POST" });
}

export function startWorkflow(id: string, dryRun: boolean) {
  return apiFetch(orgPath(`/workflow-definitions/${id}/runs`), { method: "POST", body: JSON.stringify({ request_id: crypto.randomUUID(), dry_run: dryRun }) });
}

export type WorkflowRunDetail = {
  id: string;
  status: string;
  error: string | null;
  created_at: string;
  dry_run?: boolean;
  steps?: { type: string; status: string }[];
};

export function listWorkflowRunRows(id: string) {
  return apiFetch<WorkflowRunDetail[]>(orgPath(`/workflow-definitions/${id}/runs`));
}

export type RunRow = { id: string; inquiry_subject: string; status: string; started_at: string; finished_at: string | null; error_message: string | null };

export function listRuns() {
  return apiFetch<{ items: RunRow[] }>(orgPath("/agent-runs?page=1&scope=all")).then((pageResult) => pageResult.items);
}

export function resumeRun(id: string) {
  return apiFetch(orgPath(`/agent-runs/${id}/resume`), { method: "POST" });
}

export function getRun(id: string) {
  return apiFetch<{ run: RunRow; events: { step: string; status: string; error_message: string | null; created_at: string }[]; approvals: { id: string; status: string; action_type: string }[] }>(orgPath(`/agent-runs/${id}`));
}

export type AnalyticsSnapshot = {
  companies_total: number;
  leads_total: number;
  open_inquiries: number;
  inquiries_total: number;
  lead_status: { status: string; count: number }[];
  recent_interactions: { id: string; summary: string; created_at: string; kind: string }[];
  customer_activity?: { day: string; inquiries: number; interactions: number }[];
  sales?: { opportunities_total: number; by_stage: { stage: string; count: number }[] };
};

export function loadAnalytics(period: string, channel: string, ownerId = "") {
  const query = new URLSearchParams({ scope: "all", period });
  if (channel && channel !== "all") query.set("channel", channel);
  if (ownerId) query.set("owner_user_id", ownerId);
  return apiFetch<AnalyticsSnapshot>(orgPath(`/analytics?${query.toString()}`));
}

export async function exportAnalytics(period: string, channel: string, report: string, ownerId = ""): Promise<void> {
  const query = new URLSearchParams({ scope: "all", period, report });
  if (channel && channel !== "all") query.set("channel", channel);
  if (ownerId) query.set("owner_user_id", ownerId);
  const response = await fetch(orgPath(`/analytics/export?${query.toString()}`), { credentials: "include", cache: "no-store" });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { error?: { message?: string } } | null;
    throw new ApiError(response.status, "export_failed", payload?.error?.message ?? "The report was not exported.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${report}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

export type CampaignRow = { id: string; name: string; status: string; subject: string | null; body: string | null; updated_at: string; delivery_mode: string; segment_id: string | null; scheduled_at?: string | null };

export function listCampaignRows() {
  return apiFetch<CampaignRow[]>(orgPath("/campaigns"));
}

export function createCampaignRow(body: { name: string; subject: string; body: string; segment_id: string | null }) {
  return apiFetch<CampaignRow>(orgPath("/campaigns"), { method: "POST", body: JSON.stringify({ ...body, channel: "email" }) });
}

export function updateCampaignRow(id: string, body: { name: string; subject: string | null; body: string | null; segment_id: string | null }) {
  return apiFetch<CampaignRow>(orgPath(`/campaigns/${id}`), { method: "PATCH", body: JSON.stringify(body) });
}

export function previewCampaignRow(id: string) {
  return apiFetch<{ eligible: number; suppressed: number; missing_consent: number; matching_contacts: number }>(orgPath(`/campaigns/${id}/recipients/preview`), { method: "POST" });
}

export function campaignTransport() {
  return apiFetch<{ mode: string; ready: boolean; detail: string | null }>(orgPath("/campaign-transport"));
}

export function scheduleCampaignSandbox(id: string) {
  return apiFetch(orgPath(`/campaigns/${id}/schedule`), { method: "POST", body: JSON.stringify({ scheduled_at: null, delivery_mode: "sandbox" }) });
}

export function cancelCampaignRow(id: string) {
  return apiFetch<CampaignRow>(orgPath(`/campaigns/${id}/cancel`), { method: "POST" });
}

export type SegmentRow = { id: string; name: string; preview?: { contacts: number; leads: number } };

export function listSegments() {
  return apiFetch<SegmentRow[]>(orgPath("/segments"));
}

export function listCampaignDeliveries(id: string) {
  return apiFetch<{ id: string; email: string; status: string }[]>(orgPath(`/campaigns/${id}/deliveries?offset=0`));
}

export type IntegrationRow = {
  integration_type: string;
  provider: string;
  status: string;
  verified_at: string | null;
  verification_detail: string | null;
  has_credentials: boolean;
  credential_version: number;
  config?: Record<string, unknown>;
};

export function listIntegrationRows() {
  return apiFetch<IntegrationRow[]>(orgPath("/integration-configs"));
}

export function verifyIntegrationRow(type: string) {
  return apiFetch<{ verified: boolean; detail: string }>(orgPath(`/integration-configs/${type}/verify`), { method: "POST" });
}

export function saveIntegrationRow(
  type: string,
  body: { provider: string; config: Record<string, unknown>; credentials?: string; expected_version?: number },
) {
  const payload: Record<string, unknown> = { provider: body.provider, config: body.config };
  if (body.credentials) payload.credentials = body.credentials;
  if (body.expected_version) payload.expected_version = body.expected_version;
  return apiFetch<IntegrationRow>(orgPath(`/integration-configs/${type}`), { method: "PUT", body: JSON.stringify(payload) });
}

export function setIntegrationEnabled(type: string, enabled: boolean, version: number) {
  return apiFetch<IntegrationRow>(orgPath(`/integration-configs/${type}/${enabled ? "enable" : "disable"}`), {
    method: "POST",
    body: JSON.stringify({ expected_version: version }),
  });
}

export type WebhookKeyStatus = { id: string; created_at: string; rotated_at: string | null; revoked_at: string | null; last_accepted_at: string | null } | null;

export function webhookKeyStatus() {
  return apiFetch<WebhookKeyStatus>(orgPath("/integrations/webhook-keys"));
}

export function issueWebhookKey(rotate: boolean) {
  return apiFetch<{ id: string; secret: string }>(orgPath(`/integrations/webhook-keys${rotate ? "/rotate" : ""}`), { method: "POST" });
}

export function revokeWebhookKey() {
  return apiFetch<void>(orgPath("/integrations/webhook-keys/revoke"), { method: "POST" });
}

export type BillingSnapshot = { mode: "sandbox" | "stripe"; checkout_available: boolean; portal_available: boolean; subscription: { plan_code: string; status: string; provider: string }; usage: Record<string, number>; plan: Record<string, number | string> };

export function loadBilling() {
  return apiFetch<BillingSnapshot>(orgPath("/billing"));
}

export function loadBillingPlans() {
  return apiFetch<{ code: string; name: string }[]>(orgPath("/billing/plans"));
}

export function checkoutBilling(planCode: string) {
  return apiFetch<{ mode: string; checkout_url?: string; status: string }>(orgPath("/billing/checkout"), {
    method: "POST",
    body: JSON.stringify({ plan_code: planCode, billing_interval: "month" }),
  });
}

export function openBillingPortal() {
  return apiFetch<{ portal_url: string }>(orgPath("/billing/portal"), { method: "POST" });
}

export function loadDiagnostics() {
  return apiFetch<{
    failed_runs: { id: string; error_code: string | null; hint: string | null }[];
    integration_failures: { id: string; status: string; error: string | null; hint: string | null }[];
    workers: { id: string; kind: string; status: string; last_error_code: string | null; processed_count: number }[];
    activity?: { knowledge: { ready: number; indexing: number; failed: number }; workflows: { running: number; failed: number; needs_attention: number }; assistant: { status: string; recent_errors: number; last_error_code: string | null }; integrations: { type: string; provider: string; status: string; health?: string }[] };
  }>(orgPath("/diagnostics?scope=all"));
}

export function loadTeam() {
  return apiFetch<Member[]>(orgPath("/members"));
}

export function loadInvitations() {
  return apiFetch<{ id: string; email: string; role: string; accepted_at: string | null }[]>(orgPath("/invitations"));
}

export function inviteMember(email: string) {
  return apiFetch<{ id: string; email: string; token: string }>(orgPath("/invitations"), { method: "POST", body: JSON.stringify({ email }) });
}

export function createFollowUp(title: string, description: string) {
  return apiFetch<{ id: string; title: string; status: string }>(orgPath("/workflow-tasks"), {
    method: "POST",
    body: JSON.stringify({ title, description }),
  });
}

export type SearchHit = { id: string; label: string; kind: "Companies" | "Contacts" | "Leads" };

export async function searchRecords(query: string): Promise<SearchHit[]> {
  const q = encodeURIComponent(query);
  const [companies, contacts, leads] = await Promise.all([
    apiFetch<Page<{ id: string; name: string }>>(orgPath(`/companies?q=${q}&page=1&page_size=5`)),
    apiFetch<Page<{ id: string; full_name: string }>>(orgPath(`/contacts?q=${q}&page=1&page_size=5`)),
    apiFetch<Page<{ id: string; title: string }>>(orgPath(`/leads?q=${q}&page=1&page_size=5`)),
  ]);
  return [
    ...companies.items.map((item) => ({ id: item.id, label: item.name, kind: "Companies" as const })),
    ...contacts.items.map((item) => ({ id: item.id, label: item.full_name, kind: "Contacts" as const })),
    ...leads.items.map((item) => ({ id: item.id, label: item.title, kind: "Leads" as const })),
  ];
}

export type LeadPredictionResult = {
  id: string;
  label: string;
  probability: number;
  confidence: number | null;
  synthetic: boolean;
  model_version: string;
  notice: string;
  explanation: string;
};

export function getLeadPrediction(id: string) {
  return apiFetch<LeadPredictionResult>(orgPath(`/leads/${id}/predictions`));
}

export function createLeadPrediction(id: string) {
  return apiFetch<LeadPredictionResult>(orgPath(`/leads/${id}/predictions`), { method: "POST" });
}

export function changeMemberRole(membershipId: string, role: "admin" | "staff") {
  return apiFetch(orgPath(`/members/${membershipId}`), { method: "PATCH", body: JSON.stringify({ role }) });
}

export function removeTeamMember(membershipId: string) {
  return apiFetch(orgPath(`/members/${membershipId}`), { method: "DELETE" });
}

export function renameOrganization(name: string) {
  return apiFetch(orgPath(""), { method: "PATCH", body: JSON.stringify({ name }) });
}

export function loadOnboarding() {
  return apiFetch<{ setup: { business_description: string | null; industry: string | null; timezone: string; completed: boolean }; organization: { name: string } }>(orgPath("/onboarding"));
}

export function saveOnboarding(body: { business_description?: string; industry?: string; timezone?: string; completed?: boolean }) {
  return apiFetch(orgPath("/onboarding"), { method: "PATCH", body: JSON.stringify(body) });
}
