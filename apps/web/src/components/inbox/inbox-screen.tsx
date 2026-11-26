"use client";

import { Fragment, useDeferredValue, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, ExternalLink, Inbox, Mail, MessageCircle, PanelRight, Search, Send, Settings2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { archiveInboxConversation, assignInbox, draftInboxWithAi, getInbox, linkInboxLead, listInbox, listInboxAssignees, markInboxUnread, resolveInboxHandoff, restoreInboxConversation, resumeInboxAi, saveInboxDraft, sendStaffMessage, submitInboxApproval, takeOverInbox, updateInboxStatus } from "@/lib/inbox";
import { useWorkspace } from "@/lib/use-workspace";
import { recordInboxInquiry } from "@/lib/inbox";
import { AppointmentDialog } from "@/components/calendar/appointment-dialog";
import { ConfirmButton } from "@/components/confirm-button";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { getContact, getLead, listContacts, listLeads } from "@/lib/records-api";
import { getInboxWidget, markInboxRead, saveInboxWidget, type InboxDetail, type InboxWidget, type WhatsAppServiceWindow, type WidgetSettings } from "@/lib/inbox";
import { resolveApiBaseUrl } from "@/lib/api-base";

const channelNames = { email: "Email", whatsapp: "WhatsApp", webchat: "Website chat" };
const fieldClass = "h-9 w-full min-w-0 rounded-md border border-input bg-background px-2.5 text-sm text-foreground";
const composerClass = "min-h-24 w-full rounded-md border border-input bg-background p-3 text-sm";
const recordClass = "flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-sm font-medium hover:bg-accent";

function displayDate(date: string) {
  return new Date(date).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function deliveryLabel(status: string) {
  const labels: Record<string, string> = {
    received: "Received",
    sent: "Sent",
    delivered: "Delivered",
    read: "Read",
    failed: "Failed",
  };
  return labels[status] ?? "Needs attention";
}

function serviceWindowCopy(window: WhatsAppServiceWindow) {
  const provider = window.provider === "live"
    ? "Live WhatsApp is available"
    : window.provider === "test"
      ? "Restricted test number"
      : "WhatsApp sending is unavailable";
  if (!window.closes_at) return `${provider}. No customer message has opened the 24-hour service window.`;
  const closes = displayDate(window.closes_at);
  return window.open
    ? `${provider}. Customer-service window is open until ${closes}.`
    : `${provider}. Customer-service window closed ${closes}.`;
}

function relativeTime(date: string) {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(date).getTime()) / 60000));
  if (minutes < 1) return "Now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.round(hours / 24);
  return `${days}d`;
}

export function InboxScreen() {
  const { organizationId, role } = useWorkspace();
  return organizationId ? <InboxWorkspace key={organizationId} id={organizationId} isAdmin={role === "admin"} /> : null;
}

function InboxWorkspace({ id, isAdmin }: { id: string; isAdmin: boolean }) {
  const params = useSearchParams();
  const requested = params.get("conversation");
  const [selected, setSelected] = useState<string | null>(requested);
  useEffect(() => {
    if (requested) setSelected(requested);
  }, [requested]);
  const [q, setQ] = useState("");
  const deferredQuery = useDeferredValue(q);
  const [statusFilter, setStatusFilter] = useState("");
  const [leadSearch, setLeadSearch] = useState("");
  const deferredLeadSearch = useDeferredValue(leadSearch);
  const [assignmentFilter, setAssignmentFilter] = useState("all");
  const [channelFilter, setChannelFilter] = useState("all");
  const [retention, setRetention] = useState("active");
  const [draft, setDraft] = useState("");
  const [subject, setSubject] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [newContactName, setNewContactName] = useState("");
  const [newContactAddress, setNewContactAddress] = useState("");
  const [staffReply, setStaffReply] = useState("");
  const client = useQueryClient();
  const conversations = useQuery({ queryKey: ["inbox", id, deferredQuery, assignmentFilter, channelFilter, statusFilter, retention], queryFn: () => listInbox(id, deferredQuery, assignmentFilter, channelFilter, statusFilter, retention), enabled: Boolean(id), refetchInterval: 8000 });
  const detail = useQuery({ queryKey: ["inbox-detail", id, selected], queryFn: () => getInbox(id, selected ?? ""), enabled: Boolean(id && selected), refetchInterval: 5000 });
  const { mutate: acknowledge } = useMutation({
    mutationFn: ({ id: conversationId, updated_at }: InboxDetail) => markInboxRead(id, conversationId, updated_at),
    onSuccess: ({ marked }, conversation) => {
      if (!marked) return;
      client.setQueryData<InboxDetail>(["inbox-detail", id, conversation.id], (current) =>
        current?.updated_at === conversation.updated_at ? { ...current, unread_count: 0 } : current,
      );
      void client.invalidateQueries({ queryKey: ["inbox", id] });
    },
  });
  const seenThread = detail.data;
  useEffect(() => {
    if (seenThread?.unread_count) acknowledge(seenThread);
  }, [acknowledge, seenThread]);
  const assignees = useQuery({ queryKey: ["inbox-assignees", id], queryFn: () => listInboxAssignees(id), enabled: Boolean(id) });
  const contacts = useQuery({ queryKey: ["contacts", id], queryFn: () => listContacts(id, { page: 1, pageSize: 100 }), enabled: Boolean(id && selected && detail.data && !detail.data.contact_id) });
  const leads = useQuery({
    queryKey: ["inbox-leads", id, deferredLeadSearch],
    queryFn: () => listLeads(id, { q: deferredLeadSearch, pageSize: 50 }),
    enabled: Boolean(detail.data && detail.data.channel !== "webchat" && !detail.data.lead_id && deferredLeadSearch.trim()),
  });
  const linkLead = useMutation({ mutationFn: (leadId: string) => linkInboxLead(id, selected ?? "", leadId), onSuccess: () => invalidate() });
  const latestInbound = detail.data?.messages.findLast((message) => message.direction === "inbound");
  const savedDraft = detail.data?.messages.findLast((message) => message.delivery_status === "draft");
  const recipient = detail.data?.reply_recipient ?? latestInbound?.sender ?? "";
  const invalidate = () => { void client.invalidateQueries({ queryKey: ["inbox", id] }); void client.invalidateQueries({ queryKey: ["inbox-detail", id, selected] }); };
  const save = useMutation({ mutationFn: () => saveInboxDraft(id, selected ?? "", recipient, draft, subject), onSuccess: invalidate });
  const status = useMutation({ mutationFn: (value: string) => updateInboxStatus(id, selected ?? "", value), onSuccess: invalidate });
  const assignment = useMutation({ mutationFn: (userId: string | null) => assignInbox(id, selected ?? "", userId), onSuccess: invalidate });
  const aiDraft = useMutation({ mutationFn: () => draftInboxWithAi(id, selected ?? ""), onSuccess: (result) => { setSubject(result.subject); setDraft(result.body); } });
  const approval = useMutation({ mutationFn: () => submitInboxApproval(id, selected ?? "", recipient, draft, subject, templateName || undefined), onSuccess: invalidate });
  const linkContact = useMutation({ mutationFn: (contactId: string) => import("@/lib/inbox").then(({ linkInboxContact }) => linkInboxContact(id, selected ?? "", contactId)), onSuccess: invalidate });
  const createContact = useMutation({ mutationFn: () => import("@/lib/inbox").then(({ createInboxContact }) => createInboxContact(id, selected ?? "", newContactName, detail.data?.channel === "whatsapp" ? { phone: newContactAddress } : { email: newContactAddress })), onSuccess: () => { setNewContactName(""); setNewContactAddress(""); invalidate(); } });
  const takeover = useMutation({ mutationFn: () => takeOverInbox(id, selected ?? ""), onSuccess: invalidate });
  const resolve = useMutation({ mutationFn: () => resolveInboxHandoff(id, selected ?? ""), onSuccess: invalidate });
  const resumeAi = useMutation({ mutationFn: () => resumeInboxAi(id, selected ?? ""), onSuccess: invalidate });
  const staffSend = useMutation({ mutationFn: () => sendStaffMessage(id, selected ?? "", staffReply, `staff-${Date.now()}-${Math.random().toString(36).slice(2)}`), onSuccess: () => { setStaffReply(""); invalidate(); } });
  const markUnread = useMutation({ mutationFn: () => markInboxUnread(id, selected ?? ""), onSuccess: invalidate });
  const archive = useMutation({ mutationFn: () => archiveInboxConversation(id, selected ?? ""), onSuccess: invalidate });
  const restore = useMutation({ mutationFn: () => restoreInboxConversation(id, selected ?? ""), onSuccess: invalidate });
  const open = (conversation: { id: string; subject: string }) => {
    if (conversation.id === selected || aiDraft.isPending || staffSend.isPending) return;
    setSelected(conversation.id);
    setSubject(conversation.subject);
    setDraft("");
    setStaffReply("");
    setTemplateName("");
    setLeadSearch("");
    setNewContactName("");
    setNewContactAddress("");
    save.reset();
    aiDraft.reset();
    approval.reset();
  };
  const requestError = conversations.error ?? detail.error ?? assignment.error ?? status.error ??
    save.error ?? takeover.error ?? resolve.error ?? resumeAi.error ?? staffSend.error ??
    linkContact.error ?? createContact.error ?? linkLead.error ?? markUnread.error ?? archive.error ?? restore.error;
  const filtered = Boolean(q || assignmentFilter !== "all" || channelFilter !== "all" || statusFilter);
  const clearFilters = () => {
    setQ("");
    setAssignmentFilter("all");
    setChannelFilter("all");
    setStatusFilter("");
  };
  const thread = detail.data;
  const linkedContact = useQuery({
    queryKey: ["inbox-contact", id, thread?.contact_id],
    queryFn: () => getContact(id, thread!.contact_id!),
    enabled: Boolean(thread?.contact_id),
  });
  const linkedLead = useQuery({
    queryKey: ["inbox-lead", id, thread?.lead_id],
    queryFn: () => getLead(id, thread!.lead_id!),
    enabled: Boolean(thread?.lead_id),
  });
  const messages = thread?.messages.filter((message) => message.delivery_status !== "draft");
  const threadLog = useRef<HTMLDivElement>(null);
  const followMessages = useRef(true);
  const visibleThreadId = thread?.id;
  const lastMessageId = messages?.at(-1)?.id;
  useEffect(() => { followMessages.current = true; }, [visibleThreadId]);
  useEffect(() => {
    const log = threadLog.current;
    if (log && followMessages.current) log.scrollTop = log.scrollHeight;
  }, [visibleThreadId, lastMessageId]);
  const context = thread ? (
    <div className="space-y-5">
      <div className="grid gap-3">
        <h3 className="text-sm font-semibold">Assignment and status</h3>
        <label className="grid gap-1 text-xs text-muted-foreground">Conversation assignee
          <select className={fieldClass} value={thread.assigned_to ?? ""} disabled={!assignees.data || assignment.isPending} onChange={(event) => assignment.mutate(event.target.value || null)}>
            <option value="">Unassigned</option>
            {assignees.data?.map((person) => <option key={person.user_id} value={person.user_id}>{person.full_name}</option>)}
          </select>
        </label>
        {assignees.error ? <RequestError error={assignees.error} /> : null}
        <label className="grid gap-1 text-xs text-muted-foreground">Conversation status
          <select className={fieldClass} value={thread.status} disabled={status.isPending} onChange={(event) => status.mutate(event.target.value)}>
            <option value="open">Open</option>
            <option value="pending">Pending</option>
            <option value="resolved">Resolved</option>
          </select>
        </label>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" disabled={takeover.isPending} onClick={() => takeover.mutate()}>Accept handoff</Button>
          {thread.handoff_requested ? <Button size="sm" variant="secondary" disabled={resolve.isPending} onClick={() => resolve.mutate()}>Resolve handoff</Button> : null}
          {isAdmin && thread.channel === "webchat" && thread.status === "resolved" ? <Button size="sm" variant="secondary" disabled={resumeAi.isPending} onClick={() => resumeAi.mutate()}>Resume AI</Button> : null}
          <Button size="sm" variant="outline" disabled={thread.status === "pending" || status.isPending} onClick={() => status.mutate("pending")}>Mark for follow-up</Button>
        </div>
        {thread.archived_at ? (
          <div className="grid gap-2">
            <p className="text-xs text-muted-foreground">Archived {displayDate(thread.archived_at)}. Messages stay in this workspace.</p>
            <Button size="sm" variant="outline" disabled={restore.isPending} onClick={() => restore.mutate()}>{restore.isPending ? "Restoring…" : "Restore conversation"}</Button>
          </div>
        ) : (
          <div className="grid gap-2">
            <p className="text-xs text-muted-foreground">Archiving hides this conversation. Messages stay in the workspace, and a new customer message brings it back.</p>
            <ConfirmButton size="sm" label="Archive conversation" confirmLabel="Archive and keep messages" pendingLabel="Archiving…" pending={archive.isPending} onConfirm={() => archive.mutate()} />
          </div>
        )}
      </div>
      <div className="grid gap-3 border-t border-border pt-4">
        <h3 className="text-sm font-semibold">Customer</h3>
        <dl className="grid gap-1 text-sm">
          <div className="flex justify-between gap-3"><dt className="text-muted-foreground">Name</dt><dd className="truncate">{thread.customer?.name ?? thread.customer_name ?? "Not linked"}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-muted-foreground">Email</dt><dd className="truncate">{thread.customer?.email ?? "None"}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-muted-foreground">Phone</dt><dd className="truncate">{thread.customer?.phone ?? "None"}</dd></div>
        </dl>
        {thread.customer?.company_id ? (
          <Link className={recordClass} href={`/crm?tab=companies&id=${thread.customer.company_id}`}>
            {thread.customer.company_name ?? "Open company"} <ExternalLink size={13} />
          </Link>
        ) : null}
        {thread.lead_id ? <AppointmentDialog organizationId={id} leadId={thread.lead_id} /> : null}
      </div>
      <div className="grid gap-3 border-t border-border pt-4">
        <h3 className="text-sm font-semibold">Linked CRM records</h3>
        {linkedContact.error ? <RequestError error={linkedContact.error} /> : null}
        {thread.contact_id ? (
          <Link className={recordClass} href={`/crm?tab=contacts&id=${thread.contact_id}`}>
            {linkedContact.data?.full_name ?? "Open contact"} <ExternalLink size={13} />
          </Link>
        ) : (
          <>
            <label className="grid gap-1 text-xs text-muted-foreground">Existing contact
              <select className={fieldClass} value="" disabled={linkContact.isPending} onChange={(event) => { if (event.target.value) linkContact.mutate(event.target.value); }}>
                <option value="">Choose a contact</option>
                {contacts.data?.items.map((contact) => <option key={contact.id} value={contact.id}>{contact.full_name}</option>)}
              </select>
            </label>
            {contacts.error ? <RequestError error={contacts.error} /> : null}
            <form className="grid gap-2" onSubmit={(event) => { event.preventDefault(); createContact.mutate(); }}>
              <input aria-label="New contact name" className={fieldClass} placeholder="New contact name" value={newContactName} onChange={(event) => setNewContactName(event.target.value)} required />
              <input aria-label={thread.channel === "whatsapp" ? "New contact phone" : "New contact email"} className={fieldClass} type={thread.channel === "whatsapp" ? "tel" : "email"} placeholder={thread.channel === "whatsapp" ? "Phone with country code" : "Email"} value={newContactAddress} onChange={(event) => setNewContactAddress(event.target.value)} required />
              <Button size="sm" variant="secondary" type="submit" disabled={createContact.isPending}>Create contact</Button>
            </form>
          </>
        )}
        {linkedLead.error ? <RequestError error={linkedLead.error} /> : null}
        {thread.lead_id ? (
          <Link className={recordClass} href={`/crm?tab=leads&id=${thread.lead_id}`}>
            {linkedLead.data?.title ?? "Open lead"} <ExternalLink size={13} />
          </Link>
        ) : thread.channel !== "webchat" ? (
          <>
            <label className="grid gap-1 text-xs text-muted-foreground">Link a CRM lead
              <input className={fieldClass} value={leadSearch} onChange={(event) => setLeadSearch(event.target.value)} placeholder="Search lead titles" />
            </label>
            {leads.error ? <RequestError error={leads.error} /> : null}
            {leads.data ? (
              <select aria-label="Select a CRM lead" className={fieldClass} value="" disabled={linkLead.isPending} onChange={(event) => { if (event.target.value) linkLead.mutate(event.target.value); }}>
                <option value="">Choose a matching lead</option>
                {leads.data.items.filter((lead) => lead.contact_id && (!thread.contact_id || thread.contact_id === lead.contact_id)).map((lead) => <option key={lead.id} value={lead.id}>{lead.title}</option>)}
              </select>
            ) : null}
          </>
        ) : null}
        {thread.customer?.inquiry_id ? (
          <Link className={recordClass} href={`/crm?tab=inquiries&id=${thread.customer.inquiry_id}`}>
            {thread.customer.inquiry_subject ?? "Open inquiry"} <ExternalLink size={13} />
          </Link>
        ) : null}
        {thread.contact_id && latestInbound ? (
          <RecordInquiry key={thread.id} organizationId={id} conversationId={thread.id}
            title={thread.subject} linked={Boolean(thread.lead_id)} onRecorded={invalidate} />
        ) : null}
      </div>
    </div>
  ) : null;

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <PageHeader title="Inbox" eyebrow="Customer communications" actions={isAdmin ? (
        <WidgetSettingsDialog organizationId={id} />
      ) : undefined}>
        Manage customer conversations across connected channels.
      </PageHeader>
      {requestError ? <RequestError error={requestError} /> : null}
      <div className="grid min-w-0 overflow-hidden rounded-xl border border-border bg-card lg:max-[1439px]:grid-cols-[minmax(14rem,18rem)_minmax(0,1fr)] min-[1440px]:grid-cols-[minmax(14rem,18rem)_minmax(0,1fr)_minmax(16rem,20rem)]">
        <section aria-label="Conversation queue" className={`min-w-0 lg:border-r lg:border-border ${selected ? "hidden lg:block" : ""}`}>
          <div className="space-y-3 border-b border-border p-4">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">Conversations</h2>
              {conversations.data ? (
                <span className="flex gap-1">
                  <Badge variant="secondary">{conversations.data.reduce((total, item) => total + item.unread_count, 0)} unread</Badge>
                  <Badge variant="secondary">{conversations.data.filter((item) => item.status === "open").length} open</Badge>
                </span>
              ) : null}
            </div>
            <select aria-label="Conversation retention" className={fieldClass} value={retention} onChange={(event) => setRetention(event.target.value)}>
              <option value="active">Active conversations</option>
              <option value="archived">Archived conversations</option>
            </select>
            <label className="relative block">
              <Search aria-hidden="true" size={15} className="pointer-events-none absolute top-3 left-3 text-muted-foreground" />
              <input aria-label="Search inbox" className={`${fieldClass} pl-9`} placeholder="Search conversations" value={q} onChange={(event) => setQ(event.target.value)} />
            </label>
            <details className="text-sm" open={filtered || undefined}>
              <summary className="cursor-pointer font-medium">Filters</summary>
              <div className="mt-2 grid gap-2">
                <select aria-label="Assignment filter" className={fieldClass} value={assignmentFilter} onChange={(event) => setAssignmentFilter(event.target.value)}>
                  <option value="all">All assignees</option><option value="mine">Assigned to me</option><option value="assigned">Assigned</option><option value="unassigned">Unassigned</option>
                </select>
                <select aria-label="Channel filter" className={fieldClass} value={channelFilter} onChange={(event) => setChannelFilter(event.target.value)}>
                  <option value="all">All channels</option><option value="email">Email</option><option value="whatsapp">WhatsApp</option><option value="webchat">Website chat</option>
                </select>
                <select aria-label="Status filter" className={fieldClass} value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="">All statuses</option><option value="open">Open</option><option value="pending">Pending</option><option value="resolved">Resolved</option>
                </select>
                {filtered ? <Button size="sm" variant="ghost" onClick={clearFilters}>Clear filters</Button> : null}
              </div>
            </details>
          </div>
          {conversations.isPending ? <div className="p-4" role="status" aria-label="Loading conversations"><Skeleton className="h-12" /></div> : null}
          <ul className="max-h-[65dvh] divide-y divide-border overflow-y-auto">
            {conversations.data?.map((conversation) => {
              const ChannelIcon = conversation.channel === "email" ? Mail : MessageCircle;
              return (
                <li key={conversation.id}>
                  <button type="button" aria-current={selected === conversation.id || undefined}
                    className={`flex w-full min-w-0 items-start gap-3 px-4 py-3 text-left hover:bg-accent ${selected === conversation.id ? "bg-accent" : ""}`}
                    onClick={() => open(conversation)}>
                    <span className="mt-0.5 rounded-lg bg-primary/10 p-2 text-primary"><ChannelIcon aria-hidden="true" size={16} /></span>
                    <span className="grid min-w-0 flex-1 gap-1">
                      <span className="flex items-baseline justify-between gap-2">
                        <span className="truncate text-sm font-semibold">{conversation.customer_name ?? conversation.subject}</span>
                        <time className="shrink-0 text-xs text-muted-foreground" dateTime={conversation.updated_at} title={displayDate(conversation.updated_at)}>{relativeTime(conversation.updated_at)}</time>
                      </span>
                      {conversation.customer_name ? <span className="truncate text-sm">{conversation.subject}</span> : null}
                      {conversation.preview ? <span className="truncate text-xs text-muted-foreground">{conversation.preview}</span> : null}
                      <span className="text-xs text-muted-foreground">{conversation.company_name ? `${conversation.company_name} · ` : null}{channelNames[conversation.channel]} · <span className="capitalize">{conversation.status}</span>{conversation.assignee_name ? ` · ${conversation.assignee_name}` : ""}</span>
                      {conversation.handoff_requested ? <span className="text-xs font-medium text-primary">Handoff requested</span> : null}
                    </span>
                    {conversation.unread_count > 0 ? <Badge aria-label={`${conversation.unread_count} unread`}>{conversation.unread_count}</Badge> : null}
                  </button>
                </li>
              );
            })}
          </ul>
          {conversations.data?.length === 0 ? (
            <div className="grid justify-items-center gap-2 p-8 text-center text-sm text-muted-foreground">
              <Inbox size={24} aria-hidden="true" />
              <p>{filtered ? "No matching conversations." : retention === "archived" ? "No archived conversations." : "No customer conversations yet."}</p>
            </div>
          ) : null}
        </section>
        <section aria-label="Conversation details" className={`min-w-0 ${selected ? "" : "hidden lg:block"}`}>
          {selected && !thread ? <div className="space-y-3 p-4">
            <Button size="sm" variant="ghost" className="lg:hidden" onClick={() => setSelected(null)}><ArrowLeft size={14} /> Conversations</Button>
            {detail.isPending ? <div role="status" aria-label="Loading conversation"><Skeleton className="h-12" /></div> : null}
          </div> : null}
          {thread ? (
            <>
              <header className="flex flex-wrap items-center gap-3 border-b border-border p-4">
                <Button size="icon" variant="ghost" className="lg:hidden" aria-label="Back to conversations" onClick={() => setSelected(null)}><ArrowLeft size={16} /></Button>
                <div className="min-w-0 flex-1">
                  <h2 className="break-words text-base font-semibold">{thread.subject}</h2>
                  <p className="text-xs text-muted-foreground">{channelNames[thread.channel]}{thread.assignee_name ? ` · ${thread.assignee_name}` : " · Unassigned"}</p>
                </div>
                {thread.unread_count === 0 && messages?.some((message) => message.direction === "inbound") ? (
                  <Button size="sm" variant="ghost" disabled={markUnread.isPending} onClick={() => markUnread.mutate()}>Mark unread</Button>
                ) : null}
                <Badge variant="secondary" className="capitalize">{thread.status}</Badge>
                <Dialog>
                  <DialogTrigger asChild>
                    <Button size="icon" variant="ghost" className="min-[1440px]:hidden" aria-label="Show customer context"><PanelRight size={17} /></Button>
                  </DialogTrigger>
                  <DialogContent className="max-h-[85dvh] overflow-y-auto">
                    <DialogTitle>Customer context</DialogTitle>
                    <DialogDescription className="mb-4">Manage the conversation and its CRM records.</DialogDescription>
                    {requestError ? <RequestError error={requestError} /> : null}
                    {context}
                    <DialogClose asChild><Button variant="outline" className="mt-4">Close</Button></DialogClose>
                  </DialogContent>
                </Dialog>
              </header>
              {thread.whatsapp_service_window ? (
                <p className="border-b border-border bg-muted/40 px-4 py-3 text-sm" role="status">
                  {serviceWindowCopy(thread.whatsapp_service_window)}
                </p>
              ) : null}
              {thread.handoff_requested ? (
                <p className="border-b border-border bg-primary/5 px-4 py-3 text-sm">
                  <strong>{thread.handoff_accepted_at ? "Staff handling" : "Waiting for staff"}</strong>
                  {thread.handoff_reason ? ` · ${thread.handoff_reason}` : ""}
                </p>
              ) : null}
              <div ref={threadLog} role="log" aria-label="Customer messages" className="flex max-h-[58dvh] min-h-36 flex-col gap-3 overflow-y-auto bg-muted/30 p-3 sm:p-4"
                onScroll={(event) => {
                  const { scrollHeight, scrollTop, clientHeight } = event.currentTarget;
                  followMessages.current = scrollHeight - scrollTop - clientHeight < 80;
                }}>
                {messages?.length === 0 ? <p className="m-auto text-center text-sm text-muted-foreground">No messages in this conversation.</p> : null}
                {messages?.map((message, index) => {
                  const date = new Date(message.created_at);
                  const day = date.toLocaleDateString(undefined, { dateStyle: "medium" });
                  const previous = messages[index - 1];
                  const showDay = !previous || day !== new Date(previous.created_at).toLocaleDateString(undefined, { dateStyle: "medium" });
                  const inbound = message.direction === "inbound";
                  return <Fragment key={message.id}>
                    {showDay ? <div className="flex items-center gap-3 text-xs text-muted-foreground before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border">{day}</div> : null}
                    <article className={`grid max-w-[94%] min-w-0 gap-1 sm:max-w-[85%] ${inbound ? "self-start" : "self-end"}`}>
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      <span className="break-all font-medium">{message.sender}</span>
                      <time dateTime={message.created_at}>{date.toLocaleTimeString(undefined, { timeStyle: "short" })}</time>
                    </div>
                    <p className={`break-words whitespace-pre-wrap rounded-lg border px-3 py-2 text-sm leading-6 ${inbound ? "border-border bg-card" : "border-primary/20 bg-accent"}`}>{message.body}</p>
                    <p className={`text-xs ${inbound ? "text-left" : "text-right"} ${message.delivery_status === "failed" ? "text-destructive" : "text-muted-foreground"}`} aria-label={`Delivery ${deliveryLabel(message.delivery_status)}`}>{deliveryLabel(message.delivery_status)}</p>
                    </article>
                  </Fragment>;
                })}
              </div>
              <div className="grid gap-3 border-t border-border p-4">
                {thread.channel === "webchat" ? (
                  <>
                    <textarea aria-label="Staff reply" className={composerClass} placeholder="Reply to the visitor" value={staffReply} maxLength={5000} onChange={(event) => setStaffReply(event.target.value)} />
                    <Button className="justify-self-end" onClick={() => staffSend.mutate()} disabled={!staffReply.trim() || staffSend.isPending}><Send size={15} /> Send to visitor</Button>
                  </>
                ) : (
                  <>
                    {savedDraft ? <Button className="justify-self-start" size="sm" variant="outline" onClick={() => { setSubject(thread.subject); setDraft(savedDraft.body); }}>Restore saved draft</Button> : null}
                    {thread.channel === "email" ? <input aria-label="Reply subject" className={fieldClass} placeholder="Reply subject" value={subject} onChange={(event) => setSubject(event.target.value)} /> : null}
                    {thread.channel === "whatsapp" && thread.whatsapp_reply_mode === "test" ? <p className="text-xs text-muted-foreground">Restricted test reply. Approval can send one session message to the person who already wrote in. Templates stay unavailable, and customer messaging stays off.</p> : null}
                    {thread.channel === "whatsapp" && thread.whatsapp_reply_mode !== "test" ? <input aria-label="WhatsApp template name" className={fieldClass} placeholder="Template name" value={templateName} onChange={(event) => setTemplateName(event.target.value)} /> : null}
                    <textarea aria-label="Reply draft" className={composerClass} placeholder="Write a reply draft" value={draft} onChange={(event) => setDraft(event.target.value)} />
                    <div className="flex flex-wrap gap-2">
                      <Button variant="outline" onClick={() => aiDraft.mutate()} disabled={aiDraft.isPending}>{aiDraft.isPending ? "Drafting…" : "Draft with AI"}</Button>
                      <Button variant="secondary" onClick={() => save.mutate()} disabled={!draft.trim() || !recipient || save.isPending}>Save draft</Button>
                      <Button onClick={() => approval.mutate()} disabled={!draft.trim() || !thread.lead_id || !thread.reply_recipient || Boolean(thread.reply_unavailable) || approval.isPending}>Submit for approval</Button>
                    </div>
                    {!thread.lead_id || !thread.reply_recipient ? <p className="text-xs text-muted-foreground">Link a lead and a contact with a reply address to request approval.</p> : null}
                    {save.isSuccess ? <p role="status" className="text-sm text-muted-foreground">Draft saved.</p> : null}
                    {aiDraft.error ? <RequestError error={aiDraft.error} /> : null}
                    {approval.isSuccess ? <Link className={recordClass} href={`/approvals?approval=${approval.data.approval_id}`}>Open requested approval <ExternalLink size={13} /></Link> : null}
                    {thread.reply_unavailable ? <p className="text-xs text-muted-foreground">{thread.reply_unavailable}</p> : null}
                    {approval.error ? <RequestError error={approval.error} /> : null}
                  </>
                )}
              </div>
            </>
          ) : !selected ? (
            <div className="grid min-h-[30rem] place-content-center justify-items-center gap-3 p-6 text-center text-sm text-muted-foreground">
              <Inbox size={26} aria-hidden="true" />
              <p>Select a conversation to view its messages.</p>
            </div>
          ) : null}
        </section>
        <aside aria-label="Customer context" className="hidden min-w-0 border-l border-border p-4 min-[1440px]:block">
          <h2 className="mb-4 text-sm font-semibold">Customer context</h2>
          {context ?? <p className="text-sm text-muted-foreground">Select a conversation to see linked records.</p>}
        </aside>
      </div>
    </div>
  );
}

function RecordInquiry({ organizationId, conversationId, title, linked, onRecorded }: {
  organizationId: string;
  conversationId: string;
  title: string;
  linked: boolean;
  onRecorded: () => void;
}) {
  const [name, setName] = useState(title);
  const cache = useQueryClient();
  const record = useMutation({
    mutationFn: () => recordInboxInquiry(organizationId, conversationId, name.trim()),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["leads", organizationId] });
      void cache.invalidateQueries({ queryKey: ["inquiries", organizationId] });
      onRecorded();
    },
  });
  return <div className="grid gap-2">
    {record.isSuccess ? <Link className="text-sm font-medium text-primary underline" href={`/crm?tab=inquiries&id=${record.data.inquiry_id}`}>Open CRM inquiry</Link> :
      <details className="rounded-md border border-border p-2">
        <summary className="cursor-pointer text-sm font-medium">Record customer inquiry</summary>
        <form className="mt-2 grid gap-2" onSubmit={(event) => { event.preventDefault(); if (name.trim()) record.mutate(); }}>
          {!linked ? <label className="grid gap-1 text-xs">Lead title
            <input value={name} maxLength={200} onChange={(event) => setName(event.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm" required />
          </label> : null}
          <p className="text-xs text-muted-foreground">Save the customer’s first message to CRM for follow-up.</p>
          {record.error ? <RequestError error={record.error} /> : null}
          <Button type="submit" size="sm" disabled={record.isPending || !name.trim()}>{record.isPending ? "Saving…" : linked ? "Save inquiry" : "Create lead and inquiry"}</Button>
        </form>
      </details>}
  </div>;
}


export function WidgetSettingsDialog({ organizationId }: { organizationId: string }) {
  const [open, setOpen] = useState(false);
  const widget = useQuery({
    queryKey: ["inbox-widget", organizationId],
    queryFn: () => getInboxWidget(organizationId),
    enabled: open,
  });
  const client = useQueryClient();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button variant="outline"><Settings2 size={15} /> Website chat settings</Button></DialogTrigger>
      <DialogContent className="max-h-[85dvh] overflow-y-auto">
        <DialogTitle>Website chat settings</DialogTitle>
        <DialogDescription className="mb-4">Choose which websites can open a chat and how the workspace handles new conversations.</DialogDescription>
        {widget.isPending ? <div role="status" aria-label="Loading website chat settings"><Skeleton className="h-24" /></div> : null}
        {widget.error ? <RequestError error={widget.error} /> : null}
        {widget.isSuccess ? <WidgetSettingsForm organizationId={organizationId} widget={widget.data} onSave={(saved) => {
          client.setQueryData(["inbox-widget", organizationId], saved);
        }} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function WidgetSettingsForm({ organizationId, widget, onSave }: {
  organizationId: string;
  widget: InboxWidget | null;
  onSave: (widget: InboxWidget) => void;
}) {
  const [origins, setOrigins] = useState(widget?.allowed_domains.join("\n") ?? "");
  const [welcome, setWelcome] = useState(widget?.welcome_message ?? "How can we help?");
  const [mode, setMode] = useState<WidgetSettings["operating_mode"]>(widget?.operating_mode ?? "human_review");
  const [enabled, setEnabled] = useState(widget?.enabled ?? true);
  const [originError, setOriginError] = useState("");
  const save = useMutation({
    mutationFn: (settings: WidgetSettings) => saveInboxWidget(organizationId, settings),
    onSuccess: onSave,
  });
  const siteOrigin = typeof window === "undefined" ? "" : window.location.origin;
  const apiOrigin = resolveApiBaseUrl(process.env.NEXT_PUBLIC_API_URL) || siteOrigin;
  const embed = widget && siteOrigin
    ? `<script src="${siteOrigin}/atlas-chat-widget.js" data-widget-id="${widget.public_id}" data-api-base="${apiOrigin}" defer></script>`
    : "";

  return (
    <form className="grid gap-4" onSubmit={(event) => {
      event.preventDefault();
      setOriginError("");
      const values = [...new Set(origins.split(/[\n,]/).map((value) => value.trim()).filter(Boolean))];
      try {
        const allowed = [...new Set(values.map((value) => {
          const url = new URL(value);
          if (!["http:", "https:"].includes(url.protocol) || url.pathname !== "/" ||
              url.search || url.hash || url.username || url.password) throw new Error();
          return url.origin;
        }))];
        if (!allowed.length || allowed.length > 20) throw new Error();
        save.mutate({ allowed_domains: allowed, welcome_message: welcome.trim(), operating_mode: mode, enabled });
      } catch {
        setOriginError("Enter 1 to 20 website origins, such as https://example.com, without paths.");
      }
    }}>
      <label className="grid gap-1 text-sm font-medium">Allowed website origins
        <textarea className={composerClass} value={origins} onChange={(event) => setOrigins(event.target.value)} placeholder="https://example.com" required />
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input className="mt-0.5 size-4" type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
        <span><span className="block font-medium">Accept website chats</span><span className="block text-xs text-muted-foreground">Turning this off pauses the embed. Existing conversations stay in Inbox.</span></span>
      </label>
      {originError ? <p role="alert" className="text-sm text-destructive">{originError}</p> : null}
      <label className="grid gap-1 text-sm font-medium">Welcome message
        <input className={fieldClass} value={welcome} onChange={(event) => setWelcome(event.target.value)} maxLength={500} required />
      </label>
      <label className="grid gap-1 text-sm font-medium">Operating mode
        <select className={fieldClass} value={mode} onChange={(event) => setMode(event.target.value as WidgetSettings["operating_mode"])}>
          <option value="human_review">Staff only</option>
          <option value="ai_assist">Staff with draft assistance</option>
          <option value="ai_auto_reply">Automatic replies with staff handoff</option>
        </select>
      </label>
      {embed ? (
        <label className="grid gap-1 text-sm font-medium">Website embed code
          <textarea readOnly className={`${composerClass} font-mono text-xs`} value={embed} onFocus={(event) => event.currentTarget.select()} />
        </label>
      ) : null}
      {save.isSuccess ? <p role="status" className="text-sm text-muted-foreground">{save.data?.enabled ? "Website chat settings saved." : "Website chat paused."}</p> : null}
      {save.error ? <RequestError error={save.error} /> : null}
      <div className="flex justify-end gap-2">
        <DialogClose asChild><Button type="button" variant="outline">Close</Button></DialogClose>
        <Button type="submit" disabled={!welcome.trim() || save.isPending}>Save website chat settings</Button>
      </div>
    </form>
  );
}
