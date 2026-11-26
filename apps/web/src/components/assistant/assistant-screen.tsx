"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, FileText, MessageSquare, PanelLeft, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useRef, useState } from "react";

import { ConfirmButton } from "@/components/confirm-button";
import { ProviderNotice } from "@/components/provider-notice";
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
import { ApiError } from "@/lib/api";
import { isEvaluationConversation } from "@/lib/conversations";
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
    />
  );

  return (
    <div className="flex h-full min-h-0 gap-2 bg-background p-2">
      <aside className="hidden w-[300px] shrink-0 flex-col rounded-[14px] border border-border bg-card lg:flex">{history}</aside>
      <section className="flex min-h-0 min-w-0 flex-1 flex-col px-2 sm:px-6">
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border py-4">
          <div className="min-w-0">
            {titleDraft === null ? (
              <h1 className="truncate text-xl font-semibold leading-tight text-foreground">{threadTitle}</h1>
            ) : (
              <form className="flex flex-wrap items-center gap-2" onSubmit={(event) => { event.preventDefault(); if (titleDraft.trim()) rename.mutate(titleDraft.trim()); }}>
                <Input aria-label="Conversation title" value={titleDraft} onChange={(event) => setTitleDraft(event.target.value)} className="h-9 max-w-xs" />
                <Button type="submit" size="sm" disabled={!titleDraft.trim() || rename.isPending}>Save title</Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setTitleDraft(null)}>Cancel</Button>
              </form>
            )}
            <p className="mt-1 text-sm text-muted-foreground">Ask ATLAS about your workspace, then follow the evidence.</p>
          </div>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            {conversationId && titleDraft === null ? (
              <Button type="button" size="sm" variant="outline" onClick={() => setTitleDraft(threadTitle)}>Rename</Button>
            ) : null}
            {conversationId && archivedAt ? (
              <Button type="button" size="sm" variant="outline" disabled={restore.isPending} onClick={() => restore.mutate()}>Restore</Button>
            ) : conversationId ? (
              <ConfirmButton size="sm" label="Archive" confirmLabel="Archive and keep messages" pendingLabel="Archiving…" pending={archive.isPending} onConfirm={() => archive.mutate()} />
            ) : null}
            <Button type="button" size="sm" variant="outline" className="lg:hidden" onClick={() => setHistoryOpen(true)}>
              <PanelLeft size={15} /> History
            </Button>
            {sources.length > 0 ? (
              <Button type="button" size="sm" variant="outline" aria-expanded={panelOpen || sourcesDialog} onClick={revealSources}>
                <FileText size={15} /> Sources
              </Button>
            ) : null}
          </div>
          <div className="basis-full break-words"><ProviderNotice organizationId={organizationId} compact /></div>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 py-4">
            {!conversationId ? <EmptyThread organizationName={organizationName} onPrompt={setDraft} /> : null}
            {conversationId && detail.data && detail.data.messages.length === 0 && !send.isPending ? (
              <EmptyThread organizationName={organizationName} onPrompt={setDraft} />
            ) : null}
            {detail.isPending && conversationId ? (
              <div className="space-y-3">
                <Skeleton className="h-16 w-2/3" />
                <Skeleton className="ml-auto h-12 w-1/2" />
              </div>
            ) : null}
            {detail.isError ? <RequestError error={detail.error} /> : null}
            {detail.data?.messages.map((message) => (
              <MessageView
                key={message.id}
                message={message}
                proposalPending={proposalAction.isPending}
                onSource={(source) => {
                  setFocusSource(sourceKey(source));
                  revealSources();
                }}
                onProposal={(proposalId, times) => proposalAction.mutate({ proposalId, times })}
                onDismiss={(proposalId) => proposalAction.mutate({ proposalId, dismiss: true })}
              />
            ))}
            {send.isPending ? (
              <article className="text-sm" aria-live="polite">
                <p className="text-xs font-medium text-muted-foreground">{streamStatus(phases, streaming)}</p>
                {streaming ? <div className="mt-2"><RichText id="streaming" text={streaming} /></div> : null}
              </article>
            ) : null}
          </div>
        </div>
        <div className="py-4">
          <div className="mx-auto w-full max-w-3xl space-y-3">
            {notice ? <StatusNote>{notice}</StatusNote> : null}
            {send.isError && !(send.error instanceof ApiError && send.error.code === "cancelled") ? <FailureNotice error={send.error} onRetry={() => submit()} canRetry={draft.trim().length > 0} /> : null}
            {rename.error || archive.error || restore.error || proposalAction.error ? <RequestError error={rename.error ?? archive.error ?? restore.error ?? proposalAction.error} /> : null}
            <form
              className="rounded-2xl border border-border bg-card px-4 py-3 shadow-sm"
              onSubmit={(event) => {
                event.preventDefault();
                submit();
              }}
            >
              <Textarea
                aria-label="Message to ATLAS"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    submit();
                  }
                }}
                placeholder="Ask about records, documents or your organization…"
                disabled={send.isPending || create.isPending}
                className="min-h-12 border-0 bg-transparent px-0 py-1 shadow-none focus-visible:ring-0"
              />
              <div className="mt-2 flex items-center justify-between gap-3">
                <p className="text-[10px] uppercase tracking-[0.14em] text-subtle">
                  Enter to send · Shift + Enter for a new line
                </p>
                {send.isPending ? (
                  <Button type="button" variant="outline" className="rounded-[10px]" onClick={() => abortRef.current?.abort()}>Stop</Button>
                ) : (
                  <Button type="submit" className="rounded-[10px]" disabled={create.isPending || draft.trim().length === 0}>Send →</Button>
                )}
              </div>
            </form>
          </div>
        </div>
      </section>
      {panelOpen && focused ? (
        <aside className="hidden w-80 shrink-0 flex-col overflow-y-auto rounded-xl border border-border bg-card xl:flex" aria-label="Supporting sources">
          <div className="flex justify-end border-b border-border px-3 py-2">
            <Button type="button" size="icon" variant="ghost" aria-label="Close sources" onClick={() => setPanelOpen(false)}><X size={16} /></Button>
          </div>
          <SourcePanel source={focused} sources={sources} onSelect={(source) => setFocusSource(sourceKey(source))} />
        </aside>
      ) : null}
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
}) {
  const filtered = (conversations ?? []).filter((item) => item.title.toLowerCase().includes(query.trim().toLowerCase()));
  const customer = filtered.filter((item) => !isEvaluationConversation(item));
  return (
    <div className="flex h-full min-h-0 flex-col p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg text-foreground">Conversations</h2>
        <Button type="button" size="sm" disabled={creating || busy} onClick={onCreate}>
          {creating ? "Starting…" : "New chat"}
        </Button>
      </div>
      <p className="sr-only">Stored for {organizationName}. A new chat takes its title from the first question.</p>
      <Input className="mt-4 h-10 rounded-[10px] border-0 bg-secondary" value={query} onChange={(event) => onQuery(event.target.value)} placeholder="Search conversations…" aria-label="Search conversations" />
      <select aria-label="Conversation retention" className="mt-2 h-10 w-full rounded-[10px] border-0 bg-secondary px-3 text-sm" value={retention} onChange={(event) => onRetention(event.target.value)}>
        <option value="active">Active conversations</option>
        <option value="archived">Archived conversations</option>
      </select>
      {pending ? <Skeleton className="mt-4 h-16 w-full" /> : null}
      {error ? <div className="mt-4"><RequestError error={error} /></div> : null}
      {conversations && customer.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          {query.trim() ? "No conversations match this search." : retention === "archived" ? "No archived conversations." : "No conversations yet."}
        </p>
      ) : null}
      <ul className="mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto">
        {customer.map((conversation) => (
          <ConversationButton
            key={conversation.id}
            conversation={conversation}
            selected={conversation.id === conversationId}
            disabled={creating || busy}
            onOpen={onOpen}
          />
        ))}
      </ul>
    </div>
  );
}

function ConversationButton({
  conversation,
  selected,
  disabled,
  onOpen,
}: {
  conversation: Conversation;
  selected: boolean;
  disabled: boolean;
  onOpen: (id: string) => void;
}) {
  return (
    <li>
      <button
        type="button"
        className={`w-full rounded-[10px] px-3 py-2 text-left transition-colors ${selected ? "bg-accent text-foreground" : "hover:bg-accent/60"}`}
        aria-current={selected ? "true" : undefined}
        disabled={disabled}
        onClick={() => onOpen(conversation.id)}
      >
        <span className="flex items-center gap-2 text-[13px] text-foreground"><MessageSquare size={14} className="shrink-0 text-muted-foreground" /><span className="truncate">{conversation.title}</span></span>
        <span className="mt-1 block text-[10px] text-subtle">{new Date(conversation.updated_at).toLocaleString()}</span>
      </button>
    </li>
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
    "What can you help me with?",
    "What information do you have?",
    "Which companies are in my CRM?",
    "What documents are available?",
    "Summarize the lead ",
    "Draft a follow-up for ",
    "Request an appointment for ",
    "Create a follow-up task for ",
  ];
  return (
    <div className="rounded-xl border border-border bg-card px-4 py-6 text-center sm:px-6 sm:py-8">
      <span className="mx-auto grid size-10 place-items-center rounded-xl bg-primary/10 text-primary"><Sparkles size={19} /></span>
      <h2 className="mt-3 text-lg font-semibold tracking-tight">How can I help?</h2>
      <p className="mt-1 text-sm leading-5 text-muted-foreground">Ask about customer activity or documents in {organizationName}.</p>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="rounded-lg border border-border bg-background px-3 py-2.5 text-left text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:bg-accent hover:text-foreground"
            onClick={() => onPrompt(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

function MessageView({
  message,
  proposalPending,
  onSource,
  onProposal,
  onDismiss,
}: {
  message: ChatMessage;
  proposalPending: boolean;
  onSource: (source: MessageSource) => void;
  onProposal: (proposalId: string, times?: { starts_at: string; ends_at: string }) => void;
  onDismiss: (proposalId: string) => void;
}) {
  const documents = message.sources.filter((source) => source.kind === "document");
  const records = message.sources.filter((source) => source.kind === "crm");
  const refused = message.role === "assistant" && message.content.includes(NO_RECORDS);
  if (message.role === "user") {
    return (
      <article>
        <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">You</p>
        <p className="mt-2 whitespace-pre-wrap rounded-[10px] bg-secondary px-4 py-4 text-[15px] leading-6 text-foreground">{message.content}</p>
      </article>
    );
  }
  return (
    <article>
      <p className="flex items-center gap-2 text-xs font-medium text-primary"><Bot size={16} /> ATLAS Assistant</p>
      {refused ? (
        <div className="mt-3 rounded-[10px] bg-muted px-4 py-3">
          <p className="text-[10px] uppercase tracking-[0.14em] text-subtle">No supporting evidence</p>
          <p className="mt-2 whitespace-pre-wrap text-[15px] leading-7">{message.content}</p>
        </div>
      ) : (
        <div className="mt-3 text-[15px] leading-7 text-muted-foreground">
          <RichText id={message.id} text={message.content} lead />
        </div>
      )}
      {documents.length > 0 ? <SourceList kind="document" sources={documents} onSource={onSource} /> : null}
      {records.length > 0 ? <SourceList kind="crm" sources={records} onSource={onSource} /> : null}
      {message.proposals?.map((proposal) => (
        <ProposalCard key={proposal.id} proposal={proposal} pending={proposalPending} onSubmit={onProposal} onDismiss={onDismiss} />
      ))}
      {documents.length > 0 || records.length > 0 ? (
        <div className="mt-5">
          <p className="text-sm text-muted-foreground">Relevant actions</p>
          <div className="mt-3 flex flex-wrap gap-3">
            {records.map((record) => {
              const href = record.record_id ? crmRecordHref(record) : "/crm";
              return (
                <Link key={`${sourceKey(record)}-action`} href={href} className="rounded-[10px] bg-muted px-4 py-3 text-xs text-primary">
                  View {recordLabel(record)} →
                </Link>
              );
            })}
            {documents.length > 0 ? (
              <Link href="/knowledge" className="rounded-[10px] bg-muted px-4 py-3 text-xs text-primary">
                Browse knowledge →
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function SourceList({
  kind,
  sources,
  onSource,
}: {
  kind: "document" | "crm";
  sources: MessageSource[];
  onSource: (source: MessageSource) => void;
}) {
  const eyebrow = kind === "document" ? "Company knowledge" : "CRM record";
  return (
    <div className="mt-4 flex flex-col gap-2">
      {sources.map((source, index) => (
        <div key={sourceKey(source)} className="rounded-[10px] bg-muted px-4 py-4">
          <p className="text-[11px] uppercase tracking-[0.12em] text-success">
            Source {String(index + 1).padStart(2, "0")} / {eyebrow}
          </p>
          <div className="mt-2 flex items-center justify-between gap-4">
            <p className="min-w-0 truncate text-sm text-foreground">{source.title}</p>
            <button type="button" className="shrink-0 text-xs text-primary" onClick={() => onSource(source)}>
              View exact excerpt →
            </button>
          </div>
          <details className="mt-2">
            <summary className="cursor-pointer text-xs text-muted-foreground">Preview</summary>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{source.excerpt}</p>
          </details>
        </div>
      ))}
    </div>
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
    return { heading: "Model credentials are missing", detail: error.message };
  }
  if (error.code === "llm_rate_limited" || error.code === "embedding_rate_limited") {
    return { heading: "The provider rate limit was reached", detail: error.message };
  }
  if (
    error.code === "llm_unavailable" ||
    error.code === "embedding_unavailable" ||
    error.code === "llm_timeout" ||
    error.code === "embedding_timeout"
  ) {
    return { heading: "The provider is unavailable", detail: error.message };
  }
  if (error.code === "embedding_dimension_mismatch") {
    return { heading: "Search could not use this index", detail: error.message };
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
    return "Document search is unavailable because embeddings are not configured. This answer used CRM records only.";
  }
  if (reply.document_search === "unavailable") {
    return "Document search did not run. The embedding provider was unreachable, refused the request, or the index width does not match. This answer used CRM records only.";
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
    <section className="mt-4 rounded-[10px] border border-border bg-card px-4 py-4">
      <p className="text-[10px] uppercase tracking-[0.14em] text-primary">Proposed action</p>
      <h3 className="mt-2 text-sm font-semibold text-foreground">{proposal.title}</h3>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{proposal.summary}</p>
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
        {href && linkLabel ? <Link href={href} className="rounded-[10px] bg-muted px-4 py-2 text-xs text-primary">{linkLabel} →</Link> : null}
      </div>
    </section>
  );
}
