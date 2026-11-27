import { useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, ChevronRight, Code2, Eye, EyeOff, Globe2, Mail, MessageCircle, PlugZap, RefreshCw, Search, Send, Unplug, Webhook, Workflow, X } from "lucide-react";
import { failureMessage, issueWebhookKey, listIntegrationRows, loadDiagnostics, revokeWebhookKey, saveIntegrationRow, setIntegrationEnabled, verifyIntegrationRow, webhookKeyStatus, type IntegrationRow, type WebhookKeyStatus } from "@/data/resources";
import { Badge, Button, type Tone } from "./components";

type Status = "Connected" | "Disconnected" | "Sandbox" | "Simulated" | "Unavailable";
type Integration = { id: string; name: string; description: string; status: Status; icon: typeof Mail; tone: Tone; row?: IntegrationRow };
const catalog: Integration[] = [
  { id: "email", name: "Email", description: "Inbound and outbound customer email", status: "Unavailable", icon: Mail, tone: "neutral" },
  { id: "chat", name: "Language model", description: "Assistant inference", status: "Unavailable", icon: Globe2, tone: "neutral" },
  { id: "embedding", name: "Embeddings", description: "Knowledge retrieval", status: "Unavailable", icon: Code2, tone: "neutral" },
  { id: "whatsapp", name: "WhatsApp", description: "Customer messaging channel", status: "Unavailable", icon: MessageCircle, tone: "neutral" },
  { id: "n8n", name: "n8n", description: "Workflow callback key", status: "Unavailable", icon: Workflow, tone: "neutral" },
];
function connectionLabel(status: string, verified: string | null): Status {
  if (status === "disabled") return "Disconnected";
  if (status === "verification_failed") return "Unavailable";
  if (verified) return "Connected";
  if (status === "configured") return "Sandbox";
  return "Unavailable";
}
const toneFor = (status: Status): Tone => status === "Connected" ? "green" : status === "Unavailable" ? "red" : status === "Sandbox" ? "purple" : status === "Simulated" ? "blue" : "neutral";
const textValue = (config: Record<string, unknown> | undefined, key: string) => typeof config?.[key] === "string" ? String(config[key]) : "";

export function IntegrationsWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const [items, setItems] = useState(catalog);
  const [webhook, setWebhook] = useState<WebhookKeyStatus>(null);
  const [issuedSecret, setIssuedSecret] = useState("");
  const reload = () => Promise.all([listIntegrationRows(), loadDiagnostics(), webhookKeyStatus()]).then(([rows, diagnostics, key]) => {
    setWebhook(key);
    const assistant = diagnostics.activity?.assistant;
    setItems(catalog.map((item) => {
      if (item.id === "n8n") {
        const status: Status = !key || key.revoked_at ? "Disconnected" : key.last_accepted_at ? "Connected" : "Sandbox";
        return { ...item, status, description: key?.last_accepted_at ? "Callback accepted" : key && !key.revoked_at ? "Waiting for a signed callback" : "No callback key is stored" };
      }
      const row = rows.find((entry) => entry.integration_type === item.id);
      if (!row && item.id === "chat" && assistant) {
        return { ...item, status: assistant.status === "errors" ? "Unavailable" : assistant.status === "available" ? "Connected" : "Disconnected", description: assistant.last_error_code || "Assistant activity recorded" };
      }
      if (!row) return { ...item, status: "Disconnected" as Status, description: "No workspace configuration is stored" };
      return { ...item, row, status: connectionLabel(row.status, row.verified_at), description: row.verification_detail || `${row.provider} · ${row.has_credentials ? "credentials stored" : "no credentials"}` };
    }));
  });
  useEffect(() => { reload().catch((error: unknown) => onToast(failureMessage(error))); }, [onToast]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Integration | null>(null);
  const [provider, setProvider] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("587");
  const [sender, setSender] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [phone, setPhone] = useState("");
  const [account, setAccount] = useState("");
  const [secret, setSecret] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const filtered = useMemo(() => items.filter((item) => `${item.name} ${item.description} ${item.status}`.toLowerCase().includes(search.toLowerCase())), [items, search]);
  const open = (item: Integration) => {
    const config = item.row?.config;
    setSelected(item);
    setProvider(item.row?.provider || (item.id === "email" ? "smtp" : item.id === "whatsapp" ? "meta" : item.id === "embedding" ? "ollama" : "groq"));
    setHost(textValue(config, "host"));
    setPort(typeof config?.port === "number" ? String(config.port) : "587");
    setSender(textValue(config, "from_address"));
    setBaseUrl(textValue(config, "base_url"));
    setModel(textValue(config, "model"));
    setPhone(textValue(config, "phone_number_id"));
    setAccount(textValue(config, "business_account_id"));
    setSecret("");
    setIssuedSecret("");
    setShowSecret(false);
  };
  const save = () => {
    if (!selected || selected.id === "n8n") return;
    const config: Record<string, unknown> = selected.id === "email"
      ? { host, port: Number(port), from_address: sender }
      : selected.id === "whatsapp"
        ? { phone_number_id: phone, business_account_id: account }
        : { base_url: baseUrl, model, ...(selected.id === "embedding" ? { dimensions: 768 } : {}) };
    setSaving(true);
    void saveIntegrationRow(selected.id, { provider, config, credentials: secret || undefined, expected_version: selected.row?.credential_version }).then(() => {
      setSecret("");
      onToast(`${selected.name} configuration saved`);
      return reload();
    }).catch((error: unknown) => onToast(failureMessage(error))).finally(() => setSaving(false));
  };
  const test = () => {
    if (!selected || selected.id === "n8n") return;
    setTesting(true);
    void verifyIntegrationRow(selected.id).then((result) => onToast(result.verified ? `${selected.name} verified` : result.detail)).catch((error: unknown) => onToast(failureMessage(error))).finally(() => setTesting(false));
  };
  const toggle = (enabled: boolean) => {
    if (!selected?.row) return;
    void setIntegrationEnabled(selected.id, enabled, selected.row.credential_version).then(() => { onToast(enabled ? `${selected.name} enabled` : `${selected.name} disabled`); return reload(); }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const issueKey = (rotate: boolean) => {
    void issueWebhookKey(rotate).then((result) => { setIssuedSecret(result.secret); onToast(rotate ? "Callback key rotated" : "Callback key issued"); return reload(); }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  return <main className="module-main integrations-main">
      <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Workspace connections</div><h1>Integrations</h1><p>Stored provider configuration for this workspace. Live customer messaging stays disabled until a provider accepts it.</p></div><Badge tone="blue"><Unplug size={13} /> {items.filter((item) => item.status === "Connected").length} verified</Badge></div>
    <div className="integration-toolbar"><label className="module-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search integrations" /></label><div className="integration-legend"><Badge tone="green">Connected</Badge><Badge tone="purple">Sandbox</Badge><Badge tone="red">Unavailable</Badge></div></div>
    <section className="integration-grid" aria-label="Available integrations">{filtered.length ? filtered.map((item) => { const Icon = item.icon; return <button className="integration-card" key={item.id} onClick={() => open(item)}><span className={`integration-icon badge-${item.tone}`}><Icon size={19} /></span><span><strong>{item.name}</strong><small>{item.description}</small></span><Badge tone={toneFor(item.status)}>{item.status}</Badge><ChevronRight size={15} /></button>; }) : <div className="module-empty panel"><PlugZap size={24} /><strong>No integrations found</strong><p>Try a different name or connection state.</p><Button size="sm" onClick={() => setSearch("")}>Clear search</Button></div>}</section>
    {selected && <><button className="drawer-backdrop" aria-label="Close integration settings" onClick={() => setSelected(null)} /><aside className="drawer integration-drawer" aria-label={`${selected.name} integration settings`}><div className="drawer-header"><div><h2>{selected.name}</h2><p>{selected.description}</p></div><Button size="icon" variant="ghost" aria-label="Close integration settings" onClick={() => setSelected(null)}><X size={17} /></Button></div><div className="drawer-content">
      <div className="integration-status"><span className={`integration-icon badge-${selected.tone}`}>{(() => { const Icon = selected.icon; return <Icon size={18} />; })()}</span><span><strong>Connection status</strong><small>{selected.description}</small></span><Badge tone={toneFor(selected.status)}>{selected.status}</Badge></div>
      {selected.id === "n8n" ? <section className="drawer-section form-stack"><h3>Callback key</h3><p className="detail-copy">{webhook && !webhook.revoked_at ? "A callback key is stored. The secret is shown only when it is issued or rotated." : "No active callback key is stored."}</p>{issuedSecret && <label className="field"><span>New callback secret</span><input readOnly value={issuedSecret} aria-label="Callback secret" /></label>}<div className="campaign-actions"><Button size="sm" onClick={() => issueKey(Boolean(webhook && !webhook.revoked_at))}>{webhook && !webhook.revoked_at ? "Rotate key" : "Issue key"}</Button>{webhook && !webhook.revoked_at && <Button size="sm" onClick={() => { void revokeWebhookKey().then(() => { setIssuedSecret(""); onToast("Callback key revoked"); return reload(); }).catch((error: unknown) => onToast(failureMessage(error))); }}>Revoke key</Button>}</div></section> : <section className="drawer-section form-stack"><h3>Configuration</h3>
        <label className="field"><span>Provider</span><select value={provider} onChange={(event) => setProvider(event.target.value)}>{selected.id === "email" ? <option value="smtp">smtp</option> : selected.id === "whatsapp" ? <option value="meta">meta</option> : selected.id === "embedding" ? <><option value="ollama">ollama</option><option value="openai">openai</option></> : <><option value="groq">groq</option><option value="openai">openai</option></>}</select></label>
        {selected.id === "email" ? <><label className="field"><span>SMTP host</span><input value={host} onChange={(event) => setHost(event.target.value)} /></label><label className="field"><span>Port</span><input value={port} onChange={(event) => setPort(event.target.value)} inputMode="numeric" /></label><label className="field"><span>Sender address</span><input value={sender} onChange={(event) => setSender(event.target.value)} /></label></> : selected.id === "whatsapp" ? <><label className="field"><span>Phone number ID</span><input value={phone} onChange={(event) => setPhone(event.target.value)} /></label><label className="field"><span>Business account ID</span><input value={account} onChange={(event) => setAccount(event.target.value)} /></label></> : <><label className="field"><span>Base URL</span><input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://" /></label><label className="field"><span>Model</span><input value={model} onChange={(event) => setModel(event.target.value)} /></label></>}
        <label className="field"><span>Credential</span><div className="secret-input"><input type={showSecret ? "text" : "password"} value={secret} onChange={(event) => setSecret(event.target.value)} placeholder={selected.row?.has_credentials ? "Stored credential remains until replaced" : "Required to store a new credential"} autoComplete="off" /><button type="button" aria-label={showSecret ? "Hide credential" : "Show credential"} onClick={() => setShowSecret(!showSecret)}>{showSecret ? <EyeOff size={15} /> : <Eye size={15} />}</button></div><small>A stored credential is not shown again. Leave this blank to keep it.</small></label>
      </section>}
      {selected.id !== "n8n" && <section className="drawer-section"><h3>Connection test</h3><p className="detail-copy">Verification uses the stored configuration. It does not send a customer message.</p><div className="campaign-actions"><Button disabled={!selected.row || testing} onClick={test}>{testing ? <RefreshCw className="spinning" size={14} /> : <Send size={14} />} Test connection</Button>{selected.row && <Button onClick={() => toggle(selected.row?.status === "disabled")}>{selected.row.status === "disabled" ? <CheckCircle2 size={14} /> : <Unplug size={14} />} {selected.row.status === "disabled" ? "Enable" : "Disable"}</Button>}</div></section>}
    </div><div className="drawer-footer"><Button onClick={() => setSelected(null)}>Close</Button>{selected.id !== "n8n" && <Button variant="primary" disabled={saving} onClick={save}>{saving ? <RefreshCw className="spinning" size={14} /> : null} Save configuration</Button>}</div></aside></>}
  </main>;
}
