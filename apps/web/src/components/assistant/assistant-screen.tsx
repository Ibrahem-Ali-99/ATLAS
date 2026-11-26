"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, Bot, Building2, CheckCircle2, ChevronDown, FileText, PanelLeft, Send, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { ConfirmButton } from "@/components/confirm-button";
import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, sessionQueryOptions } from "@/lib/api";
import { isEvaluationConversation } from "@/lib/conversations";
import { isDemoSession } from "@/lib/demo-session";
import { RichText } from "@/components/assistant/rich-text";
import { archiveConversation, createConversation, dismissAssistantProposal, getConversation, listConversations, renameConversation, restoreConversation, streamConversationMessage, submitAssistantProposal } from "@/lib/records-api";
import type { AssistantProposal, AssistantReply, ChatMessage, Conversation, ConversationDetail, MessageSource } from "@/lib/records";
import { useWorkspace } from "@/lib/use-workspace";

const NO_RECORDS = "I could not find relevant company documents or CRM records for that question.";

export function AssistantScreen() {
  const { organizationId, organizationName } = useWorkspace();
  if (!organizationId) {
    return null;
  }
  return (
    <AssistantWorkspace key={organizationId} organizationId={organizationId} organizationName={organizationName ?? "this organization"} />
  );
}

function AssistantWorkspace({
  organizationId,
  organizationName,
}: {
  organizationId: string;
  organizationName: string;
}) {
  const router = useRouter();
  const session = useQuery(sessionQueryOptions);
  const demonstration = isDemoSession(session.data);
  const params = useSearchParams();
  const conversationId = params.get("conversation");
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [streaming, setStreaming] = useState("");
  const [phases, setPhases] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [retention, setRetention] = useState("active");
  const [titleDraft, setTitleDraft] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const seededPrompt = useRef(false);
  useEffect(() => {
    const prompt = params.get("prompt");
    if (!seededPrompt.current && prompt && !conversationId) {
      seededPrompt.current = true;
      setDraft(prompt.slice(0, 4000));
    }
  }, [params, conversationId]);
  const [panelOpen, setPanelOpen] = useState(false);
  const [sourcesDialog, setSourcesDialog] = useState(false);
  const [focusSource, setFocusSource] = useState<string | null>(null);
  const conversations = useQuery({
    queryKey: ["conversations", organizationId, retention],
    queryFn: () => listConversations(organizationId, retention),
  });
  const detail = useQuery({
    queryKey: ["conversation", organizationId, conversationId],
    queryFn: () => getConversation(organizationId, conversationId ?? ""),
    enabled: Boolean(conversationId),
  });
  const create = useMutation({
    mutationFn: () => createConversation(organizationId),
    onSuccess: (conversation) => {
      void queryClient.invalidateQueries({ queryKey: ["conversations", organizationId] });
      setHistoryOpen(false);
      router.replace(`/assistant?conversation=${conversation.id}`);
    },
  });
  const send = useMutation({
    mutationFn: async ({ content, targetConversationId }: { content: string; targetConversationId: string }) => {
      setStreaming("");
      setPhases([]);
      setNotice(null);
      let phase = "";
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        return await streamConversationMessage(
          organizationId,
          targetConversationId,
          content,
          (token) => {
            if (phase === "verifying") {
              return;
            }
            setStreaming((current) => current + token);
          },
          (next) => {
            phase = next;
            setPhases((current) => (current.at(-1) === next ? current : [...current, next]));
          },
          controller.signal,
        );
      } finally {
        abortRef.current = null;
      }
    },
    onSuccess: async (reply) => {
      setDraft("");
      setStreaming("");
      setPhases([]);
      setNotice(searchNotice(reply));
      if (reply.message.sources.length > 0) {
        setFocusSource(sourceKey(reply.message.sources[0]));
      }
      await queryClient.invalidateQueries({ queryKey: ["conversation", organizationId, reply.conversation_id] });
      await queryClient.invalidateQueries({ queryKey: ["conversations", organizationId] });
    },
    onError: async (error, { targetConversationId }) => {
      setStreaming("");
      setPhases([]);
      await queryClient.invalidateQueries({ queryKey: ["conversation", organizationId, targetConversationId] });
      if (error instanceof ApiError && error.code === "cancelled") {
        const saved = queryClient.getQueryData<ConversationDetail>([
          "conversation",
          organizationId,
          targetConversationId,
        ]);
        setNotice(saved?.messages.at(-1)?.role === "assistant" ? null : "Stopped before the answer was saved.");
      }
    },
  });
  const rename = useMutation({
    mutationFn: (title: string) => renameConversation(organizationId, conversationId ?? "", title),
    onSuccess: async () => {
      setTitleDraft(null);
      await queryClient.invalidateQueries({ queryKey: ["conversations", organizationId] });
      await queryClient.invalidateQueries({ queryKey: ["conversation", organizationId, conversationId] });
    },
  });
  const archive = useMutation({
    mutationFn: () => archiveConversation(organizationId, conversationId ?? ""),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["conversations", organizationId] });
      await queryClient.invalidateQueries({ queryKey: ["conversation", organizationId, conversationId] });
    },
  });
  const restore = useMutation({
    mutationFn: () => restoreConversation(organizationId, conversationId ?? ""),
    onSuccess: async () => {
      setRetention("active");
      await queryClient.invalidateQueries({ queryKey: ["conversations", organizationId] });
      await queryClient.invalidateQueries({ queryKey: ["conversation", organizationId, conversationId] });
    },
  });
  const proposalAction = useMutation({
    mutationFn: (input: { proposalId: string; times?: { starts_at: string; ends_at: string }; dismiss?: boolean }) =>
      input.dismiss
        ? dismissAssistantProposal(organizationId, conversationId ?? "", input.proposalId)
        : submitAssistantProposal(organizationId, conversationId ?? "", input.proposalId, input.times),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["conversation", organizationId, conversationId] });
    },
  });

  const current = conversations.data?.find((item) => item.id === conversationId) ?? null;
  const threadTitle = detail.data?.title ?? current?.title ?? "Assistant";
  const archivedAt = detail.data?.archived_at ?? current?.archived_at ?? null;
  const sources = useMemo(() => {
    const messages = detail.data?.messages ?? [];
    return messages.flatMap((message) => message.sources);
  }, [detail.data?.messages]);
  const focused = sources.find((source) => sourceKey(source) === focusSource) ?? sources[0] ?? null;
  const recordSources = sources.filter((source) => source.kind === "crm");
  const documentSources = sources.filter((source) => source.kind === "document");

  async function submit(content = draft.trim()) {
    if (!content || send.isPending || create.isPending) return;
    let targetConversationId = conversationId;
    if (!targetConversationId) {
      try {
        const conversation = await create.mutateAsync();
        targetConversationId = conversation.id;
        router.replace(`/assistant?conversation=${conversation.id}`);
      } catch {
        return;
      }
    }
    send.mutate({ content, targetConversationId });
  }

  function revealSources() {
    if (window.matchMedia("(max-width: 1279px)").matches) {
      setSourcesDialog(true);
    } else {
      setPanelOpen(true);
    }
  }

  function clearThreadControls() {
    setDraft("");
    setNotice(null);
    setFocusSource(null);
    setPanelOpen(false);
    send.reset();
  }

  const history = (
    <ConversationHistory
      organizationName={organizationName}
      conversations={conversations.data}
      pending={conversations.isPending}
      error={conversations.isError ? conversations.error : create.isError ? create.error : null}
      query={query}
      retention={retention}
      onRetention={setRetention}
      onQuery={setQuery}
      conversationId={conversationId}
      creating={create.isPending}
      busy={send.isPending}
      onCreate={() => { clearThreadControls(); create.mutate(); }}
      onOpen={(id) => {
        setHistoryOpen(false);
        if (id === conversationId) return;
        clearThreadControls();
        router.replace(`/assistant?conversation=${id}`);
      }}
      onClose={() => setHistoryOpen(false)}
    />
  );

  return (
    <div className="assistant-layout">
      <aside className={`assistant-history ${historyOpen ? "mobile-open" : ""}`} aria-label="Assistant conversation history">{history}</aside>
      <section className="assistant-chat" aria-label={threadTitle}>
        <header className="assistant-chat-header">
          <button type="button" className="button button-ghost button-icon history-toggle" aria-label="Open conversation history" onClick={() => setHistoryOpen(true)}><PanelLeft size={17} /></button>
          <div className="min-w-0">
            {titleDraft === null ? (
              <h1>{threadTitle}</h1>
            ) : (
              <form className="flex flex-wrap items-center gap-2" onSubmit={(event) => { event.preventDefault(); if (titleDraft.trim()) rename.mutate(titleDraft.trim()); }}>
                <Input aria-label="Conversation title" value={titleDraft} onChange={(event) => setTitleDraft(event.target.value)} className="h-8 max-w-xs" />
                <Button type="submit" size="sm" disabled={!titleDraft.trim() || rename.isPending}>Save</Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setTitleDraft(null)}>Cancel</Button>
              </form>
            )}
            <p>{demonstration ? "Answers use this workspace’s records" : "ATLAS Assistant · Sources enabled"}</p>
          </div>
          <span className="badge badge-green"><span className="live-dot" /> Available</span>
          {conversationId && titleDraft === null ? <Button type="button" size="sm" variant="ghost" onClick={() => setTitleDraft(threadTitle)}>Rename</Button> : null}
          {conversationId && archivedAt ? (
            <Button type="button" size="sm" variant="ghost" disabled={restore.isPending} onClick={() => restore.mutate()}>Restore</Button>
          ) : conversationId ? (
            <ConfirmButton size="sm" label="Archive" confirmLabel="Archive and keep messages" pendingLabel="Archiving…" pending={archive.isPending} onConfirm={() => archive.mutate()} />
          ) : null}
          <button type="button" className="button button-ghost button-icon context-toggle force" aria-label="Open workspace context" aria-expanded={panelOpen} onClick={() => setPanelOpen((value) => !value)}><FileText size={16} /></button>
        </header>
        <div className="assistant-thread">
          {!conversationId ? <EmptyThread organizationName={organizationName} onPrompt={setDraft} /> : null}
          {conversationId && detail.data && detail.data.messages.length === 0 && !send.isPending ? (
            <EmptyThread organizationName={organizationName} onPrompt={setDraft} />
          ) : null}
          {detail.isPending && conversationId ? <Skeleton className="h-16 w-2/3" /> : null}
          {detail.isError ? <RequestError error={detail.error} /> : null}
          {detail.data?.messages.map((message) => (
            <MessageView
              key={message.id}
              userInitials={personInitials(session.data?.user.full_name ?? "You")}
              message={message}
              proposalPending={proposalAction.isPending}
              onSource={(source) => {
                setFocusSource(sourceKey(source));
                setPanelOpen(true);
              }}
              onProposal={(proposalId, times) => proposalAction.mutate({ proposalId, times })}
              onDismiss={(proposalId) => proposalAction.mutate({ proposalId, dismiss: true })}
            />
          ))}
          {send.isPending ? (
            <article className="assistant-message" aria-live="polite">
              <span className="assistant-avatar"><Bot size={16} /></span>
              <div>
                <strong>ATLAS Assistant</strong>
                <div className="streaming-line">{streamStatus(phases, streaming)}</div>
                {streaming ? <RichText id="streaming" text={streaming} /> : null}
                <Button type="button" size="sm" variant="ghost" onClick={() => abortRef.current?.abort()}>Stop</Button>
              </div>
            </article>
          ) : null}
          {notice ? <StatusNote>{notice}</StatusNote> : null}
          {send.isError && !(send.error instanceof ApiError && send.error.code === "cancelled") ? <FailureNotice error={send.error} onRetry={() => submit()} canRetry={draft.trim().length > 0} /> : null}
          {rename.error || archive.error || restore.error || proposalAction.error ? <RequestError error={rename.error ?? archive.error ?? restore.error ?? proposalAction.error} /> : null}
        </div>
        <form className="assistant-composer" onSubmit={(event) => { event.preventDefault(); submit(); }}>
          <Textarea
            aria-label="Ask ATLAS Assistant"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            placeholder="Ask about customers, work, or knowledge…"
            disabled={send.isPending || create.isPending}
          />
          <div>
            <span>ATLAS can make mistakes. Verify important information.</span>
            {send.isPending ? (
              <Button type="button" size="icon" variant="ghost" aria-label="Stop" onClick={() => abortRef.current?.abort()}>Stop</Button>
            ) : (
              <button type="submit" className="button button-primary button-icon" aria-label="Send question" disabled={create.isPending || draft.trim().length === 0}><Send size={15} /></button>
            )}
          </div>
        </form>
      </section>
      <aside className={`assistant-context ${panelOpen ? "mobile-open" : ""}`} aria-label="CRM context">
        <header>
          <h2>CRM context</h2>
          <span className="badge badge-blue">{recordSources.length} records</span>
          <button type="button" className="button button-ghost button-icon context-close" aria-label="Close workspace context" onClick={() => setPanelOpen(false)}><X size={16} /></button>
        </header>
        <div className="assistant-context-content">
          {recordSources.length === 0 && documentSources.length === 0 ? (
            <div className="context-note"><AlertCircle size={15} /><p><strong>Context appears with an answer</strong><small>Customer records and document passages cited in this conversation show up here.</small></p></div>
          ) : null}
          {recordSources.map((source) => (
            <Link key={sourceKey(source)} href={source.record_id ? crmRecordHref(source) : "/crm"} className="context-record">
              <Building2 size={15} />
              <span><strong>{source.title}</strong><small>{recordLabel(source)}</small></span>
              <ArrowRight size={14} />
            </Link>
          ))}
          {documentSources.length > 0 ? (
            <div className="citation-list">
              {documentSources.map((source) => (
                <details key={sourceKey(source)} open={sourceKey(source) === focusSource}>
                  <summary>{source.title}</summary>
                  <p>{source.excerpt}</p>
                </details>
              ))}
            </div>
          ) : null}
          <div className="context-note"><AlertCircle size={15} /><p><strong>Context is read-only</strong><small>Proposed changes require explicit approval.</small></p></div>
        </div>
      </aside>
      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Conversations</DialogTitle>
            <DialogDescription>History for {organizationName}.</DialogDescription>
          </DialogHeader>
          {history}
        </DialogContent>
      </Dialog>
      <Dialog open={sourcesDialog} onOpenChange={setSourcesDialog}>
        <DialogContent className="max-h-[80vh] overflow-y-auto xl:hidden">
          <DialogHeader>
            <DialogTitle>Sources</DialogTitle>
            <DialogDescription>Passages and records that support the answers in this conversation.</DialogDescription>
          </DialogHeader>
          {focused ? (
            <SourcePanel source={focused} sources={sources} onSelect={(source) => setFocusSource(sourceKey(source))} />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ConversationHistory({
  organizationName,
  conversations,
  pending,
  error,
  query,
  retention,
  onRetention,
  onQuery,
  conversationId,
  creating,
  busy,
  onCreate,
  onOpen,
  onClose,
}: {
  organizationName: string;
  conversations: Conversation[] | undefined;
  pending: boolean;
  error: unknown;
  query: string;
  retention: string;
  onRetention: (value: string) => void;
  onQuery: (value: string) => void;
  conversationId: string | null;
  creating: boolean;
  busy: boolean;
  onCreate: () => void;
  onOpen: (id: string) => void;
  onClose: () => void;
}) {
  const filtered = (conversations ?? []).filter((item) => item.title.toLowerCase().includes(query.trim().toLowerCase()));
  const customer = filtered.filter((item) => !isEvaluationConversation(item));
  return (
    <>
      <header>
        <div><h2>Assistant</h2><p>Workspace conversations</p></div>
        <button type="button" className="button button-ghost button-icon history-close" aria-label="Close conversation history" onClick={onClose}><X size={16} /></button>
      </header>
      <button type="button" className="button button-primary button-md" disabled={creating || busy} onClick={onCreate}>{creating ? "Starting…" : "New conversation"}</button>
      <p className="sr-only">Stored for {organizationName}. A new chat takes its title from the first question.</p>
      <label className="module-search"><input value={query} onChange={(event) => onQuery(event.target.value)} placeholder="Search conversations" aria-label="Search assistant conversations" /></label>
      <label className="toolbar-select">
        <span className="sr-only">Conversation retention</span>
        <select aria-label="Conversation retention" value={retention} onChange={(event) => onRetention(event.target.value)}>
          <option value="active">Active</option>
          <option value="archived">Archived</option>
        </select>
      </label>
      {pending ? <Skeleton className="mt-4 h-16 w-full" /> : null}
      {error ? <div className="mt-4"><RequestError error={error} /></div> : null}
      {conversations && customer.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          {query.trim() ? "No conversations match this search." : retention === "archived" ? "No archived conversations." : "No conversations yet."}
        </p>
      ) : null}
      <div className="assistant-history-list">
        {customer.map((conversation) => (
          <button
            type="button"
            key={conversation.id}
            className={conversation.id === conversationId ? "active" : ""}
            aria-current={conversation.id === conversationId ? "true" : undefined}
            disabled={creating || busy}
            onClick={() => onOpen(conversation.id)}
          >
            <span><Bot size={14} /><strong>{conversation.title}</strong></span>
            <small>{new Date(conversation.updated_at).toLocaleDateString()}</small>
          </button>
        ))}
      </div>
      <div className="assistant-privacy"><Sparkles size={14} /><p><strong>Grounded in your workspace</strong><small>Answers cite accessible CRM and knowledge records.</small></p></div>
    </>
  );
}

function EmptyThread({
  organizationName,
  onPrompt,
}: {
  organizationName: string;
  onPrompt: (value: string) => void;
}) {
  const prompts = [
    "Who are our customers?",
    "Who works in this workspace?",
    "Which leads should I prioritize?",
    "How is the business doing?",
    "What does our warehousing note say?",
    "Draft a follow-up for a qualified lead",
  ];
  return (
    <div className="assistant-welcome">
      <span className="assistant-logo"><Sparkles size={22} /></span>
      <h2>How can I help?</h2>
      <p>Ask about customer activity, open work, or trusted knowledge in {organizationName}.</p>
      <div>
        {prompts.map((prompt) => (
          <button key={prompt} type="button" onClick={() => onPrompt(prompt)}>{prompt}<ArrowRight size={14} /></button>
        ))}
      </div>
    </div>
  );
}

function MessageView({
  userInitials,
  message,
  proposalPending,
  onSource,
  onProposal,
  onDismiss,
}: {
  userInitials: string;
  message: ChatMessage;
  proposalPending: boolean;
  onSource: (source: MessageSource) => void;
  onProposal: (proposalId: string, times?: { starts_at: string; ends_at: string }) => void;
  onDismiss: (proposalId: string) => void;
}) {
  const documents = message.sources.filter((source) => source.kind === "document");
  const refused = message.role === "assistant" && message.content.includes(NO_RECORDS);
  if (message.role === "user") {
    return (
      <article className="assistant-message user">
        <span className="avatar avatar-blue avatar-sm">{userInitials}</span>
        <div><strong>You</strong><p>{message.content}</p></div>
      </article>
    );
  }
  return (
    <article className="assistant-message">
      <span className="assistant-avatar"><Bot size={16} /></span>
      <div className="assistant-response">
        <strong>ATLAS Assistant</strong>
        {refused ? <p>{message.content}</p> : <RichText id={message.id} text={message.content} />}
        {message.steps && message.steps.length > 0 ? (
          <div className="evidence-list">
            {message.steps.map((step, index) => (
              <div key={`${message.id}-step-${index}`}>
                <span>
                  <strong>{stepLabel(step.tool_name)}</strong>
                  <small>{step.detail || stepStatus(step.status)}</small>
                </span>
              </div>
            ))}
          </div>
        ) : null}
        {documents.length > 0 ? <SourceList sources={documents} onSource={onSource} /> : null}
        {message.proposals?.map((proposal) => (
          <ProposalCard key={proposal.id} proposal={proposal} pending={proposalPending} onSubmit={onProposal} onDismiss={onDismiss} />
        ))}
      </div>
    </article>
  );
}

function stepStatus(status: string): string {
  if (status === "succeeded" || status === "completed" || status === "ok") return "Completed";
  if (status === "failed" || status === "error") return "Needs attention";
  return status.replaceAll("_", " ");
}

function stepLabel(tool: string): string {
  const labels: Record<string, string> = {
    list_companies: "Companies",
    list_contacts: "Contacts",
    list_leads: "Leads",
    list_members: "Workspace members",
    list_opportunities: "Pipeline",
    list_tasks: "Tasks",
    search_inbox: "Inbox",
    business_analytics: "Analytics",
    search_knowledge: "Knowledge",
    check_availability: "Calendar",
    list_workflow_runs: "Workflow runs",
    draft_customer_message: "Draft",
    propose_appointment: "Appointment proposal",
    propose_task: "Task proposal",
    respond: "Reply",
    clarify: "Clarifying question",
  };
  return labels[tool] ?? tool.replaceAll("_", " ");
}

function personInitials(name: string): string {
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("") || "Y";
}

function SourceList({
  sources,
  onSource,
}: {
  sources: MessageSource[];
  onSource: (source: MessageSource) => void;
}) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <button type="button" className="source-toggle" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <FileText size={14} /> {sources.length} sources <ChevronDown size={14} className={open ? "rotate-180" : ""} />
      </button>
      {open ? (
        <div className="citation-list">
          {sources.map((source) => (
            <details key={sourceKey(source)}>
              <summary>Knowledge · {source.title}</summary>
              <p>{source.excerpt}</p>
              <button type="button" className="text-button" onClick={() => onSource(source)}>Preview in context <ArrowRight size={12} /></button>
            </details>
          ))}
        </div>
      ) : null}
    </>
  );
}

function SourcePanel({
  source,
  sources,
  onSelect,
}: {
  source: MessageSource;
  sources: MessageSource[];
  onSelect: (source: MessageSource) => void;
}) {
  return (
    <div className="flex h-full flex-col p-4">
      <h2 className="text-sm font-semibold">Source</h2>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">
        A passage or record that supports the answer, or an inventory row the answer lists.
      </p>
      <p className="mt-2 text-xs text-muted-foreground">{sourceKindLabel(source)}</p>
      <div className="mt-4 rounded-lg border border-border bg-card p-3">
        <Badge variant="secondary">{source.kind === "document" ? "Document" : source.record_type ?? "CRM"}</Badge>
        <p className="mt-2 font-medium">{source.title}</p>
        {source.page_number !== null ? <p className="mt-1 text-xs text-muted-foreground">Page {source.page_number}</p> : null}
        <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{source.excerpt}</p>
      </div>
      {sources.length > 1 ? (
        <ul className="mt-4 space-y-1">
          {sources.map((item, index) => (
            <li key={`${sourceKey(item)}-${index}`}>
              <button type="button" className="w-full truncate rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent" onClick={() => onSelect(item)}>
                {item.title}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function StatusNote({ children }: { children: string }) {
  return <p className="rounded-md border border-border bg-card px-3 py-2 text-sm leading-6 text-muted-foreground">{children}</p>;
}

function FailureNotice({ error, onRetry, canRetry }: { error: unknown; onRetry: () => void; canRetry: boolean }) {
  const copy = failureCopy(error);
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-3 text-sm" role="alert">
      <p className="font-medium">{copy.heading}</p>
      <p className="mt-1 leading-6 text-foreground">{copy.detail}</p>
      {canRetry ? (
        <Button type="button" size="sm" variant="outline" className="mt-3" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}

function failureCopy(error: unknown): { heading: string; detail: string } {
  if (!(error instanceof ApiError)) {
    return {
      heading: "The reply did not finish",
      detail: error instanceof Error ? error.message : "Request failed",
    };
  }
  if (error.code === "llm_unconfigured" || error.code === "embedding_unconfigured") {
    return { heading: "The assistant is not connected yet", detail: "An administrator needs to connect a language model before answers can be generated." };
  }
  if (error.code === "llm_rate_limited" || error.code === "embedding_rate_limited") {
    return { heading: "The assistant is busy", detail: "Too many requests were sent. Wait a moment and try again." };
  }
  if (
    error.code === "llm_unavailable" ||
    error.code === "embedding_unavailable" ||
    error.code === "llm_timeout" ||
    error.code === "embedding_timeout"
  ) {
    return { heading: "The assistant is unavailable", detail: "The language service did not respond. Try again in a moment." };
  }
  if (error.code === "embedding_dimension_mismatch") {
    return { heading: "Document search needs to be rebuilt", detail: "The document index does not match the current search setup. An administrator can rebuild it from Knowledge." };
  }
  if (error.status === 403 || error.code === "forbidden") {
    return { heading: "Permission denied", detail: error.message };
  }
  if (error.code === "cancelled") {
    return { heading: "Stopped", detail: error.message };
  }
  if (error.status === 404 || error.code === "not_found") {
    return { heading: "You cannot use this conversation", detail: error.message };
  }
  return { heading: "The reply did not finish", detail: error.message };
}

function searchNotice(reply: AssistantReply): string | null {
  if (reply.document_search === "skipped") {
    return null;
  }
  if (reply.document_search === "unconfigured") {
    return "Document search is not set up yet. This answer used customer records only.";
  }
  if (reply.document_search === "unavailable") {
    return "Document search did not run, so this answer used customer records only.";
  }
  if (reply.document_search === "empty" && reply.message.sources.every((source) => source.kind !== "document")) {
    return "No company document matched this question.";
  }
  return null;
}

function sourceKey(source: MessageSource): string {
  return `${source.kind}-${source.chunk_id ?? source.record_id ?? source.document_id ?? source.title}`;
}

function streamStatus(phases: string[], streaming: string): string {
  const last = phases.at(-1);
  if (last === "verifying") {
    return "Checking the answer against company records";
  }
  const labels = phases.map(phaseLabel).filter((label): label is string => label !== null);
  if (streaming) {
    return labels.includes("Streaming an answer") ? "Streaming an answer" : "Assistant";
  }
  return labels.at(-1) ?? "Preparing";
}

function phaseLabel(phase: string): string | null {
  if (phase === "preparing") return "Preparing";
  if (phase === "selecting_tools") return "Choosing what to look up";
  if (phase === "searching_crm") return "Searching company records";
  if (phase === "retrieving_documents") return "Retrieving documents";
  if (phase === "verifying") return "Checking the answer against company records";
  if (phase === "streaming") return "Streaming an answer";
  return null;
}

function sourceKindLabel(source: MessageSource): string {
  if (source.chunk_id) return "Supporting passage";
  if (source.kind === "document") return "Document inventory";
  return "CRM record";
}

function crmRecordHref(source: MessageSource): string {
  if (source.record_type === "conversation") return "/inbox";
  const tab = source.record_type === "company" ? "companies"
    : source.record_type === "contact" ? "contacts"
      : source.record_type === "inquiry" ? "inquiries"
        : "leads";
  return `/crm?tab=${tab}&id=${encodeURIComponent(source.record_id ?? "")}`;
}

function recordLabel(source: MessageSource): string {
  if (source.record_type === "company") return "company record";
  if (source.record_type === "contact") return "contact record";
  if (source.record_type === "inquiry") return "inquiry";
  if (source.record_type === "conversation") return "conversation";
  return "lead record";
}

function ProposalCard({
  proposal,
  pending,
  onSubmit,
  onDismiss,
}: {
  proposal: AssistantProposal;
  pending: boolean;
  onSubmit: (proposalId: string, times?: { starts_at: string; ends_at: string }) => void;
  onDismiss: (proposalId: string) => void;
}) {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const validTime = proposal.kind !== "appointment" || (Boolean(start && end) && Date.parse(start) < Date.parse(end));
  const href = proposal.approval_id
    ? `/approvals?approval=${proposal.approval_id}`
    : proposal.task_id
      ? "/workflows"
      : proposal.lead_id
        ? `/crm?tab=leads&id=${proposal.lead_id}`
        : null;
  const linkLabel = proposal.approval_id ? "Open approval" : proposal.task_id ? "Open tasks" : proposal.lead_id ? "Open lead" : null;
  return (
    <section className="proposed-action">
      <span><CheckCircle2 size={16} /></span>
      <div>
      <strong>Proposed action</strong>
      <p>{proposal.title}. {proposal.summary}</p>
      <p className="mt-2 text-sm font-medium text-foreground">{proposal.result_label}</p>
      {proposal.status === "proposed" && proposal.kind === "appointment" ? (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <label className="grid gap-1 text-xs text-muted-foreground">Starts
            <Input type="datetime-local" value={start} onChange={(event) => setStart(event.target.value)} />
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">Ends
            <Input type="datetime-local" value={end} onChange={(event) => setEnd(event.target.value)} />
          </label>
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        {proposal.status === "proposed" ? (
          <>
            <Button type="button" size="sm" disabled={pending || !validTime} onClick={() => onSubmit(proposal.id, proposal.kind === "appointment" ? { starts_at: new Date(start).toISOString(), ends_at: new Date(end).toISOString() } : undefined)}>
              {proposal.kind === "task" ? "Create task" : "Request approval"}
            </Button>
            <Button type="button" size="sm" variant="ghost" disabled={pending} onClick={() => onDismiss(proposal.id)}>Dismiss</Button>
          </>
        ) : null}
        {href && linkLabel ? <Link href={href} className="text-button">{linkLabel} <ArrowRight size={12} /></Link> : null}
      </div>
      </div>
    </section>
  );
}
