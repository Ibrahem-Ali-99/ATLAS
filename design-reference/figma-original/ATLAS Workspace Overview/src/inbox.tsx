import { useMemo, useState } from "react";
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
import { appConfig } from "./appConfig";
import { Avatar, Badge, Button, Modal, type Tone } from "./components";

type Channel = "Website chat" | "Email" | "WhatsApp";
type ConversationStatus = "Open" | "Pending" | "Resolved";
type Message = {
  id: number;
  author: string;
  body: string;
  time: string;
  direction: "in" | "out";
  state?: "sent" | "delivered" | "failed";
};
type Conversation = {
  id: number;
  customer: string;
  initials: string;
  company: string;
  subject: string;
  preview: string;
  time: string;
  channel: Channel;
  status: ConversationStatus;
  assignee: string;
  unread: boolean;
  unavailable?: boolean;
  messages: Message[];
};

const initialConversations: Conversation[] = [
  {
    id: 1,
    customer: "Mina Park",
    initials: "MP",
    company: "Arcade",
    subject: "Enterprise plan requirements",
    preview: "Can you confirm the account setup steps?",
    time: "8m",
    channel: "Website chat",
    status: "Open",
    assignee: "Olivia Martin",
    unread: true,
    messages: [
      { id: 1, author: "Mina Park", body: "Hi, we are evaluating ATLAS for our operations team.", time: "9:42 AM", direction: "in" },
      { id: 2, author: "ATLAS Assistant", body: "I can help with that. What would you like to know?", time: "9:43 AM", direction: "out", state: "delivered" },
      { id: 3, author: "Mina Park", body: "Can you confirm the account setup steps and what the implementation process looks like?", time: "9:46 AM", direction: "in" },
    ],
  },
  {
    id: 2,
    customer: "Nadia Flores",
    initials: "NF",
    company: "Northstar",
    subject: "Data residency options",
    preview: "We need clarification before legal review.",
    time: "52m",
    channel: "Email",
    status: "Pending",
    assignee: "Olivia Martin",
    unread: true,
    messages: [
      { id: 1, author: "Nadia Flores", body: "Could you share the currently supported data residency options? We need clarification before legal review.", time: "8:56 AM", direction: "in" },
      { id: 2, author: "Olivia Martin", body: "I’m confirming the applicable policy documentation and will follow up shortly.", time: "9:08 AM", direction: "out", state: "sent" },
    ],
  },
  {
    id: 3,
    customer: "Jon Bell",
    initials: "JB",
    company: "Vertex",
    subject: "Security questionnaire",
    preview: "The attachment could not be delivered.",
    time: "3h",
    channel: "Email",
    status: "Open",
    assignee: "Maya Chen",
    unread: false,
    messages: [
      { id: 1, author: "Jon Bell", body: "Following up on the security questionnaire shared yesterday.", time: "7:20 AM", direction: "in" },
      { id: 2, author: "Maya Chen", body: "Thanks, Jon. The completed questionnaire is attached.", time: "7:42 AM", direction: "out", state: "failed" },
    ],
  },
  {
    id: 4,
    customer: "Theo Brooks",
    initials: "TB",
    company: "Layers",
    subject: "Workspace provisioning",
    preview: "Website chat is currently unavailable.",
    time: "1d",
    channel: "Website chat",
    status: "Resolved",
    assignee: "Sam Rivera",
    unread: false,
    unavailable: true,
    messages: [
      { id: 1, author: "Theo Brooks", body: "Our workspace is ready. Thank you for the help.", time: "Yesterday", direction: "in" },
      { id: 2, author: "Sam Rivera", body: "Glad to hear it. I’ve marked this conversation as resolved.", time: "Yesterday", direction: "out", state: "delivered" },
    ],
  },
];

const channelIcon = (channel: Channel) =>
  channel === "Email" ? Mail : channel === "WhatsApp" ? MessageCircle : Globe2;
const channelTone = (channel: Channel): Tone =>
  channel === "Email" ? "blue" : channel === "WhatsApp" ? "green" : "purple";
const statusTone = (status: ConversationStatus): Tone =>
  status === "Open" ? "blue" : status === "Pending" ? "amber" : "green";

function useInboxModel(onToast: (message: string) => void) {
  const [conversations, setConversations] = useState(initialConversations);
  const [selectedId, setSelectedId] = useState(1);
  const [search, setSearch] = useState("");
  const [channel, setChannel] = useState("All channels");
  const [status, setStatus] = useState("All statuses");
  const [assignee, setAssignee] = useState("All assignees");
  const [draft, setDraft] = useState("");
  const [humanOnly, setHumanOnly] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const selected = conversations.find((item) => item.id === selectedId) || conversations[0];
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
  const patch = (id: number, values: Partial<Conversation>) =>
    setConversations((current) => current.map((item) => (item.id === id ? { ...item, ...values } : item)));
  const send = () => {
    if (!draft.trim()) return;
    patch(selected.id, {
      preview: draft,
      time: "Now",
      messages: [...selected.messages, { id: Date.now(), author: appConfig.user.name, body: draft, time: "Now", direction: "out", state: "sent" }],
    });
    setDraft("");
    onToast("Reply added to the conversation");
  };
  return {
    conversations, filtered, selected, selectedId, setSelectedId, search, setSearch, channel, setChannel,
    status, setStatus, assignee, setAssignee, draft, setDraft, humanOnly, setHumanOnly, settingsOpen,
    setSettingsOpen, contextOpen, setContextOpen, patch, send,
  };
}

export function InboxWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const model = useInboxModel(onToast);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const suggestions = [
    "I can share the available workspace setup and role-planning guide.",
    "I’ll connect you with our security specialist for the implementation details.",
  ];

  return (
    <main className="module-main inbox-main">
      <div className="module-heading">
        <div><div className="eyebrow"><span className="live-dot" /> Customer communications</div><h1>Inbox</h1><p>Manage customer conversations across connected channels.</p></div>
        <Button onClick={() => model.setSettingsOpen(true)}><Settings2 size={15} /> Website chat</Button>
      </div>
      <div className={`inbox-layout ${model.selectedId ? "has-selection" : ""}`}>
        <section className="inbox-list-panel" aria-label="Conversations">
          <div className="inbox-list-header">
            <div><h2>Conversations</h2><Badge tone="blue">16 open</Badge></div>
            <div className="module-search"><Search size={15} /><input value={model.search} onChange={(event) => model.setSearch(event.target.value)} placeholder="Search conversations" aria-label="Search conversations" />{model.search && <button aria-label="Clear search" onClick={() => model.setSearch("")}><X size={14} /></button>}</div>
            <Button size="sm" variant={model.channel !== "All channels" || model.status !== "All statuses" || model.assignee !== "All assignees" ? "primary" : "secondary"} onClick={() => setFiltersOpen(!filtersOpen)}><Filter size={14} /> Filters</Button>
          </div>
          {filtersOpen && <div className="inbox-filters"><select aria-label="Filter by channel" value={model.channel} onChange={(event) => model.setChannel(event.target.value)}><option>All channels</option><option>Website chat</option><option>Email</option><option>WhatsApp</option></select><select aria-label="Filter by status" value={model.status} onChange={(event) => model.setStatus(event.target.value)}><option>All statuses</option><option>Open</option><option>Pending</option><option>Resolved</option></select><select aria-label="Filter by assignee" value={model.assignee} onChange={(event) => model.setAssignee(event.target.value)}><option>All assignees</option><option>Olivia Martin</option><option>Maya Chen</option><option>Sam Rivera</option></select></div>}
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
            <Button className="thread-back" size="icon" variant="ghost" aria-label="Back to conversations" onClick={() => model.setSelectedId(0)}><ArrowLeft size={17} /></Button>
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
              {message.direction === "out" && <div className={`delivery-state ${message.state === "failed" ? "failed" : ""}`}>{message.state === "failed" ? <><AlertTriangle size={12} /> Delivery failed <button onClick={() => onToast("Message queued to retry")}>Retry</button></> : message.state === "delivered" ? <><CheckCheck size={12} /> Delivered</> : <><Check size={12} /> Sent</>}</div>}
            </article>)}
          </div>
          <div className="suggested-replies">
            <span><Sparkles size={13} /> Suggested replies</span>
            <div>{suggestions.map((suggestion) => <button key={suggestion} onClick={() => model.setDraft(suggestion)}>{suggestion}</button>)}</div>
          </div>
          <div className="composer">
            <textarea value={model.draft} onChange={(event) => model.setDraft(event.target.value)} placeholder="Write a reply…" aria-label="Reply message" />
            <div><span>{model.draft.length}/1,000</span><Button variant="primary" disabled={!model.draft.trim() || model.selected.unavailable} onClick={model.send}><Send size={14} /> Send</Button></div>
          </div>
        </section>

        <CustomerContext conversation={model.selected} patch={model.patch} onToast={onToast} mobileOpen={model.contextOpen} onClose={() => model.setContextOpen(false)} />
      </div>

      <Modal open={model.settingsOpen} title="Website chat" description="Configure how ATLAS handles new website conversations." onClose={() => model.setSettingsOpen(false)}>
        <div className="dialog-body">
          <div className="chat-preview"><div className="chat-preview-site"><span>{appConfig.organization.initials}</span><strong>{appConfig.organization.name}</strong></div><div className="chat-preview-window"><header><span className="live-dot" />Chat with our team</header><p>Hi, how can we help?</p><div>Type a message… <Send size={12} /></div></div></div>
          <label className="toggle-row"><span><strong>Human-only mode</strong><small>Route every new conversation directly to staff.</small></span><input type="checkbox" checked={model.humanOnly} onChange={(event) => model.setHumanOnly(event.target.checked)} /></label>
          <label className="field"><span>Greeting</span><input defaultValue="Hi, how can we help?" /></label>
          <div className="permission-state"><ShieldCheck size={17} /><span><strong>Domain settings are restricted</strong><small>An administrator must change the allowed website domains.</small></span></div>
        </div>
        <div className="dialog-footer"><Button onClick={() => model.setSettingsOpen(false)}>Cancel</Button><Button variant="primary" onClick={() => { model.setSettingsOpen(false); onToast("Website chat settings saved"); }}>Save settings</Button></div>
      </Modal>
    </main>
  );
}

function CustomerContext({
  conversation,
  patch,
  onToast,
  mobileOpen,
  onClose,
}: {
  conversation: Conversation;
  patch: (id: number, values: Partial<Conversation>) => void;
  onToast: (message: string) => void;
  mobileOpen: boolean;
  onClose: () => void;
}) {
  return (
    <aside className={`customer-context ${mobileOpen ? "mobile-open" : ""}`} aria-label="Customer context">
      <header><div><h2>Customer context</h2><p>CRM and conversation controls</p></div><Button className="context-close" size="icon" variant="ghost" aria-label="Close customer context" onClick={onClose}><X size={16} /></Button></header>
      <div className="context-scroll">
        <section className="customer-card"><Avatar initials={conversation.initials} tone="blue" /><div><strong>{conversation.customer}</strong><span>{conversation.company}</span></div><Button size="icon" variant="ghost" aria-label="Open customer menu"><MoreHorizontal size={16} /></Button></section>
        <section className="context-section"><h3>Conversation</h3>
          <label className="field"><span>Assignee</span><select value={conversation.assignee} onChange={(event) => { patch(conversation.id, { assignee: event.target.value }); onToast(`Assigned to ${event.target.value}`); }}><option>Olivia Martin</option><option>Maya Chen</option><option>Sam Rivera</option></select></label>
          <label className="field"><span>Status</span><select value={conversation.status} onChange={(event) => patch(conversation.id, { status: event.target.value as ConversationStatus })}><option>Open</option><option>Pending</option><option>Resolved</option></select></label>
          <Button variant="secondary" onClick={() => { patch(conversation.id, { assignee: appConfig.user.name }); onToast("Human takeover enabled"); }}><UserRoundCheck size={14} /> Take over conversation</Button>
        </section>
        <section className="context-section"><h3>Customer details</h3><dl className="context-details"><div><dt>Email</dt><dd>{conversation.customer.toLowerCase().replace(" ", ".")}@{conversation.company.toLowerCase()}.example</dd></div><div><dt>Company</dt><dd>{conversation.company}</dd></div><div><dt>Local time</dt><dd>10:24 AM</dd></div></dl></section>
        <section className="context-section"><div className="context-title"><h3>Linked CRM records</h3><button onClick={() => onToast("Opening CRM record")}>View CRM</button></div><div className="linked-context-list"><button><Building2 size={14} /><span><strong>{conversation.company}</strong><small>Company · Customer</small></span><ChevronRight size={14} /></button><button><CircleUserRound size={14} /><span><strong>{conversation.customer}</strong><small>Contact · Decision maker</small></span><ChevronRight size={14} /></button><button><Clock3 size={14} /><span><strong>{conversation.subject}</strong><small>Inquiry · {conversation.status}</small></span><ExternalLink size={13} /></button></div></section>
      </div>
    </aside>
  );
}
