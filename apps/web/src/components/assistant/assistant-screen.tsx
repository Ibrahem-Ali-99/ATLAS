"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { createConversation, getConversation, listConversations, streamConversationMessage } from "@/lib/records-api";
import type { AssistantReply, ChatMessage, MessageSource } from "@/lib/records";
import { useWorkspace } from "@/lib/use-workspace";

export function AssistantScreen() {
  const { organizationId, organizationName } = useWorkspace();
  if (!organizationId) {
    return null;
  }
  return (
    <AssistantWorkspace organizationId={organizationId} organizationName={organizationName ?? "this organization"} />
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
  const [streaming, setStreaming] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const conversations = useQuery({
    queryKey: ["conversations", organizationId],
    queryFn: () => listConversations(organizationId),
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
      router.replace(`/assistant?conversation=${conversation.id}`);
    },
  });
  const send = useMutation({
    mutationFn: async (content: string) => {
      if (!conversationId) {
        throw new Error("Start a conversation first.");
      }
      setStreaming("");
      setNotice(null);
      return streamConversationMessage(organizationId, conversationId, content, (token) => {
        setStreaming((current) => current + token);
      });
    },
    onSuccess: async (reply) => {
      setDraft("");
      setStreaming("");
      setNotice(searchNotice(reply));
      await queryClient.invalidateQueries({ queryKey: ["conversation", organizationId, conversationId] });
      await queryClient.invalidateQueries({ queryKey: ["conversations", organizationId] });
    },
    onError: async () => {
      setStreaming("");
      await queryClient.invalidateQueries({ queryKey: ["conversation", organizationId, conversationId] });
    },
  });

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
      <PageHeader title="AI Assistant">
        Answers use stored documents and CRM records for {organizationName}. A citation is a retrieved row, not a phrase taken from the model text.
      </PageHeader>
      <div className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
      <aside className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Conversations</h2>
          <Button type="button" size="sm" disabled={create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? "Starting…" : "New"}
          </Button>
        </div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">History is stored for {organizationName} and stays after refresh.</p>
        {conversations.isPending ? <Skeleton className="mt-4 h-16 w-full" /> : null}
        {conversations.isError ? <div className="mt-4"><RequestError error={conversations.error} /></div> : null}
        {create.isError ? <div className="mt-4"><RequestError error={create.error} /></div> : null}
        {conversations.data && conversations.data.length === 0 ? (
          <p className="mt-4 text-sm text-muted-foreground">No conversations yet.</p>
        ) : null}
        <ul className="mt-4 space-y-1">
          {conversations.data?.map((conversation) => (
            <li key={conversation.id}>
              <button
                type="button"
                className={`w-full rounded-md px-2 py-2 text-left text-sm ${conversation.id === conversationId ? "bg-accent" : "hover:bg-accent/50"}`}
                onClick={() => router.replace(`/assistant?conversation=${conversation.id}`)}
              >
                <span className="block truncate font-medium">{conversation.title}</span>
                <span className="mt-1 block text-xs text-muted-foreground">{new Date(conversation.updated_at).toLocaleString()}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <section className="flex min-h-[32rem] flex-col rounded-xl border border-border bg-card">
        {!conversationId ? (
          <div className="p-6">
            <p className="text-sm font-medium">No conversation is open</p>
            <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
              Start one, then ask about a document you uploaded or a CRM record in this organization. The answer stays in this conversation after you refresh.
            </p>
          </div>
        ) : null}
        {detail.isPending && conversationId ? <div className="space-y-3 p-6"><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-2/3" /></div> : null}
        {detail.isError ? <div className="p-6"><RequestError error={detail.error} /></div> : null}
        <div className="flex-1 space-y-4 p-6">
          {detail.data?.messages.map((message) => <MessageView key={message.id} message={message} />)}
          {send.isPending ? (
            <article className="rounded-lg border border-border p-4 text-sm">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Assistant</p>
              <p className="mt-2 whitespace-pre-wrap">{streaming || "Looking through company records…"}</p>
            </article>
          ) : null}
        </div>
        {notice ? <p className="px-6 text-sm text-muted-foreground">{notice}</p> : null}
        {send.isError ? <div className="px-6"><RequestError error={send.error} /></div> : null}
        <form
          className="grid gap-3 border-t border-border p-4"
          onSubmit={(event) => {
            event.preventDefault();
            const content = draft.trim();
            if (content && conversationId) {
              send.mutate(content);
            }
          }}
        >
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask about a document or a CRM record"
            disabled={!conversationId || send.isPending}
          />
          <div className="flex justify-end">
            <Button type="submit" disabled={!conversationId || send.isPending || draft.trim().length === 0}>
              {send.isPending ? "Answering…" : "Send"}
            </Button>
          </div>
        </form>
      </section>
      </div>
    </div>
  );
}

function searchNotice(reply: AssistantReply): string | null {
  if (reply.document_search === "unconfigured") {
    return "Document search is unavailable because embeddings are not configured. This answer used CRM records only.";
  }
  if (reply.document_search === "empty" && reply.message.sources.every((source) => source.kind !== "document")) {
    return "No company document matched this question.";
  }
  return null;
}

function MessageView({ message }: { message: ChatMessage }) {
  const documents = message.sources.filter((source) => source.kind === "document");
  const records = message.sources.filter((source) => source.kind === "crm");
  return (
    <article
      className={
        message.role === "user"
          ? "ml-auto max-w-[40rem] rounded-lg bg-accent px-4 py-3 text-sm"
          : "max-w-[40rem] rounded-lg border border-border bg-background px-4 py-3 text-sm"
      }
    >
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {message.role === "user" ? "You" : "Assistant"}
      </p>
      <p className="mt-2 whitespace-pre-wrap leading-6">{message.content}</p>
      {documents.length > 0 ? <SourceList label="Company documents" sources={documents} /> : null}
      {records.length > 0 ? <SourceList label="CRM records" sources={records} /> : null}
    </article>
  );
}

function SourceList({ label, sources }: { label: string; sources: MessageSource[] }) {
  return (
    <div className="mt-3 space-y-2">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      {sources.map((source) => (
        <div key={`${source.kind}-${source.chunk_id ?? source.record_id ?? source.title}`} className="rounded-md bg-background p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{source.kind === "document" ? "Document" : source.record_type ?? "CRM"}</Badge>
            <span className="font-medium">{source.title}</span>
            {source.page_number !== null ? <span className="text-xs text-muted-foreground">page {source.page_number}</span> : null}
          </div>
          <p className="mt-2 whitespace-pre-wrap text-muted-foreground">{source.excerpt}</p>
        </div>
      ))}
    </div>
  );
}
