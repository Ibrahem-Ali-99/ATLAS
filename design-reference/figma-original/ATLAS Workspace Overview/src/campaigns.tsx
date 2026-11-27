import { useMemo, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  Ban,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronRight,
  Copy,
  Edit3,
  Eye,
  Filter,
  Inbox,
  Link2Off,
  LoaderCircle,
  Mail,
  Megaphone,
  MoreHorizontal,
  Plus,
  Save,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { Avatar, Badge, Button, Modal, type Tone } from "./components";

type CampaignStatus = "Draft" | "Scheduled" | "Approval required" | "Executing" | "Failed";
type Campaign = {
  id: number;
  name: string;
  status: CampaignStatus;
  audience: string;
  recipients: number;
  owner: string;
  updated: string;
  subject: string;
  restricted?: boolean;
};

const initialCampaigns: Campaign[] = [
  { id: 1, name: "Customer onboarding guidance", status: "Draft", audience: "New customers", recipients: 4, owner: "Olivia Martin", updated: "12 min ago", subject: "Getting started with your ATLAS workspace" },
  { id: 2, name: "Product education follow-up", status: "Approval required", audience: "Active evaluation leads", recipients: 8, owner: "Sam Rivera", updated: "Yesterday", subject: "Resources for your workspace evaluation" },
  { id: 3, name: "Quarterly customer update", status: "Scheduled", audience: "Consented customers", recipients: 11, owner: "Olivia Martin", updated: "Feb 20", subject: "What’s new for your team" },
  { id: 4, name: "Workspace adoption check-in", status: "Executing", audience: "Active customers", recipients: 6, owner: "Maya Chen", updated: "Feb 19", subject: "How is your workspace working for you?" },
  { id: 5, name: "External delivery test", status: "Failed", audience: "Internal review segment", recipients: 2, owner: "Olivia Martin", updated: "Feb 18", subject: "Campaign review message", restricted: true },
];

const toneFor = (status: CampaignStatus): Tone =>
  status === "Draft" ? "neutral" : status === "Scheduled" ? "blue" : status === "Approval required" ? "amber" : status === "Executing" ? "purple" : "red";

export function CampaignsWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const [campaigns, setCampaigns] = useState(initialCampaigns);
  const [selectedId, setSelectedId] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All statuses");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<Campaign | null>(null);
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [audience, setAudience] = useState("New customers");
  const [content, setContent] = useState("Hi {{first_name}},\n\nHere are the resources discussed with your account team.");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const selected = campaigns.find((campaign) => campaign.id === selectedId) || campaigns[0];
  const filtered = useMemo(() => campaigns.filter((campaign) =>
    `${campaign.name} ${campaign.audience} ${campaign.owner}`.toLowerCase().includes(search.toLowerCase()) &&
    (status === "All statuses" || campaign.status === status),
  ), [campaigns, search, status]);
  const openEditor = (campaign?: Campaign) => {
    setEditing(campaign || null);
    setName(campaign?.name || "");
    setSubject(campaign?.subject || "");
    setAudience(campaign?.audience || "New customers");
    setEditorOpen(true);
  };
  const save = () => {
    if (editing) setCampaigns((current) => current.map((campaign) => campaign.id === editing.id ? { ...campaign, name, subject, audience, updated: "Just now" } : campaign));
    else {
      const next: Campaign = { id: Date.now(), name, subject, audience, status: "Draft", recipients: audience === "New customers" ? 4 : 8, owner: "Olivia Martin", updated: "Just now" };
      setCampaigns((current) => [next, ...current]);
      setSelectedId(next.id);
    }
    setEditorOpen(false);
    onToast(editing ? "Campaign updated" : "Campaign draft created");
  };
  const duplicate = () => {
    const next = { ...selected, id: Date.now(), name: `${selected.name} copy`, status: "Draft" as CampaignStatus, updated: "Just now" };
    setCampaigns((current) => [next, ...current]);
    setSelectedId(next.id);
    onToast("Campaign duplicated as draft");
  };
  const requestApproval = () => {
    setLoading(true);
    window.setTimeout(() => {
      setCampaigns((current) => current.map((campaign) => campaign.id === selected.id ? { ...campaign, status: "Approval required" } : campaign));
      setLoading(false);
      onToast("Campaign submitted for review");
    }, 500);
  };
  return (
    <main className="module-main campaigns-main">
      <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Customer communication planning</div><h1>Campaigns</h1><p>Create reviewed campaign drafts and manage consented audiences.</p></div><Button variant="primary" onClick={() => openEditor()}><Plus size={15} /> New campaign</Button></div>
      <div className="campaign-layout">
        <section className="panel campaign-library">
          <div className="operations-toolbar"><label className="module-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search campaigns" aria-label="Search campaigns" /></label><label className="toolbar-select"><Filter size={14} /><select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter campaign status"><option>All statuses</option><option>Draft</option><option>Scheduled</option><option>Approval required</option><option>Executing</option><option>Failed</option></select></label></div>
          <div className="campaign-list">{filtered.length ? filtered.map((campaign) => <button className={selected.id === campaign.id ? "active" : ""} key={campaign.id} onClick={() => setSelectedId(campaign.id)}><span className="operation-icon"><Megaphone size={15} /></span><span><strong>{campaign.name}</strong><small>{campaign.audience} · {campaign.recipients} recipients</small></span><Badge tone={toneFor(campaign.status)}>{campaign.status}</Badge></button>) : <div className="module-empty compact"><Megaphone size={24} /><strong>No campaigns found</strong><p>Change your search or status filter.</p><Button size="sm" onClick={() => { setSearch(""); setStatus("All statuses"); }}>Clear filters</Button></div>}</div>
        </section>
        <section className="panel campaign-detail">
          <header><div><div className="campaign-title"><h2>{selected.name}</h2><Badge tone={toneFor(selected.status)}>{selected.status}</Badge></div><p>{selected.subject}</p></div><Button size="icon" variant="ghost" aria-label="Campaign actions" onClick={duplicate}><MoreHorizontal size={16} /></Button></header>
          <div className="campaign-actions"><Button size="sm" disabled={selected.restricted} onClick={() => openEditor(selected)}><Edit3 size={13} /> Edit</Button><Button size="sm" onClick={duplicate}><Copy size={13} /> Duplicate</Button><Button size="sm" onClick={() => setPreviewOpen(true)}><Eye size={13} /> Review</Button><Button size="sm" variant="primary" disabled={selected.restricted || selected.status !== "Draft" || loading} onClick={requestApproval}>{loading ? <LoaderCircle size={13} /> : <BadgeCheck size={13} />} Request approval</Button></div>
          <div className="delivery-unavailable"><Link2Off size={17} /><div><strong>Live delivery is not connected</strong><p>Campaigns can be drafted and reviewed here. Scheduling and execution statuses are prototype records only.</p></div><Badge tone="amber">Unavailable</Badge></div>
          {selected.restricted && <div className="permission-state campaign-state"><ShieldCheck size={17} /><span><strong>Restricted campaign</strong><small>Only campaign administrators can edit this record or change its audience.</small></span></div>}
          {selected.status === "Failed" && <div className="state-banner error"><AlertTriangle size={16} /><span><strong>Prototype execution failed</strong><small>No delivery provider is connected, so this sandbox execution could not continue.</small></span><Button size="sm" disabled>Retry delivery</Button></div>}
          <div className="campaign-grid">
            <section><div className="section-title"><h3>Audience</h3><Users size={15} /></div><div className="audience-card"><div><strong>{selected.audience}</strong><Badge tone="blue">{selected.recipients} recipients</Badge></div><p>Contacts with recorded marketing consent who are not suppressed.</p><button onClick={() => setPreviewOpen(true)}>Preview recipients <ChevronRight size={13} /></button></div></section>
            <section><div className="section-title"><h3>Consent and suppression</h3><ShieldCheck size={15} /></div><div className="consent-stats"><div><strong>{selected.recipients}</strong><span>Eligible</span></div><div><strong>2</strong><span>Suppressed</span></div><div><strong>1</strong><span>Missing consent</span></div></div><div className="suppression-note"><Ban size={14} /> Suppressed contacts are always excluded.</div></section>
            <section className="campaign-content-section"><div className="section-title"><h3>Message content</h3><Mail size={15} /></div><div className="message-preview"><small>Subject</small><strong>{selected.subject}</strong><p>Hi Mina,<br /><br />Here are the workspace resources discussed with your account team.</p><span>Draft content · No live delivery</span></div></section>
            <section><div className="section-title"><h3>Schedule</h3><CalendarClock size={15} /></div><div className="schedule-card"><strong>{selected.status === "Scheduled" ? "Planned for next Tuesday" : "Not scheduled"}</strong><span>{selected.status === "Scheduled" ? "10:00 AM · Organization time zone" : "Approval is required before scheduling"}</span></div><Button size="sm" disabled>Configure live schedule</Button></section>
          </div>
        </section>
      </div>

      <Modal open={editorOpen} title={editing ? "Edit campaign" : "New campaign"} description="Create a local campaign draft for review. No message will be delivered." onClose={() => setEditorOpen(false)}>
        <div className="dialog-body campaign-editor"><label className="field"><span>Campaign name</span><input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="Campaign name" /></label><label className="field"><span>Audience segment</span><select value={audience} onChange={(event) => setAudience(event.target.value)}><option>New customers</option><option>Active evaluation leads</option><option>Consented customers</option><option>Internal review segment</option></select></label><div className="recipient-preview"><Users size={16} /><span><strong>{audience === "New customers" ? "4" : "8"} eligible recipients</strong><small>Consent and suppression rules applied</small></span><button onClick={() => { setEditorOpen(false); setPreviewOpen(true); }}>Preview</button></div><label className="field"><span>Subject</span><input value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Message subject" /></label><label className="field"><span>Content</span><textarea value={content} onChange={(event) => setContent(event.target.value)} /></label><div className="validation-summary"><CheckCircle2 size={16} /><span><strong>Consent rules enabled</strong><small>Suppressed and non-consented contacts will remain excluded.</small></span></div></div>
        <div className="dialog-footer"><Button onClick={() => setEditorOpen(false)}>Cancel</Button><Button variant="primary" disabled={name.trim().length < 3 || subject.trim().length < 3} onClick={save}><Save size={14} /> Save draft</Button></div>
      </Modal>

      {previewOpen && <><button className="drawer-backdrop" aria-label="Close campaign review" onClick={() => setPreviewOpen(false)} /><aside className="drawer campaign-review"><div className="drawer-header"><div><h2>Campaign review</h2><p>{selected.name} · Draft preview</p></div><Button size="icon" variant="ghost" aria-label="Close campaign review" onClick={() => setPreviewOpen(false)}><X size={17} /></Button></div><div className="drawer-content"><div className="delivery-unavailable compact"><Link2Off size={16} /><div><strong>Preview only</strong><p>No delivery or analytics provider is connected.</p></div></div><section className="drawer-section"><h3>Recipient preview</h3><div className="recipient-list">{[["MP","Mina Park","Arcade"],["NF","Nadia Flores","Northstar"],["TB","Theo Brooks","Layers"]].map(([initials,name,company]) => <div key={name}><Avatar initials={initials} tone="blue" /><span><strong>{name}</strong><small>{company} · Consented</small></span><Check size={14} /></div>)}</div><button className="suppressed-row"><Ban size={14} /><span><strong>2 suppressed recipients</strong><small>Excluded by workspace suppression rules</small></span><ChevronRight size={14} /></button></section><section className="drawer-section"><h3>Content review</h3><div className="message-preview"><small>Subject</small><strong>{selected.subject}</strong><p>Hi Mina,<br /><br />Here are the workspace resources discussed with your account team.</p></div></section></div><div className="drawer-footer"><Button onClick={() => setPreviewOpen(false)}>Close</Button><Button variant="primary" disabled={selected.restricted} onClick={() => { setPreviewOpen(false); requestApproval(); }}>Submit for approval</Button></div></aside></>}
    </main>
  );
}
