import { useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  Bot,
  Building2,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleStop,
  Clock3,
  Code2,
  FileText,
  LoaderCircle,
  PanelLeft,
  Plus,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  Target,
  UserRound,
  WifiOff,
  X,
} from "lucide-react";
import { appConfig } from "./appConfig";
import { Avatar, Badge, Button } from "./components";

type AssistantConversation = {
  id: number;
  title: string;
  date: string;
  state?: "provider-error" | "insufficient";
};

const initialHistory: AssistantConversation[] = [
  { id: 1, title: "Which leads need attention?", date: "Today" },
  { id: 2, title: "Summarize the Northstar account", date: "Today" },
  { id: 3, title: "Prepare customer follow-ups", date: "Yesterday" },
  { id: 4, title: "Provider availability check", date: "Yesterday", state: "provider-error" },
  { id: 5, title: "Legacy policy question", date: "Feb 20", state: "insufficient" },
];

type ChatMessage = { id: number; role: "user" | "assistant"; body: string };

function useAssistantModel(onToast: (message: string) => void) {
  const [history, setHistory] = useState(initialHistory);
  const [selectedId, setSelectedId] = useState(1);
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: 1, role: "user", body: "Which leads need attention today?" },
    { id: 2, role: "assistant", body: "Three leads need attention based on recent activity and open work." },
  ]);
  const selected = history.find((item) => item.id === selectedId) || history[0];
  const filtered = useMemo(() => history.filter((item) => item.title.toLowerCase().includes(search.toLowerCase())), [history, search]);
  const select = (id: number) => {
    setSelectedId(id);
    setStreaming(false);
    const item = history.find((entry) => entry.id === id);
    setMessages(item?.state ? [] : [
      { id: 1, role: "user", body: item?.title || "" },
      { id: 2, role: "assistant", body: id === 2 ? "Northstar is an active customer with a qualified opportunity and a pending custom terms review." : "Three leads need attention based on recent activity and open work." },
    ]);
  };
  const newConversation = () => {
    const next = { id: Date.now(), title: "New conversation", date: "Now" };
    setHistory([next, ...history]);
    setSelectedId(next.id);
    setMessages([]);
    setDraft("");
  };
  const send = () => {
    if (!draft.trim() || streaming) return;
    const question = draft.trim();
    setMessages((current) => [...current, { id: Date.now(), role: "user", body: question }]);
    setDraft("");
    setStreaming(true);
    window.setTimeout(() => {
      setMessages((current) => [...current, { id: Date.now() + 1, role: "assistant", body: "I found relevant customer records and knowledge sources. Here is a concise operational summary." }]);
      setStreaming(false);
      setHistory((current) => current.map((item) => item.id === selectedId ? { ...item, title: item.title === "New conversation" ? question : item.title } : item));
      onToast("Assistant response completed");
    }, 900);
  };
  return { history, filtered, selected, selectedId, search, setSearch, draft, setDraft, streaming, setStreaming, messages, select, newConversation, send };
}

export function AssistantWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const model = useAssistantModel(onToast);
  const [historyOpen, setHistoryOpen] = useState(false);
  const suggestions = ["Which open inquiries are waiting on us?", "Summarize recent activity for Arcade", "What should I prepare for today’s approvals?"];
  return (
    <main className="module-main assistant-main">
      <div className="assistant-layout">
        <aside className={`assistant-history ${historyOpen ? "mobile-open" : ""}`} aria-label="Assistant conversation history">
          <header><div><h2>Assistant</h2><p>Workspace conversations</p></div><Button className="history-close" size="icon" variant="ghost" aria-label="Close conversation history" onClick={() => setHistoryOpen(false)}><X size={16} /></Button></header>
          <Button variant="primary" onClick={model.newConversation}><Plus size={15} /> New conversation</Button>
          <label className="module-search"><Search size={14} /><input value={model.search} onChange={(event) => model.setSearch(event.target.value)} placeholder="Search conversations" aria-label="Search assistant conversations" /></label>
          <div className="assistant-history-list">
            {model.filtered.length ? model.filtered.map((conversation) => <button className={model.selectedId === conversation.id ? "active" : ""} key={conversation.id} onClick={() => { model.select(conversation.id); setHistoryOpen(false); }}><span><Bot size={14} /><strong>{conversation.title}</strong></span><small>{conversation.date}</small></button>) : <div className="module-empty compact"><Search size={21} /><strong>No conversations</strong><p>Try a different search.</p></div>}
          </div>
          <div className="assistant-privacy"><Sparkles size={14} /><p><strong>Grounded in your workspace</strong><small>Answers cite accessible CRM and knowledge records.</small></p></div>
        </aside>

        <section className="assistant-chat" aria-label={model.selected.title}>
          <header className="assistant-chat-header"><Button className="history-toggle" size="icon" variant="ghost" aria-label="Open conversation history" onClick={() => setHistoryOpen(true)}><PanelLeft size={17} /></Button><div><h1>{model.selected.title}</h1><p>ATLAS Assistant · Sources enabled</p></div><Badge tone="green"><span className="live-dot" /> Available</Badge></header>
          <div className="assistant-thread">
            {!model.messages.length && !model.selected.state && <AssistantWelcome suggestions={suggestions} onSelect={model.setDraft} />}
            {model.selected.state === "provider-error" && <div className="assistant-state error"><WifiOff size={24} /><h2>Assistant provider unavailable</h2><p>The response provider could not be reached. Your conversation history is safe.</p><Button onClick={() => { model.select(1); onToast("Provider connection restored"); }}><RefreshCw size={14} /> Retry connection</Button></div>}
            {model.selected.state === "insufficient" && <div className="assistant-state"><FileText size={24} /><h2>Insufficient knowledge</h2><p>ATLAS could not find enough trusted information to answer this question. Add relevant documents or provide more context.</p><Button onClick={() => onToast("Opening Knowledge")}>Review knowledge sources <ArrowRight size={14} /></Button></div>}
            {model.messages.map((message, index) => message.role === "user" ? <article className="assistant-message user" key={message.id}><Avatar initials={appConfig.user.initials} tone="blue" /><div><strong>{appConfig.user.name}</strong><p>{message.body}</p></div></article> : <AssistantResponse key={message.id} compact={model.selected.id === 2 || index > 2} onToast={onToast} />)}
            {model.streaming && <article className="assistant-message"><span className="assistant-avatar"><Bot size={16} /></span><div><strong>ATLAS Assistant</strong><div className="streaming-line"><LoaderCircle size={15} /> Reviewing customer records and trusted sources…</div><Button size="sm" onClick={() => model.setStreaming(false)}><CircleStop size={13} /> Stop</Button></div></article>}
          </div>
          <div className="assistant-composer">
            <textarea value={model.draft} onChange={(event) => model.setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); model.send(); } }} placeholder="Ask about customers, work, or knowledge…" aria-label="Ask ATLAS Assistant" />
            <div><span>ATLAS can make mistakes. Verify important information.</span><Button variant="primary" size="icon" disabled={!model.draft.trim() || model.streaming || !!model.selected.state} aria-label="Send question" onClick={model.send}><Send size={15} /></Button></div>
          </div>
        </section>

        <aside className="assistant-context" aria-label="CRM context"><header><h2>CRM context</h2><Badge tone="blue">3 records</Badge></header><div className="assistant-context-content"><div className="context-record"><Avatar initials="MP" tone="green" /><span><strong>Mina Park</strong><small>Lead · Qualified · Score 88</small></span><ChevronRight size={14} /></div><div className="context-record"><Building2 size={15} /><span><strong>Arcade</strong><small>Company · Customer</small></span><ChevronRight size={14} /></div><div className="context-record"><Target size={15} /><span><strong>Enterprise rollout</strong><small>Opportunity · Qualified</small></span><ChevronRight size={14} /></div><div className="context-note"><AlertCircle size={15} /><p><strong>Context is read-only</strong><small>Proposed changes require explicit approval.</small></p></div></div></aside>
      </div>
    </main>
  );
}

function AssistantWelcome({ suggestions, onSelect }: { suggestions: string[]; onSelect: (value: string) => void }) {
  return <div className="assistant-welcome"><span className="assistant-logo"><Sparkles size={22} /></span><h2>How can I help?</h2><p>Ask about customer activity, open work, or trusted knowledge.</p><div>{suggestions.map((suggestion) => <button key={suggestion} onClick={() => onSelect(suggestion)}>{suggestion}<ArrowRight size={14} /></button>)}</div></div>;
}

function AssistantResponse({ compact, onToast }: { compact?: boolean; onToast: (message: string) => void }) {
  const [sourcesOpen, setSourcesOpen] = useState(!compact);
  return <article className="assistant-message"><span className="assistant-avatar"><Bot size={16} /></span><div className="assistant-response"><strong>ATLAS Assistant</strong><p>Three leads need attention today based on open inquiries, recent engagement, and overdue follow-up:</p><ol><li><b>Mina Park at Arcade</b> — qualified lead with an unanswered enterprise plan question.</li><li><b>Nadia Flores at Northstar</b> — custom terms review is waiting for approval.</li><li><b>Jon Bell at Vertex</b> — security questionnaire delivery failed.</li></ol>{!compact && <><div className="assistant-table"><div><b>Lead</b><b>Priority</b><b>Next step</b></div><div><span>Mina Park</span><Badge tone="red">High</Badge><span>Reply today</span></div><div><span>Nadia Flores</span><Badge tone="amber">Medium</Badge><span>Review terms</span></div></div><pre><code><Code2 size={13} /> filter: status = open{`\n`}sort: last_activity asc</code></pre></>}
    <button className="source-toggle" onClick={() => setSourcesOpen(!sourcesOpen)} aria-expanded={sourcesOpen}><FileText size={14} /> 3 sources <ChevronDown size={14} className={sourcesOpen ? "rotate-180" : ""} /></button>
    {sourcesOpen && <div className="citation-list"><details open><summary>CRM · Lead record: Mina Park <Badge tone="green">Lead score 88</Badge></summary><p>Qualified lead. Last activity: enterprise plan inquiry received 8 minutes ago.</p></details><details><summary>Knowledge · Enterprise implementation guide</summary><p>Workspace roles and account setup are reviewed during implementation planning.</p></details></div>}
    <div className="proposed-action"><span><CheckCircle2 size={16} /></span><div><strong>Proposed action</strong><p>Create a follow-up task for Mina Park, due today.</p></div><Button size="sm" variant="primary" onClick={() => onToast("Approval request opened")}>Review approval</Button></div>
    <div className="response-actions"><Button size="sm" variant="ghost" onClick={() => onToast("Response copied")}>Copy</Button><Button size="sm" variant="ghost" onClick={() => onToast("Response marked helpful")}>Helpful</Button><Button size="sm" variant="ghost" onClick={() => onToast("Assistant is retrying the answer")}><RefreshCw size={13} /> Retry</Button></div>
  </div></article>;
}
