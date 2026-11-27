import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  Building2,
  Check,
  CheckCheck,
  ChevronRight,
  CircleUserRound,
  Clock3,
  ExternalLink,
  Filter,
  Globe2,
  Inbox as InboxIcon,
  Mail,
  MessageCircle,
  MoreHorizontal,
  PanelRight,
  RefreshCw,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  UserRoundCheck,
  WifiOff,
  X,
} from "lucide-react";
import { archiveInbox, assignInbox, draftInbox, failureMessage, getWidget, inboxAssignees, loadInbox, loadInboxThread, saveWidget, submitInboxReply, takeOverInbox, updateInboxStatus, type InboxItem } from "@/data/resources";
import { appConfig } from "./appConfig";
import { Avatar, Badge, Button, Modal, type Tone } from "./components";

type Channel = "Website chat" | "Email" | "WhatsApp";
type ConversationStatus = "Open" | "Pending" | "Resolved";
type Message = InboxItem["messages"][number];
type Conversation = InboxItem & { unavailable?: boolean; assigneeId?: string | null };

const channelIcon = (channel: Channel) =>
  channel === "Email" ? Mail : channel === "WhatsApp" ? MessageCircle : Globe2;
const channelTone = (channel: Channel): Tone =>
  channel === "Email" ? "blue" : channel === "WhatsApp" ? "green" : "purple";
const statusTone = (status: ConversationStatus): Tone =>
  status === "Open" ? "blue" : status === "Pending" ? "amber" : "green";

const emptyConversation: Conversation = { id: "", customer: "No conversation", initials: "—", company: "", subject: "", preview: "", time: "", channel: "Email", status: "Open", assignee: "Unassigned", unread: false, messages: [] };

function useInboxModel(onToast: (message: string) => void) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [assignees, setAssignees] = useState<{ user_id: string; full_name: string }[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [search, setSearch] = useState("");
  const [channel, setChannel] = useState("All channels");
  const [status, setStatus] = useState("All statuses");
  const [assignee, setAssignee] = useState("All assignees");
  const [draft, setDraft] = useState("");
  const [humanOnly, setHumanOnly] = useState(false);
  const [greeting, setGreeting] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const selected = conversations.find((item) => item.id === selectedId) || conversations[0] || emptyConversation;
  const filtered = useMemo(
    () =>
      conversations.filter(
        (item) =>
          `${item.customer} ${item.company} ${item.subject}`.toLowerCase().includes(search.toLowerCase()) &&
          (channel === "All channels" || item.channel === channel) &&
          (status === "All statuses" || item.status === status) &&
          (assignee === "All assignees" || item.assignee === assignee),
      ),
    [conversations, search, channel, status, assignee],
  );
  useEffect(() => {
    let cancelled = false;
    loadInbox().then((rows) => { if (!cancelled) { setConversations(rows); setSelectedId(rows[0]?.id || ""); } }).catch((error: unknown) => onToast(failureMessage(error)));
    inboxAssignees().then((rows) => { if (!cancelled) setAssignees(rows); }).catch(() => undefined);
    getWidget().then((widget) => { if (!cancelled && widget) { setGreeting(widget.welcome_message); setHumanOnly(widget.operating_mode === "human_review"); } }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [onToast]);
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    loadInboxThread(selectedId).then((thread) => {
      if (cancelled) return;
      setConversations((current) => current.map((item) => item.id === selectedId ? { ...item, ...thread, unread: false } : item));
    }).catch((error: unknown) => onToast(failureMessage(error)));
    return () => { cancelled = true; };
  }, [selectedId, onToast]);
  const patch = (id: string, values: Partial<Conversation>) =>
    setConversations((current) => current.map((item) => (item.id === id ? { ...item, ...values } : item)));
  const send = () => {
    if (!draft.trim() || !selected.id) return;
    const recipient = selected.email || "";
    if (!recipient) {
      onToast("This conversation has no reply address, so the message was not submitted.");
      return;
    }
    const body = draft.trim();
    void submitInboxReply(selected.id, recipient, selected.subject, body)
      .then(() => {
        patch(selected.id, { messages: [...selected.messages, { id: `pending-${Date.now()}`, author: appConfig.user.name, body, time: "Now", direction: "out", state: "pending" }] });
        setDraft("");
        onToast("Reply submitted for approval. It was not sent to the customer.");
      })
      .catch((error: unknown) => onToast(failureMessage(error)));
  };
  const draftReply = () => {
    if (!selected.id) return;
    void draftInbox(selected.id).then((result) => setDraft(result.body)).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const saveSettings = () => {
    void saveWidget({ welcome_message: greeting, operating_mode: humanOnly ? "human_review" : "ai_assist", allowed_domains: [] })
      .then(() => { setSettingsOpen(false); onToast("Website chat settings saved"); })
      .catch((error: unknown) => onToast(failureMessage(error)));
  };
  const archive = () => {
    if (!selected.id) return;
    void archiveInbox(selected.id).then(() => {
      setConversations((current) => current.filter((item) => item.id !== selected.id));
      setSelectedId("");
      onToast("Conversation archived");
    }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  return {
    conversations, filtered, selected, selectedId, setSelectedId, search, setSearch, channel, setChannel,
    status, setStatus, assignee, setAssignee, draft, setDraft, humanOnly, setHumanOnly, greeting, setGreeting, settingsOpen,
    setSettingsOpen, contextOpen, setContextOpen,     assignees, patch, send, draftReply, saveSettings, archive,
  };
}

export function InboxWorkspace({ onToast, onOpenCrm, focusQuery = "" }: { onToast: (message: string) => void; onOpenCrm?: (section: "Companies" | "Contacts" | "Leads", query: string) => void; focusQuery?: string }) {
  const model = useInboxModel(onToast);
  const [filtersOpen, setFiltersOpen] = useState(false);
  useEffect(() => { if (focusQuery) model.setSearch(focusQuery); }, [focusQuery, model.setSearch]);
  const openCount = model.conversations.filter((item) => item.status === "Open").length;

  return (
    <main className="module-main inbox-main">
      <div className="module-heading">
        <div><div className="eyebrow"><span className="live-dot" /> Customer communications</div><h1>Inbox</h1><p>Manage customer conversations across connected channels.</p></div>
        <Button onClick={() => model.setSettingsOpen(true)}><Settings2 size={15} /> Website chat</Button>
      </div>
      <div className={`inbox-layout ${model.selectedId ? "has-selection" : ""}`}>
        <section className="inbox-list-panel" aria-label="Conversations">
          <div className="inbox-list-header">
            <div><h2>Conversations</h2><Badge tone="blue">{openCount} open</Badge></div>
            <div className="module-search"><Search size={15} /><input value={model.search} onChange={(event) => model.setSearch(event.target.value)} placeholder="Search conversations" aria-label="Search conversations" />{model.search && <button aria-label="Clear search" onClick={() => model.setSearch("")}><X size={14} /></button>}</div>
            <Button size="sm" variant={model.channel !== "All channels" || model.status !== "All statuses" || model.assignee !== "All assignees" ? "primary" : "secondary"} onClick={() => setFiltersOpen(!filtersOpen)}><Filter size={14} /> Filters</Button>
          </div>
          {filtersOpen && <div className="inbox-filters"><select aria-label="Filter by channel" value={model.channel} onChange={(event) => model.setChannel(event.target.value)}><option>All channels</option><option>Website chat</option><option>Email</option><option>WhatsApp</option></select><select aria-label="Filter by status" value={model.status} onChange={(event) => model.setStatus(event.target.value)}><option>All statuses</option><option>Open</option><option>Pending</option><option>Resolved</option></select><select aria-label="Filter by assignee" value={model.assignee} onChange={(event) => model.setAssignee(event.target.value)}><option>All assignees</option>{model.assignees.map((person) => <option key={person.user_id}>{person.full_name}</option>)}</select></div>}
          <div className="conversation-list">
            {model.filtered.length ? model.filtered.map((conversation) => {
              const ChannelIcon = channelIcon(conversation.channel);
              return <button className={`conversation-item ${model.selected.id === conversation.id ? "active" : ""}`} key={conversation.id} onClick={() => model.setSelectedId(conversation.id)}>
                <Avatar initials={conversation.initials} tone={conversation.unread ? "blue" : "neutral"} />
                <span className="conversation-copy"><span><strong>{conversation.customer}</strong><time>{conversation.time}</time></span><b>{conversation.subject}</b><small>{conversation.preview}</small><span className="conversation-meta"><ChannelIcon size={12} />{conversation.channel}<Badge tone={statusTone(conversation.status)}>{conversation.status}</Badge></span></span>
                {conversation.unread && <i aria-label="Unread" />}
              </button>;
            }) : <div className="module-empty compact"><InboxIcon size={23} /><strong>No conversations found</strong><p>Change your search or filters.</p><Button size="sm" onClick={() => { model.setSearch(""); model.setChannel("All channels"); model.setStatus("All statuses"); model.setAssignee("All assignees"); }}>Clear filters</Button></div>}
          </div>
        </section>

        <section className="thread-panel" aria-label={`${model.selected.customer} conversation`}>
          <header className="thread-header">
            <Button className="thread-back" size="icon" variant="ghost" aria-label="Back to conversations" onClick={() => model.setSelectedId("")}><ArrowLeft size={17} /></Button>
            <Avatar initials={model.selected.initials} tone="blue" />
            <div><h2>{model.selected.customer}</h2><p>{model.selected.company} · {model.selected.channel}</p></div>
            <Badge tone={statusTone(model.selected.status)}>{model.selected.status}</Badge>
            <Button size="icon" variant="ghost" aria-label="Show customer context" className="context-toggle" onClick={() => model.setContextOpen(true)}><PanelRight size={17} /></Button>
          </header>
          {model.selected.unavailable && <div className="state-banner warning"><WifiOff size={16} /><span><strong>Channel unavailable</strong><small>Website chat is paused. Existing history remains available.</small></span><Button size="sm" disabled>Reconnect</Button></div>}
          <div className="thread-messages">
            <div className="thread-date"><span>Today</span></div>
            {model.selected.messages.map((message) => <article className={`message-bubble ${message.direction}`} key={message.id}>
              <div className="message-author"><strong>{message.author}</strong><time>{message.time}</time></div>
              <p>{message.body}</p>
              {message.direction === "out" && <div className={`delivery-state ${message.state === "failed" ? "failed" : ""}`}>{message.state === "failed" ? <><AlertTriangle size={12} /> Delivery failed</> : message.state === "pending" ? <><Check size={12} /> Pending approval</> : message.state === "delivered" ? <><CheckCheck size={12} /> Delivered</> : <><Check size={12} /> Recorded</>}</div>}
            </article>)}
          </div>
          <div className="suggested-replies">
            <span><Sparkles size={13} /> Assistant draft</span>
            <div><button onClick={model.draftReply}>Draft a reply from this conversation</button></div>
          </div>
          <div className="composer">
            <textarea value={model.draft} onChange={(event) => model.setDraft(event.target.value)} placeholder="Write a reply…" aria-label="Reply message" />
            <div><span>{model.draft.length}/1,000</span><Button variant="primary" disabled={!model.draft.trim() || !model.selected.id} onClick={model.send}><Send size={14} /> Submit for approval</Button></div>
          </div>
        </section>

        <CustomerContext conversation={model.selected} assignees={model.assignees} patch={model.patch} onToast={onToast} onArchive={model.archive} onOpenCrm={onOpenCrm} mobileOpen={model.contextOpen} onClose={() => model.setContextOpen(false)} />
      </div>

      <Modal open={model.settingsOpen} title="Website chat" description="Configure how ATLAS handles new website conversations." onClose={() => model.setSettingsOpen(false)}>
        <div className="dialog-body">
          <div className="chat-preview"><div className="chat-preview-site"><span>{appConfig.organization.initials}</span><strong>{appConfig.organization.name}</strong></div><div className="chat-preview-window"><header><span className="live-dot" />Chat with our team</header><p>Hi, how can we help?</p><div>Type a message… <Send size={12} /></div></div></div>
          <label className="toggle-row"><span><strong>Human-only mode</strong><small>Route every new conversation directly to staff.</small></span><input type="checkbox" checked={model.humanOnly} onChange={(event) => model.setHumanOnly(event.target.checked)} /></label>
          <label className="field"><span>Greeting</span><input value={model.greeting} onChange={(event) => model.setGreeting(event.target.value)} /></label>
          <div className="permission-state"><ShieldCheck size={17} /><span><strong>Domain settings are restricted</strong><small>An administrator must change the allowed website domains.</small></span></div>
        </div>
        <div className="dialog-footer"><Button onClick={() => model.setSettingsOpen(false)}>Cancel</Button><Button variant="primary" onClick={model.saveSettings}>Save settings</Button></div>
      </Modal>
    </main>
  );
}

function CustomerContext({
  conversation,
  assignees,
  patch,
  onToast,
  onArchive,
  onOpenCrm,
  mobileOpen,
  onClose,
}: {
  conversation: Conversation;
  assignees: { user_id: string; full_name: string }[];
  patch: (id: string, values: Partial<Conversation>) => void;
  onToast: (message: string) => void;
  onArchive: () => void;
  onOpenCrm?: (section: "Companies" | "Contacts" | "Leads", query: string) => void;
  mobileOpen: boolean;
  onClose: () => void;
}) {
  return (
    <aside className={`customer-context ${mobileOpen ? "mobile-open" : ""}`} aria-label="Customer context">
      <header><div><h2>Customer context</h2><p>CRM and conversation controls</p></div><Button className="context-close" size="icon" variant="ghost" aria-label="Close customer context" onClick={onClose}><X size={16} /></Button></header>
      <div className="context-scroll">
        <section className="customer-card"><Avatar initials={conversation.initials} tone="blue" /><div><strong>{conversation.customer}</strong><span>{conversation.company}</span></div><Button size="icon" variant="ghost" aria-label="Open customer menu"><MoreHorizontal size={16} /></Button></section>
        <section className="context-section"><h3>Conversation</h3>
          <label className="field"><span>Assignee</span><select value={conversation.assignee} onChange={(event) => {
            const person = assignees.find((item) => item.full_name === event.target.value);
            void assignInbox(conversation.id, person?.user_id || null).then(() => { patch(conversation.id, { assignee: event.target.value }); onToast(`Assigned to ${event.target.value}`); }).catch((error: unknown) => onToast(failureMessage(error)));
          }}><option>Unassigned</option>{assignees.map((person) => <option key={person.user_id}>{person.full_name}</option>)}</select></label>
          <label className="field"><span>Status</span><select value={conversation.status} onChange={(event) => {
            const next = event.target.value as ConversationStatus;
            const apiStatus = next === "Resolved" ? "resolved" : next === "Pending" ? "pending" : "open";
            void updateInboxStatus(conversation.id, apiStatus).then(() => patch(conversation.id, { status: next })).catch((error: unknown) => onToast(failureMessage(error)));
          }}><option>Open</option><option>Pending</option><option>Resolved</option></select></label>
          <Button variant="secondary" disabled={!conversation.id} onClick={() => { void takeOverInbox(conversation.id).then(() => { patch(conversation.id, { assignee: appConfig.user.name }); onToast("You took over this conversation"); }).catch((error: unknown) => onToast(failureMessage(error))); }}><UserRoundCheck size={14} /> Take over conversation</Button>
          <Button variant="secondary" disabled={!conversation.id} onClick={onArchive}>Archive conversation</Button>
        </section>
        <section className="context-section"><h3>Customer details</h3><dl className="context-details"><div><dt>Email</dt><dd>{conversation.email || "Not recorded"}</dd></div><div><dt>Company</dt><dd>{conversation.company}</dd></div><div><dt>Channel</dt><dd>{conversation.channel}</dd></div></dl></section>
        <section className="context-section"><div className="context-title"><h3>Linked CRM records</h3>{onOpenCrm && <button onClick={() => onOpenCrm("Companies", conversation.company)}>View CRM</button>}</div><div className="linked-context-list"><button onClick={() => onOpenCrm?.("Companies", conversation.company)}><Building2 size={14} /><span><strong>{conversation.company}</strong><small>Company</small></span><ChevronRight size={14} /></button><button onClick={() => onOpenCrm?.("Contacts", conversation.customer)}><CircleUserRound size={14} /><span><strong>{conversation.customer}</strong><small>Contact</small></span><ChevronRight size={14} /></button><button onClick={() => onOpenCrm?.("Leads", conversation.subject)}><Clock3 size={14} /><span><strong>{conversation.subject}</strong><small>Inquiry · {conversation.status}</small></span><ExternalLink size={13} /></button></div></section>
      </div>
    </aside>
  );
}
