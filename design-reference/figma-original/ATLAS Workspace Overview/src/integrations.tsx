import { useMemo, useState } from "react";
import { AlertCircle, CalendarDays, CheckCircle2, ChevronRight, Code2, Eye, EyeOff, Globe2, Mail, MessageCircle, PlugZap, RefreshCw, Search, Send, Unplug, Webhook, Workflow, X } from "lucide-react";
import { Badge, Button, type Tone } from "./components";

type Status = "Connected" | "Disconnected" | "Sandbox" | "Simulated" | "Unavailable";
type Integration = { id: string; name: string; description: string; status: Status; icon: typeof Mail; tone: Tone; configurable: boolean };
const initialItems: Integration[] = [
  { id: "email", name: "Email", description: "Inbound and outbound customer email", status: "Disconnected", icon: Mail, tone: "neutral", configurable: true },
  { id: "calendar", name: "Calendar", description: "Availability and event coordination", status: "Unavailable", icon: CalendarDays, tone: "red", configurable: false },
  { id: "whatsapp", name: "WhatsApp", description: "Customer messaging channel", status: "Unavailable", icon: MessageCircle, tone: "red", configurable: false },
  { id: "chat", name: "Website chat", description: "Local widget configuration", status: "Connected", icon: Globe2, tone: "green", configurable: true },
  { id: "n8n", name: "n8n", description: "Workflow automation endpoint", status: "Sandbox", icon: Workflow, tone: "purple", configurable: true },
  { id: "webhook", name: "Webhooks", description: "Signed event destination", status: "Simulated", icon: Webhook, tone: "blue", configurable: true },
];
const toneFor = (status: Status): Tone => status === "Connected" ? "green" : status === "Unavailable" ? "red" : status === "Sandbox" ? "purple" : status === "Simulated" ? "blue" : "neutral";

export function IntegrationsWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const [items, setItems] = useState(initialItems);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Integration | null>(null);
  const [secret, setSecret] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [endpoint, setEndpoint] = useState("");
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState("");
  const filtered = useMemo(() => items.filter((item) => `${item.name} ${item.description} ${item.status}`.toLowerCase().includes(search.toLowerCase())), [items, search]);
  const save = () => {
    if (!selected) return;
    if (selected.id !== "chat" && (!endpoint.startsWith("https://") || secret.length < 8)) { setError("Enter an HTTPS endpoint and a credential of at least 8 characters."); return; }
    setItems((current) => current.map((item) => item.id === selected.id ? { ...item, status: item.id === "chat" ? "Sandbox" : "Simulated", tone: item.id === "chat" ? "purple" : "blue" } : item));
    setError(""); setSecret(""); setSelected(null); onToast("Integration configuration saved locally");
  };
  const test = () => {
    if (!selected || !["Sandbox", "Simulated", "Connected"].includes(selected.status)) return;
    setTesting(true); window.setTimeout(() => { setTesting(false); onToast(`${selected.name} local test completed`); }, 500);
  };
  return <main className="module-main integrations-main">
    <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Workspace connections</div><h1>Integrations</h1><p>Configure supported local adapters without implying provider availability.</p></div><Badge tone="amber"><Unplug size={13} /> No live providers</Badge></div>
    <div className="integration-toolbar"><label className="module-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search integrations" /></label><div className="integration-legend"><Badge tone="green">Connected</Badge><Badge tone="purple">Sandbox</Badge><Badge tone="red">Unavailable</Badge></div></div>
    <section className="integration-grid" aria-label="Available integrations">{filtered.length ? filtered.map((item) => { const Icon = item.icon; return <button className="integration-card" key={item.id} onClick={() => { setSelected(item); setEndpoint(item.id === "webhook" ? "https://hooks.harborandco.example/atlas" : ""); setSecret(""); setError(""); }}><span className={`integration-icon badge-${item.tone}`}><Icon size={19} /></span><span><strong>{item.name}</strong><small>{item.description}</small></span><Badge tone={toneFor(item.status)}>{item.status}</Badge><ChevronRight size={15} /></button>; }) : <div className="module-empty panel"><PlugZap size={24} /><strong>No integrations found</strong><p>Try a different name or connection state.</p><Button size="sm" onClick={() => setSearch("")}>Clear search</Button></div>}</section>
    {selected && <><button className="drawer-backdrop" aria-label="Close integration settings" onClick={() => setSelected(null)} /><aside className="drawer integration-drawer" aria-label={`${selected.name} integration settings`}><div className="drawer-header"><div><h2>{selected.name}</h2><p>{selected.description}</p></div><Button size="icon" variant="ghost" aria-label="Close integration settings" onClick={() => setSelected(null)}><X size={17} /></Button></div><div className="drawer-content">
      <div className="integration-status"><span className={`integration-icon badge-${selected.tone}`}>{(() => { const Icon = selected.icon; return <Icon size={18} />; })()}</span><span><strong>Connection status</strong><small>{selected.status === "Unavailable" ? "Provider capability is not available." : `${selected.status} configuration only; no live delivery is verified.`}</small></span><Badge tone={toneFor(selected.status)}>{selected.status}</Badge></div>
      {selected.configurable ? <section className="drawer-section form-stack"><h3>Configuration</h3>{selected.id === "chat" ? <><label className="field"><span>Widget label</span><input defaultValue="Chat with Harbor & Co." /></label><label className="switch-row"><span><strong>Human-only mode</strong><small>Disable automated responses in the sandbox widget.</small></span><input type="checkbox" role="switch" /></label></> : <><label className="field"><span>{selected.id === "email" ? "Server endpoint" : selected.id === "n8n" ? "Workflow URL" : "Webhook endpoint"}</span><input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="https://…" /></label><label className="field"><span>Credential</span><div className="secret-input"><input type={showSecret ? "text" : "password"} value={secret} onChange={(event) => setSecret(event.target.value)} placeholder="Stored only until this drawer closes" /><button aria-label={showSecret ? "Hide credential" : "Show credential"} onClick={() => setShowSecret(!showSecret)}>{showSecret ? <EyeOff size={15} /> : <Eye size={15} />}</button></div><small>Secrets are masked and are not persisted in this frontend prototype.</small></label></>}{error && <div className="auth-error" role="alert"><AlertCircle size={15} />{error}</div>}</section> : <div className="permission-state"><Unplug size={17} /><span><strong>Configuration unavailable</strong><small>This provider cannot be connected in the current workspace.</small></span></div>}
      <section className="drawer-section"><h3>Connection test</h3><p className="detail-copy">{["Sandbox", "Simulated", "Connected"].includes(selected.status) ? "Run a supported local validation. This does not contact an external provider." : "Save a valid local configuration before testing."}</p><Button disabled={!["Sandbox", "Simulated", "Connected"].includes(selected.status) || testing} onClick={test}>{testing ? <RefreshCw className="spinning" size={14} /> : <Send size={14} />} Test connection</Button></section>
    </div><div className="drawer-footer"><Button onClick={() => setSelected(null)}>Cancel</Button><Button variant="primary" disabled={!selected.configurable} onClick={save}>Save configuration</Button></div></aside></>}
  </main>;
}
