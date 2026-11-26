import { apiFetch } from "@/lib/api";
export const recordInboxInquiry = (id: string, conversationId: string, title: string) =>
  apiFetch<{ lead_id: string; inquiry_id: string }>(`${path(id)}/${conversationId}/crm-intake`, {
    method: "POST", body: JSON.stringify({ title }),
  });
export type InboxConversation = {
  id: string;
  subject: string;
  channel: "email" | "whatsapp" | "webchat";
  status: string;
  unread_count: number;
  contact_id: string | null;
  lead_id: string | null;
  assigned_to: string | null;
  handoff_requested?: boolean;
  handoff_reason?: string | null;
  updated_at: string;
  customer_name?: string | null;
  company_name?: string | null;
  preview?: string | null;
};
export type InboxDetail = InboxConversation & { ai_resumed?: boolean; reply_recipient?: string | null; reply_unavailable?: string | null; handoff_accepted_at?: string | null; handoff_resolved_at?: string | null; messages: { id: string; sender: string; recipient: string; body: string; direction: string; channel: string; delivery_status: string; created_at: string }[] };
const path = (id: string) => `/api/v1/organizations/${id}/inbox`;
export type WidgetSettings = {
  allowed_domains: string[];
  welcome_message: string;
  operating_mode: "human_review" | "ai_assist" | "ai_auto_reply";
  enabled?: boolean;
};
export type InboxWidget = WidgetSettings & { public_id: string; enabled: boolean };
export const getInboxWidget = (id: string) => apiFetch<InboxWidget | null>(`${path(id)}/widget`);
export const saveInboxWidget = (id: string, settings: WidgetSettings) =>
  apiFetch<InboxWidget>(`${path(id)}/widget`, { method: "PUT", body: JSON.stringify(settings) });
export type InboxAssignee = { user_id: string; full_name: string; email: string };
export const listInbox = (id: string, q = "", assigned = "all", channel = "all", status = "") => apiFetch<InboxConversation[]>(`${path(id)}?${new URLSearchParams({ ...(q ? { q } : {}), ...(assigned !== "all" ? { assigned } : {}), ...(channel !== "all" ? { channel } : {}), ...(status ? { status } : {}) })}`);
export const getInbox = (id: string, conversationId: string) => apiFetch<InboxDetail>(`${path(id)}/${conversationId}`);
export const markInboxRead = (id: string, conversationId: string, updatedAt: string) =>
  apiFetch<{ marked: boolean }>(`${path(id)}/${conversationId}/read`, {
    method: "PATCH",
    body: JSON.stringify({ updated_at: updatedAt }),
  });
export const saveInboxDraft = (id: string, conversationId: string, recipient: string, body: string, subject: string) => apiFetch<{ id: string; delivery_status: string }>(`${path(id)}/${conversationId}/draft`, { method: "POST", body: JSON.stringify({ recipient, body, subject }) });
export const updateInboxStatus = (id: string, conversationId: string, status: string) => apiFetch<{ status: string }>(`${path(id)}/${conversationId}/status?status=${status}`, { method: "PATCH" });
export const draftInboxWithAi = (id: string, conversationId: string) => apiFetch<{ subject: string; body: string }>(`${path(id)}/${conversationId}/draft-with-ai`, { method: "POST", body: JSON.stringify({}) });
export const submitInboxApproval = (id: string, conversationId: string, recipient: string, body: string, subject: string, templateName?: string, templateLanguage = "en_US") => apiFetch<{ approval_id: string; status: string }>(`${path(id)}/${conversationId}/submit-for-approval`, { method: "POST", body: JSON.stringify({ recipient, body, subject, ...(templateName ? { template_name: templateName, template_language: templateLanguage } : {}) }) });
export const listInboxAssignees = (id: string) => apiFetch<InboxAssignee[]>(`${path(id)}/assignees`);
export const assignInbox = (id: string, conversationId: string, userId: string | null) => apiFetch<{ assigned_to: string | null }>(`${path(id)}/${conversationId}/assignment`, { method: "PATCH", body: JSON.stringify({ user_id: userId }) });
export const linkInboxContact = (id: string, conversationId: string, contactId: string) => apiFetch<{ contact_id: string }>(`${path(id)}/${conversationId}/contact`, { method: "PATCH", body: JSON.stringify({ contact_id: contactId }) });
export const createInboxContact = (id: string, conversationId: string, fullName: string, address: { email: string } | { phone: string }) => apiFetch<{ contact_id: string }>(`${path(id)}/${conversationId}/contact`, { method: "POST", body: JSON.stringify({ full_name: fullName, ...address }) });
export const takeOverInbox = (id: string, conversationId: string) => apiFetch(`${path(id)}/${conversationId}/takeover`, { method: "POST" });
export const resolveInboxHandoff = (id: string, conversationId: string) => apiFetch(`${path(id)}/${conversationId}/resolve`, { method: "POST" });
export const resumeInboxAi = (id: string, conversationId: string) => apiFetch(`${path(id)}/${conversationId}/resume-ai`, { method: "POST" });
export const sendStaffMessage = (id: string, conversationId: string, body: string, clientMessageId: string) => apiFetch(`${path(id)}/${conversationId}/staff-message`, { method: "POST", body: JSON.stringify({ body, client_message_id: clientMessageId }) });

export const linkInboxLead = (id: string, conversationId: string, leadId: string) => apiFetch<{ lead_id: string }>(`${path(id)}/${conversationId}/lead`, { method: "PATCH", body: JSON.stringify({ lead_id: leadId }) });
