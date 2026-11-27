"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  Archive,
  ArrowRight,
  Bot,
  Calendar,
  Check,
  ChevronDown,
  CircleStop,
  Copy,
  FileText,
  ListTodo,
  LoaderCircle,
  Mail,
  PanelLeft,
  PanelRight,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { ApiError } from "@/data/client";
import {
  archiveAssistantConversation,
  createAssistantConversation,
  dismissProposal,
  failureMessage,
  getAssistantConversation,
  listAssistantConversations,
  relativeTime,
  renameAssistantConversation,
  restoreAssistantConversation,
  streamAssistantMessage,
  submitProposal,
  type AssistantMessage,
  type AssistantProposal,
  type AssistantReply,
  type AssistantSource,
  type AssistantStep,
} from "@/data/resources";
import { AssistantMarkdown } from "@/presentation/assistant-markdown";
import { Badge, Button, type Tone } from "@/presentation/components";

type ConversationItem = { id: string; title: string; date: string };
type Citation = { key: string; title: string; kind: "document" | "crm"; label: string; excerpts: string[] };

const suggestions = [
  "Who are our customers?",
  "Which leads should I prioritize?",
  "What should I prepare for today's approvals?",
  "Draft a follow-up for a qualified lead",
];

export function AssistantWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const [history, setHistory] = useState<ConversationItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [search, setSearch] = useState("");
  const [retention, setRetention] = useState<"active" | "archived">("active");
  const [renamingId, setRenamingId] = useState("");
  const [renameDraft, setRenameDraft] = useState("");
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingThread, setLoadingThread] = useState(false);
  const [pending, setPending] = useState(false);
  const [streaming, setStreaming] = useState("");
  const [phases, setPhases] = useState<string[]>([]);
  const [failure, setFailure] = useState<unknown>(null);
  const [stoppedNote, setStoppedNote] = useState<string | null>(null);
  const [searchNote, setSearchNote] = useState<string | null>(null);
  const [retryContent, setRetryContent] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [inspection, setInspection] = useState<Citation | null>(null);
  const [copiedId, setCopiedId] = useState("");
  const [proposalPending, setProposalPending] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const turnRef = useRef(0);
  const loadSeq = useRef(0);
  const selectedIdRef = useRef("");
  const threadRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);
  const userScrolling = useRef(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const listSeq = useRef(0);
  const booted = useRef(false);
  const skipRename = useRef(false);
  const renameLock = useRef("");
  const toastRef = useRef(onToast);
  toastRef.current = onToast;

  const selected = history.find((item) => item.id === selectedId);
  const title = selected?.title || "New conversation";
  const lastAssistantId = [...messages].reverse().find((message) => message.role === "assistant")?.id ?? "";

  useEffect(() => {
    const handle = window.setTimeout(() => {
      const seq = ++listSeq.current;
      const query = search.trim();
      listAssistantConversations(query, retention)
        .then((rows) => {
          if (seq !== listSeq.current) return;
          setHistory(rows.map(mapConversation));
          setLoadingList(false);
          if (!booted.current) {
            booted.current = true;
            const first = rows[0];
            if (first) {
              selectedIdRef.current = first.id;
              setSelectedId(first.id);
              void loadThread(first.id);
            }
          }
        })
        .catch((error: unknown) => {
          if (seq !== listSeq.current) return;
          setLoadingList(false);
          toastRef.current(failureMessage(error));
        });
    }, search.trim() ? 250 : 0);
    return () => window.clearTimeout(handle);
  }, [search, retention]);

  useLayoutEffect(() => {
    const composer = composerRef.current;
    if (composer) {
      composer.style.height = "0px";
      composer.style.height = `${Math.min(composer.scrollHeight, 160)}px`;
    }
    const thread = threadRef.current;
    if (thread && stickRef.current) thread.scrollTop = thread.scrollHeight;
  }, [draft, messages, streaming, phases, failure, stoppedNote, loadingThread]);

  useEffect(() => {
    if (!pending) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") abortRef.current?.abort();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending]);

  async function loadThread(id: string) {
    const seq = ++loadSeq.current;
    setLoadingThread(true);
    try {
      const detail = await getAssistantConversation(id);
      if (seq !== loadSeq.current) return;
      setMessages(detail.messages);
      rememberThread(detail);
      setLoadingThread(false);
    } catch (error: unknown) {
      if (seq !== loadSeq.current) return;
      setLoadingThread(false);
      toastRef.current(failureMessage(error));
    }
  }

  function rememberThread(detail: { id: string; title: string; updatedAt: string }) {
    setHistory((current) => current.map((item) => (
      item.id === detail.id
        ? { ...item, title: detail.title || "New conversation", date: relativeTime(detail.updatedAt) || item.date }
        : item
    )));
  }

  function resetTurnView() {
    setStreaming("");
    setPhases([]);
    setFailure(null);
    setStoppedNote(null);
    setSearchNote(null);
    setRetryContent("");
    setInspection(null);
    stickRef.current = true;
  }

  function selectConversation(id: string) {
    setRenamingId("");
    if (id === selectedIdRef.current && !pending) {
      setHistoryOpen(false);
      return;
    }
    turnRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setPending(false);
    resetTurnView();
    setMessages([]);
    selectedIdRef.current = id;
    setSelectedId(id);
    setHistoryOpen(false);
    void loadThread(id);
  }

  function newConversation() {
    void createAssistantConversation()
      .then((created) => {
        turnRef.current += 1;
        abortRef.current?.abort();
        abortRef.current = null;
        setPending(false);
        resetTurnView();
        loadSeq.current += 1;
        setLoadingThread(false);
        setMessages([]);
        setRenamingId("");
        const next = { id: created.id, title: created.title || "New conversation", date: "Now" };
        if (retention !== "active" || search.trim()) {
          setSearch("");
          setRetention("active");
          setHistory([next]);
        } else {
          setHistory((current) => [next, ...current.filter((item) => item.id !== created.id)]);
        }
        selectedIdRef.current = created.id;
        setSelectedId(created.id);
        setDraft("");
        setHistoryOpen(false);
        composerRef.current?.focus();
      })
      .catch((error: unknown) => toastRef.current(failureMessage(error)));
  }

  function startRename(item: ConversationItem) {
    skipRename.current = false;
    setRenamingId(item.id);
    setRenameDraft(item.title);
  }

  function saveRename(id: string) {
    if (skipRename.current) {
      skipRename.current = false;
      return;
    }
    if (renamingId !== id || renameLock.current === id) return;
    const title = renameDraft.trim().replace(/\s+/g, " ");
    const current = history.find((item) => item.id === id)?.title ?? "";
    if (!title || title.length > 200) {
      toastRef.current("Use a title between 1 and 200 characters.");
      return;
    }
    setRenamingId("");
    if (title === current) return;
    renameLock.current = id;
    void renameAssistantConversation(id, title)
      .then((row) => {
        setHistory((items) => items.map((item) => (item.id === id ? { ...item, title: row.title || title } : item)));
      })
      .catch((error: unknown) => toastRef.current(failureMessage(error)))
      .finally(() => {
        if (renameLock.current === id) renameLock.current = "";
      });
  }

  function archiveConversation(id: string) {
    const request = retention === "archived" ? restoreAssistantConversation(id) : archiveAssistantConversation(id);
    void request
      .then(() => {
        const remaining = history.filter((item) => item.id !== id);
        setHistory(remaining);
        setRenamingId((current) => (current === id ? "" : current));
        toastRef.current(retention === "archived" ? "Conversation restored" : "Conversation archived");
        if (selectedIdRef.current !== id) return;
        const fallback = remaining[0];
        if (fallback) selectConversation(fallback.id);
        else {
          turnRef.current += 1;
          abortRef.current?.abort();
          abortRef.current = null;
          setPending(false);
          resetTurnView();
          setMessages([]);
          selectedIdRef.current = "";
          setSelectedId("");
        }
      })
      .catch((error: unknown) => toastRef.current(failureMessage(error)));
  }

  async function send(raw = draft) {
    const content = raw.trim();
    if (!content || content.length > 4000 || pending) return;
    const turn = ++turnRef.current;
    loadSeq.current += 1;
    setDraft("");
    resetTurnView();
    setPending(true);
    setMessages((current) => [...current, localUserMessage(turn, content)]);
    const controller = new AbortController();
    abortRef.current = controller;
    let conversationId = selectedIdRef.current;
    try {
      if (!conversationId) {
        const created = await createAssistantConversation();
        if (turn !== turnRef.current) return;
        conversationId = created.id;
        selectedIdRef.current = created.id;
        setSelectedId(created.id);
        setHistory((current) => [{ id: created.id, title: "New conversation", date: "Now" }, ...current]);
      }
      setHistory((current) => current.map((item) => (
        item.id === conversationId && item.title === "New conversation"
          ? { ...item, title: conversationTitle(content) }
          : item
      )));
      let phase = "";
      const reply = await streamAssistantMessage(
        conversationId,
        content,
        (token) => {
          if (turn !== turnRef.current) return;
          if (phase === "verifying") setStreaming(token);
          else setStreaming((current) => current + token);
        },
        (next) => {
          phase = next;
          if (turn !== turnRef.current) return;
          setPhases((current) => (current.at(-1) === next ? current : [...current, next]));
        },
        controller.signal,
      );
      if (turn !== turnRef.current) return;
      await applyCompletedTurn(turn, conversationId, reply);
    } catch (error: unknown) {
      if (turn !== turnRef.current) return;
      setStreaming("");
      setPhases([]);
      const cancelled = error instanceof ApiError && error.code === "cancelled";
      let savedUser = false;
      let savedAnswer = false;
      if (!conversationId) {
        setMessages((current) => current.filter((message) => message.id !== `local-${turn}`));
      } else {
        try {
          const detail = await getAssistantConversation(conversationId);
          if (turn !== turnRef.current) return;
          setMessages(detail.messages);
          rememberThread(detail);
          const last = detail.messages.at(-1);
          const before = detail.messages.at(-2);
          savedUser = detail.messages.some((message) => message.role === "user" && message.body === content);
          savedAnswer = last?.role === "assistant" && before?.role === "user" && before.body === content;
        } catch {
          if (turn !== turnRef.current) return;
        }
      }
      if (cancelled) {
        setStoppedNote(savedAnswer ? null : "Stopped before the answer was saved.");
        return;
      }
      setFailure(error);
      setRetryContent(content);
      if (!savedUser) setDraft((current) => current || content);
    } finally {
      if (turn === turnRef.current) {
        setPending(false);
        abortRef.current = null;
      }
    }
  }

  async function applyCompletedTurn(turn: number, conversationId: string, reply: AssistantReply) {
    try {
      const detail = await getAssistantConversation(conversationId);
      if (turn !== turnRef.current) return;
      setMessages(detail.messages);
      rememberThread(detail);
    } catch {
      if (turn !== turnRef.current) return;
      setMessages((current) => [...current, reply.message]);
    }
    setStreaming("");
    setPhases([]);
    setSearchNote(searchNotice(reply));
  }

  async function copyAnswer(id: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      window.setTimeout(() => setCopiedId((current) => (current === id ? "" : current)), 1600);
    } catch {
      toastRef.current("Could not copy that answer");
    }
  }

  function replaceProposal(updated: AssistantProposal) {
    setMessages((current) => current.map((message) => ({
      ...message,
      proposals: message.proposals.map((item) => (item.id === updated.id ? updated : item)),
    })));
    toastRef.current(updated.result_label);
  }

  function decideProposal(proposal: AssistantProposal, times?: { starts_at: string; ends_at: string }, dismiss = false) {
    if (!selectedId || proposalPending) return;
    setProposalPending(proposal.id);
    const request = dismiss
      ? dismissProposal(selectedId, proposal.id)
      : submitProposal(selectedId, proposal.id, times);
    void request
      .then((updated) => replaceProposal(updated))
      .catch((error: unknown) => toastRef.current(failureMessage(error)))
      .finally(() => setProposalPending(""));
  }

  function inspect(citation: Citation) {
    setInspection(citation);
    setInspectorOpen(true);
  }

  const canSend = draft.trim().length > 0 && draft.trim().length <= 4000 && !pending;

  return (
    <main className="module-main assistant-main">
      <div className={`assistant-layout${inspectorOpen ? " with-inspector" : ""}`}>
        <aside className={`assistant-history ${historyOpen ? "mobile-open" : ""}`} aria-label="Assistant conversation history">
          <header>
            <div><h2>Assistant</h2><p>Workspace conversations</p></div>
            <Button className="history-close" size="icon" variant="ghost" aria-label="Close conversation history" onClick={() => setHistoryOpen(false)}><X size={16} /></Button>
          </header>
          <Button variant="primary" onClick={newConversation}><Plus size={15} /> New conversation</Button>
          <label className="module-search">
            <Search size={14} />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search conversations" aria-label="Search assistant conversations" />
          </label>
          <div className="assistant-history-list" role="list">
            {loadingList ? <p className="history-status">Loading conversations…</p> : null}
            {!loadingList && history.length ? history.map((conversation) => (
              <div className={`history-row${selectedId === conversation.id ? " active" : ""}${renamingId === conversation.id ? " renaming" : ""}`} key={conversation.id} role="listitem">
                {renamingId === conversation.id ? (
                  <form onSubmit={(event) => { event.preventDefault(); saveRename(conversation.id); }}>
                    <input
                      className="history-rename"
                      value={renameDraft}
                      autoFocus
                      maxLength={200}
                      aria-label="Conversation title"
                      onChange={(event) => setRenameDraft(event.target.value)}
                      onBlur={() => saveRename(conversation.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Escape") {
                          event.preventDefault();
                          skipRename.current = true;
                          setRenamingId("");
                        }
                      }}
                    />
                  </form>
                ) : (
                  <button className="history-open" type="button" onClick={() => selectConversation(conversation.id)}>
                    <strong>{conversation.title}</strong>
                    <small>{conversation.date}</small>
                  </button>
                )}
                {renamingId === conversation.id ? null : (
                  <div className="history-tools">
                    <button className="history-icon" type="button" aria-label={`Rename ${conversation.title}`} onClick={() => startRename(conversation)}><Pencil size={14} /></button>
                    <button className="history-icon" type="button" aria-label={retention === "archived" ? `Restore ${conversation.title}` : `Archive ${conversation.title}`} onClick={() => archiveConversation(conversation.id)}>
                      {retention === "archived" ? <RotateCcw size={14} /> : <Archive size={14} />}
                    </button>
                  </div>
                )}
              </div>
            )) : null}
            {!loadingList && !history.length ? (
              <div className="module-empty compact">
                <Search size={21} />
                <strong>{search.trim() ? "No matching conversations" : retention === "archived" ? "No archived conversations" : "No conversations"}</strong>
                <p>{search.trim() ? "Try a different title." : retention === "archived" ? "Archived conversations appear here." : "Start a conversation to see it here."}</p>
              </div>
            ) : null}
          </div>
          <button className="history-retention" type="button" onClick={() => { setRenamingId(""); setRetention((current) => (current === "active" ? "archived" : "active")); }}>
            {retention === "active" ? "Archived" : "Active conversations"}
          </button>
        </aside>

        <section className="assistant-chat" aria-label={title}>
          <header className="assistant-chat-header">
            <Button className="history-toggle" size="icon" variant="ghost" aria-label="Open conversation history" onClick={() => setHistoryOpen(true)}><PanelLeft size={17} /></Button>
            <div><h1>{title}</h1><p>ATLAS Assistant</p></div>
            <Badge tone="green"><span className="live-dot" /> Available</Badge>
            <Button className={`inspector-toggle${inspectorOpen ? " active" : ""}`} size="icon" variant="ghost" aria-label={inspectorOpen ? "Close context" : "Open context"} aria-pressed={inspectorOpen} onClick={() => setInspectorOpen((open) => !open)}>
              <PanelRight size={17} />
            </Button>
          </header>
          <div
            className="assistant-thread"
            ref={threadRef}
            role="log"
            aria-busy={pending || loadingThread}
            onWheel={() => { userScrolling.current = true; }}
            onTouchMove={() => { userScrolling.current = true; }}
            onPointerDown={() => { userScrolling.current = true; }}
            onScroll={() => {
              if (!userScrolling.current) return;
              const node = threadRef.current;
              if (!node) return;
              stickRef.current = node.scrollHeight - node.scrollTop - node.clientHeight < 96;
            }}
          >
            {!messages.length && !pending && !loadingThread && !loadingList ? <AssistantWelcome onSelect={(value) => { setDraft(value); composerRef.current?.focus(); }} /> : null}
            {loadingList || (loadingThread && !messages.length) ? <p className="history-status">Loading conversation…</p> : null}
            {messages.map((message) => message.role === "user" ? (
              <article className="turn turn-user" key={message.id} aria-label="You"><p>{message.body}</p></article>
            ) : (
              <AssistantAnswer
                key={message.id}
                message={message}
                copied={copiedId === message.id}
                canRetry={!pending && !failure && message.id === lastAssistantId}
                proposalPending={proposalPending}
                inspectorOpen={inspectorOpen}
                activeCitation={inspection?.key ?? ""}
                onCopy={() => void copyAnswer(message.id, message.body)}
                onRetry={() => {
                  const question = previousQuestion(messages, message.id);
                  if (question) void send(question);
                }}
                onInspect={inspect}
                onSubmit={(proposal, times) => decideProposal(proposal, times)}
                onDismiss={(proposal) => decideProposal(proposal, undefined, true)}
              />
            ))}
            {pending ? (
              <article className="turn turn-assistant" aria-live="polite" aria-label="ATLAS Assistant">
                <span className="assistant-avatar" aria-hidden="true"><Bot size={16} /></span>
                <div className="turn-body">
                  <LiveProgress phases={phases} writing={streaming.length > 0} />
                  {streaming ? <AssistantMarkdown id="streaming" text={streaming} streaming /> : null}
                </div>
              </article>
            ) : null}
            {stoppedNote ? <p className="answer-note">{stoppedNote}</p> : null}
            {searchNote && !failure ? <p className="answer-note">{searchNote}</p> : null}
            {failure ? <FailureNotice error={failure} canRetry={retryContent.trim().length > 0 && !pending} onRetry={() => void send(retryContent)} /> : null}
          </div>
          <div className="assistant-composer-slot">
            <form className="assistant-composer" onSubmit={(event) => { event.preventDefault(); void send(); }}>
              <textarea
                ref={composerRef}
                value={draft}
                rows={1}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                    event.preventDefault();
                    void send();
                  }
                }}
                placeholder="Ask about customers, work, or knowledge…"
                aria-label="Ask ATLAS Assistant"
              />
              <div className="composer-end">
                {draft.length > 3200 ? <b>{draft.length}/4000</b> : null}
                {pending ? (
                  <button className="composer-action stop" type="button" aria-label="Stop generation" onClick={() => abortRef.current?.abort()}><CircleStop size={16} /></button>
                ) : (
                  <button className="composer-action" type="submit" disabled={!canSend} aria-label="Send question"><Send size={15} /></button>
                )}
              </div>
            </form>
          </div>
        </section>

        {inspectorOpen ? <button className="inspector-backdrop" type="button" aria-label="Close context" onClick={() => setInspectorOpen(false)} /> : null}
        <aside className="assistant-context" aria-label="Context" hidden={!inspectorOpen}>
          <header>
            <h2>Context</h2>
            <Button size="icon" variant="ghost" aria-label="Close context" onClick={() => setInspectorOpen(false)}><X size={16} /></Button>
          </header>
          <div className="assistant-context-content">
            {inspection ? <Inspection citation={inspection} /> : (
              <div className="context-note"><FileText size={15} /><p><strong>No source selected</strong><small>Open a citation when you want the supporting passage or record.</small></p></div>
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}

function AssistantWelcome({ onSelect }: { onSelect: (value: string) => void }) {
  return (
    <div className="assistant-welcome">
      <span className="assistant-logo"><Sparkles size={22} /></span>
      <h2>How can I help?</h2>
      <p>Ask about customer activity, open work, or trusted knowledge.</p>
      <div>{suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => onSelect(suggestion)}>{suggestion}<ArrowRight size={14} /></button>)}</div>
    </div>
  );
}

function AssistantAnswer({
  message,
  copied,
  canRetry,
  proposalPending,
  inspectorOpen,
  activeCitation,
  onCopy,
  onRetry,
  onInspect,
  onSubmit,
  onDismiss,
}: {
  message: AssistantMessage;
  copied: boolean;
  canRetry: boolean;
  proposalPending: string;
  inspectorOpen: boolean;
  activeCitation: string;
  onCopy: () => void;
  onRetry: () => void;
  onInspect: (citation: Citation) => void;
  onSubmit: (proposal: AssistantProposal, times?: { starts_at: string; ends_at: string }) => void;
  onDismiss: (proposal: AssistantProposal) => void;
}) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [stepsOpen, setStepsOpen] = useState(false);
  const citations = citationsFor(message.sources);
  const cards = usefulRecords(message.body, citations);
  const cardKeys = new Set(cards.map((item) => item.key));
  const listed = citations.filter((item) => !cardKeys.has(item.key));
  const knowledge = listed.filter((item) => item.kind === "document");
  const records = listed.filter((item) => item.kind === "crm");
  const steps = visibleSteps(message.steps);
  return (
    <article className="turn turn-assistant" aria-label="ATLAS Assistant">
      <span className="assistant-avatar" aria-hidden="true"><Bot size={16} /></span>
      <div className="turn-body">
        {steps.length ? <ToolProgress steps={steps} open={stepsOpen} onToggle={() => setStepsOpen((open) => !open)} /> : null}
        <AssistantMarkdown id={message.id} text={message.body} />
        {cards.length ? (
          <div className="record-row">
            {cards.map((citation) => (
              <button className={activeCitation === citation.key ? "record-card active" : "record-card"} key={citation.key} type="button" onClick={() => onInspect(citation)}>
                <strong>{citation.title}</strong>
                <small>{citation.label}</small>
              </button>
            ))}
          </div>
        ) : null}
        {listed.length ? (
          <div className="source-block">
            {!sourcesOpen ? (
              <div className="cite-row">
                {listed.slice(0, listed.length > 4 ? 3 : listed.length).map((citation, index) => (
                  <button className={activeCitation === citation.key ? "cite-chip active" : "cite-chip"} key={citation.key} type="button" onClick={() => onInspect(citation)}>
                    <b>{index + 1}</b>
                    <span>{citation.title}</span>
                  </button>
                ))}
                {listed.length > 4 ? <button className="cite-chip more" type="button" onClick={() => setSourcesOpen(true)}>+{listed.length - 3} sources</button> : null}
              </div>
            ) : null}
            <button className="source-toggle" type="button" aria-expanded={sourcesOpen} onClick={() => setSourcesOpen((open) => !open)}>
              <FileText size={14} /> {listed.length} {listed.length === 1 ? "source" : "sources"}
              <ChevronDown size={14} className={sourcesOpen ? "rotate-180" : ""} />
            </button>
            {sourcesOpen ? (
              <div className="source-groups">
                {knowledge.length ? <SourceGroup title="Knowledge" items={knowledge} activeKey={activeCitation} inspectorOpen={inspectorOpen} onInspect={onInspect} /> : null}
                {records.length ? <SourceGroup title="Records" items={records} activeKey={activeCitation} inspectorOpen={inspectorOpen} onInspect={onInspect} /> : null}
              </div>
            ) : null}
          </div>
        ) : null}
        {message.proposals.map((proposal) => (
          <ActionCard key={proposal.id} proposal={proposal} pending={proposalPending === proposal.id} onSubmit={onSubmit} onDismiss={onDismiss} />
        ))}
        <div className="turn-actions">
          <Button size="sm" variant="ghost" aria-label={copied ? "Copied answer" : "Copy answer"} onClick={onCopy}>{copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "Copied" : "Copy"}</Button>
          {canRetry ? <Button size="sm" variant="ghost" onClick={onRetry}><RefreshCw size={13} /> Retry</Button> : null}
        </div>
      </div>
    </article>
  );
}

function SourceGroup({
  title,
  items,
  activeKey,
  inspectorOpen,
  onInspect,
}: {
  title: string;
  items: Citation[];
  activeKey: string;
  inspectorOpen: boolean;
  onInspect: (citation: Citation) => void;
}) {
  return (
    <section className="source-group">
      <h3>{title}</h3>
      {items.map((item) => {
        const showingElsewhere = inspectorOpen && activeKey === item.key;
        return (
          <details key={item.key}>
            <summary><span>{item.title}</span><small>{item.label}</small></summary>
            {showingElsewhere ? <p>Showing in context.</p> : item.excerpts.map((excerpt, index) => <p key={index}>{excerpt}</p>)}
            <button type="button" onClick={() => onInspect(item)}>Open in context <ArrowRight size={12} /></button>
          </details>
        );
      })}
    </section>
  );
}

function ToolProgress({ steps, open, onToggle }: { steps: AssistantStep[]; open: boolean; onToggle: () => void }) {
  const labels = progressLabels(steps);
  return (
    <div className="tool-progress">
      <button type="button" aria-expanded={open} onClick={onToggle}>
        <Check size={13} />
        <span>{labels.join(" · ")}</span>
        <small>{open ? "Hide" : "Details"}</small>
      </button>
      {open ? (
        <ol>
          {steps.map((step, index) => {
            const note = stepNote(step);
            return (
              <li key={`${step.tool_name}-${index}`}>
                <strong>{toolLabel(step.tool_name)}</strong>
                <small>{stepStatus(step.status)} · {durationLabel(step.duration_ms)}</small>
                {note ? <p>{note}</p> : null}
              </li>
            );
          })}
        </ol>
      ) : null}
    </div>
  );
}

function LiveProgress({ phases, writing }: { phases: string[]; writing: boolean }) {
  const labels = uniquePhaseLabels(phases);
  const lookups = labels.filter((label) => label !== "Writing the answer");
  if (writing) {
    return <p className="live-progress-summary"><LoaderCircle className="spinning" size={14} /> {lookups.length ? lookups.join(" · ") : "Writing the answer"}</p>;
  }
  const shown = labels.length ? labels : ["Preparing your answer"];
  return (
    <ol className="live-progress">
      {shown.map((label, index) => {
        const current = index === shown.length - 1;
        return <li key={label} className={current ? "current" : "done"}>{current ? <LoaderCircle className="spinning" size={14} /> : <Check size={14} />}<span>{label}</span></li>;
      })}
    </ol>
  );
}

function ActionCard({
  proposal,
  pending,
  onSubmit,
  onDismiss,
}: {
  proposal: AssistantProposal;
  pending: boolean;
  onSubmit: (proposal: AssistantProposal, times?: { starts_at: string; ends_at: string }) => void;
  onDismiss: (proposal: AssistantProposal) => void;
}) {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const badge = statusBadge(proposal);
  const appointment = proposal.kind === "appointment";
  const validTime = !appointment || (Boolean(start && end) && Date.parse(start) < Date.parse(end));
  const Icon = proposal.kind === "appointment" ? Calendar : proposal.kind === "task" ? ListTodo : Mail;
  return (
    <section className={`action-card ${actionClass(proposal)}`}>
      <header>
        <span className="action-icon" aria-hidden="true"><Icon size={16} /></span>
        <div>
          <span>{kindLabel(proposal.kind)}</span>
          <h3>{proposal.title}</h3>
        </div>
        <Badge tone={badge.tone}>{badge.label}</Badge>
      </header>
      {proposal.summary ? <p className={proposal.kind === "follow_up" ? "action-draft" : ""}>{proposal.summary}</p> : null}
      {proposal.status === "proposed" && appointment ? (
        <div className="field-row">
          <label className="field"><span>Starts</span><input type="datetime-local" value={start} onChange={(event) => setStart(event.target.value)} /></label>
          <label className="field"><span>Ends</span><input type="datetime-local" value={end} onChange={(event) => setEnd(event.target.value)} /></label>
        </div>
      ) : null}
      {proposal.status === "proposed" && appointment && start && end && !validTime ? <p className="action-warning">Choose an end time after the start.</p> : null}
      {proposal.result_label ? <p className="action-result">{proposal.result_label}</p> : null}
      {proposal.status === "proposed" ? (
        <div className="actions">
          <Button size="sm" variant="primary" disabled={pending || !validTime} onClick={() => onSubmit(proposal, appointment ? { starts_at: new Date(start).toISOString(), ends_at: new Date(end).toISOString() } : undefined)}>
            {pending ? "Saving…" : submitLabel(proposal.kind)}
          </Button>
          <Button size="sm" variant="ghost" disabled={pending} onClick={() => onDismiss(proposal)}>Dismiss</Button>
        </div>
      ) : null}
    </section>
  );
}

function Inspection({ citation }: { citation: Citation }) {
  return (
    <article className="inspection">
      <span>{citation.kind === "document" ? "Knowledge" : citation.label}</span>
      <h3>{citation.title}</h3>
      {citation.excerpts.length ? citation.excerpts.map((excerpt, index) => <p key={index}>{excerpt}</p>) : <p>No preview is stored for this source.</p>}
    </article>
  );
}

function FailureNotice({ error, canRetry, onRetry }: { error: unknown; canRetry: boolean; onRetry: () => void }) {
  const copy = failureCopy(error);
  return (
    <div className="answer-alert" role="alert">
      <h2>{copy.heading}</h2>
      <p>{copy.detail}</p>
      {copy.raw && copy.raw !== copy.detail ? (
        <details className="answer-details">
          <summary>Details</summary>
          <p>{copy.raw}</p>
        </details>
      ) : null}
      {canRetry ? <Button size="sm" onClick={onRetry}><RefreshCw size={13} /> Retry</Button> : null}
    </div>
  );
}

function localUserMessage(turn: number, body: string): AssistantMessage {
  return { id: `local-${turn}`, role: "user", body, sources: [], proposals: [], steps: [] };
}

function mapConversation(row: { id: string; title: string; updated_at: string }): ConversationItem {
  return { id: row.id, title: row.title || "Conversation", date: relativeTime(row.updated_at) || row.updated_at.slice(0, 10) };
}

function conversationTitle(content: string): string {
  const collapsed = content.split(/\s+/).filter(Boolean).join(" ");
  if (!collapsed) return "New conversation";
  if (collapsed.length <= 72) return collapsed;
  let shortened = collapsed.slice(0, 72).replace(/\s+\S*$/, "").replace(/[.,;:!?]+$/, "");
  if (shortened.length < 12) shortened = collapsed.slice(0, 72).trimEnd();
  return shortened;
}

function previousQuestion(messages: AssistantMessage[], assistantId: string): string {
  const index = messages.findIndex((message) => message.id === assistantId);
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    if (messages[cursor]?.role === "user") return messages[cursor].body;
  }
  return "";
}

function citationsFor(sources: AssistantSource[]): Citation[] {
  const groups = new Map<string, Citation & { pages: number[] }>();
  for (const source of sources) {
    const key = source.kind === "document" ? `document:${source.document_id || source.title}` : `crm:${source.record_id || source.title}`;
    const excerpt = (source.excerpt || "").trim();
    const current = groups.get(key);
    if (current) {
      if (excerpt && !current.excerpts.includes(excerpt)) current.excerpts.push(excerpt);
      if (source.page_number) current.pages.push(source.page_number);
      continue;
    }
    groups.set(key, {
      key,
      title: source.title,
      kind: source.kind === "crm" ? "crm" : "document",
      label: source.kind === "document" ? "Knowledge" : recordLabel(source.record_type),
      excerpts: excerpt ? [excerpt] : [],
      pages: source.page_number ? [source.page_number] : [],
    });
  }
  return [...groups.values()].map((group) => ({
    key: group.key,
    title: group.title,
    kind: group.kind,
    label: group.kind === "document" ? pageMeta(group.pages) : group.label,
    excerpts: group.excerpts,
  }));
}

function usefulRecords(body: string, citations: Citation[]): Citation[] {
  const records = citations.filter((item) => item.kind === "crm");
  if (!records.length || records.length > 3) return [];
  const analytical = /(^|\n)\s*#{1,3}\s|\n\|/.test(body);
  if (analytical) return records;
  const folded = body.toLowerCase();
  const unnamed = records.filter((record) => !folded.includes(record.title.toLowerCase()));
  if (body.trim().length > 320 && unnamed.length) return unnamed;
  return [];
}

function pageMeta(pages: number[]): string {
  const unique = [...new Set(pages)];
  if (unique.length === 1) return `Page ${unique[0]}`;
  if (unique.length > 1) return `Pages ${unique.slice(0, 3).join(", ")}`;
  return "Knowledge";
}

function recordLabel(recordType: string | null | undefined): string {
  if (recordType === "company") return "Company";
  if (recordType === "contact") return "Contact";
  if (recordType === "inquiry") return "Inquiry";
  if (recordType === "conversation") return "Conversation";
  if (recordType === "lead") return "Lead";
  if (recordType === "task") return "Task";
  return "Record";
}

function visibleSteps(steps: AssistantStep[]): AssistantStep[] {
  return steps.filter((step) => {
    const name = step.tool_name.toLowerCase();
    if (name.includes("reason") || name.includes("think") || name === "respond" || name === "clarify") return step.status === "failed";
    return true;
  });
}

function progressLabels(steps: AssistantStep[]): string[] {
  const labels: string[] = [];
  for (const step of steps) {
    const label = toolLabel(step.tool_name);
    if (labels.at(-1) !== label) labels.push(label);
  }
  if (steps.some((step) => step.status === "failed") && labels.at(-1) !== "Needs attention") labels.push("Needs attention");
  return labels;
}

function toolLabel(tool: string): string {
  const labels: Record<string, string> = {
    search_knowledge: "Searching company knowledge",
    search_company_knowledge: "Searching company knowledge",
    list_companies: "Reviewing customer records",
    list_contacts: "Reviewing customer records",
    list_leads: "Reviewing customer records",
    list_members: "Reviewing workspace members",
    list_opportunities: "Reviewing the pipeline",
    list_tasks: "Reviewing tasks",
    search_inbox: "Reviewing the inbox",
    business_analytics: "Reviewing business activity",
    check_availability: "Checking calendar availability",
    list_workflow_runs: "Reviewing workflow runs",
    draft_customer_message: "Preparing a follow-up",
    propose_appointment: "Preparing your appointment",
    propose_task: "Preparing a task",
  };
  return labels[tool] ?? "Checking workspace records";
}

function stepStatus(status: AssistantStep["status"]): string {
  if (status === "failed") return "Needs attention";
  if (status === "recovered") return "Continued";
  return "Completed";
}

function stepNote(step: AssistantStep): string {
  const detail = step.detail.trim();
  if (!detail || detail === "Answered without a workspace lookup") return "";
  return detail;
}

function durationLabel(durationMs: number): string {
  if (durationMs < 1000) return `${durationMs} ms`;
  return `${(durationMs / 1000).toFixed(1)} s`;
}

function uniquePhaseLabels(phases: string[]): string[] {
  const labels: string[] = [];
  for (const phase of phases) {
    const label = phaseLabel(phase);
    if (label && labels.at(-1) !== label) labels.push(label);
  }
  return labels;
}

function phaseLabel(phase: string): string | null {
  if (phase === "preparing") return "Preparing your answer";
  if (phase === "selecting_tools") return "Choosing what to check";
  if (phase === "searching_crm") return "Reviewing customer records";
  if (phase === "retrieving_documents") return "Searching company knowledge";
  if (phase === "verifying") return "Checking the answer against company records";
  if (phase === "streaming") return "Writing the answer";
  return null;
}

function searchNotice(reply: AssistantReply): string | null {
  if (reply.document_search === "unconfigured") return "Document search is not set up yet. This answer used customer records only.";
  if (reply.document_search === "unavailable") return "Document search did not run, so this answer used customer records only.";
  if (reply.document_search === "empty" && reply.message.sources.every((source) => source.kind !== "document")) return "No company document matched this question.";
  return null;
}

function statusBadge(proposal: AssistantProposal): { label: string; tone: Tone } {
  if (proposal.status === "dismissed") return { label: "Dismissed", tone: "neutral" };
  if (proposal.approval_status === "rejected") return { label: "Not approved", tone: "red" };
  if (proposal.approval_status === "executed") return { label: "Completed", tone: "green" };
  if (proposal.approval_status === "failed" || proposal.approval_status === "needs_attention") return { label: "Needs attention", tone: "red" };
  if (proposal.kind === "task" && proposal.task_id) return { label: "Created", tone: "green" };
  if (proposal.status === "submitted" || proposal.approval_status === "pending") return { label: "Waiting for approval", tone: "amber" };
  return { label: "Ready to review", tone: "amber" };
}

function actionClass(proposal: AssistantProposal): string {
  const badge = statusBadge(proposal);
  if (badge.tone === "green") return "done";
  if (badge.tone === "red") return "failed";
  if (badge.label === "Waiting for approval") return "waiting";
  if (badge.label === "Dismissed") return "muted";
  return "proposed";
}

function kindLabel(kind: AssistantProposal["kind"]): string {
  if (kind === "appointment") return "Appointment";
  if (kind === "task") return "Task";
  return "Follow-up";
}

function submitLabel(kind: AssistantProposal["kind"]): string {
  if (kind === "task") return "Create task";
  if (kind === "appointment") return "Submit appointment";
  return "Submit follow-up";
}

function failureCopy(error: unknown): { heading: string; detail: string; raw: string } {
  const raw = error instanceof Error ? error.message : "Request failed";
  if (!(error instanceof ApiError)) {
    return { heading: "The reply did not finish", detail: "The assistant could not complete that reply.", raw };
  }
  if (error.code === "llm_unconfigured" || error.code === "embedding_unconfigured") {
    return { heading: "The assistant is not connected yet", detail: "An administrator needs to connect a language model before answers can be generated.", raw };
  }
  if (error.code === "llm_rate_limited" || error.code === "embedding_rate_limited") {
    return { heading: "The assistant is busy", detail: "Too many requests were sent. Wait a moment and try again.", raw };
  }
  if (error.code === "llm_unavailable" || error.code === "embedding_unavailable" || error.code === "llm_timeout" || error.code === "embedding_timeout") {
    return { heading: "The assistant is unavailable", detail: "The language service did not respond. Try again in a moment.", raw };
  }
  if (error.code === "embedding_dimension_mismatch") {
    return { heading: "Document search needs to be rebuilt", detail: "The document index does not match the current search setup.", raw };
  }
  if (error.status === 403 || error.code === "forbidden") {
    return { heading: "Permission denied", detail: "You do not have access to that conversation.", raw };
  }
  if (error.status === 404 || error.code === "not_found") {
    return { heading: "Conversation unavailable", detail: "That conversation is no longer available in this workspace.", raw };
  }
  return { heading: "The reply did not finish", detail: "The assistant could not complete that reply.", raw };
}
