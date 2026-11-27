import { useEffect, useMemo, useState } from "react";
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
import { campaignTransport, cancelCampaignRow, createCampaignRow, failureMessage, listCampaignDeliveries, listCampaignRows, listSegments, previewCampaignRow, scheduleCampaignSandbox, updateCampaignRow, type SegmentRow } from "@/data/resources";
import { Avatar, Badge, Button, Modal, type Tone } from "./components";

type CampaignStatus = "Draft" | "Scheduled" | "Approval required" | "Executing" | "Failed";
type Campaign = {
  id: string;
  name: string;
  status: CampaignStatus;
  audience: string;
  recipients: number;
  owner: string;
  updated: string;
  subject: string;
  body: string;
  segmentId: string | null;
  scheduledAt: string | null;
  restricted?: boolean;
};

const campaignStatus = (value: string): CampaignStatus => value === "scheduled" ? "Scheduled" : value === "sending" || value === "running" ? "Executing" : value === "failed" ? "Failed" : value === "pending_approval" ? "Approval required" : "Draft";

const toneFor = (status: CampaignStatus): Tone =>
  status === "Draft" ? "neutral" : status === "Scheduled" ? "blue" : status === "Approval required" ? "amber" : status === "Executing" ? "purple" : "red";

export function CampaignsWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [segments, setSegments] = useState<SegmentRow[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [transport, setTransport] = useState("Checking delivery");
  const [preview, setPreview] = useState<{ eligible: number; suppressed: number; missing_consent: number } | null>(null);
  const [deliveries, setDeliveries] = useState<{ id: string; email: string; status: string }[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All statuses");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<Campaign | null>(null);
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [segmentId, setSegmentId] = useState("");
  const [content, setContent] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const emptyCampaign: Campaign = { id: "", name: "No campaigns", status: "Draft", audience: "No segment", recipients: 0, owner: "Workspace", updated: "", subject: "", body: "", segmentId: null, scheduledAt: null };
  const selected = campaigns.find((campaign) => campaign.id === selectedId) || campaigns[0] || emptyCampaign;
  const mapRow = (row: { id: string; name: string; status: string; segment_id: string | null; delivery_mode: string; updated_at: string; subject: string | null; body: string | null; scheduled_at?: string | null }, audienceName?: string): Campaign => ({
    id: row.id,
    name: row.name,
    status: campaignStatus(row.status),
    audience: audienceName || segments.find((segment) => segment.id === row.segment_id)?.name || (row.segment_id ? "Saved segment" : "No segment"),
    recipients: 0,
    owner: row.delivery_mode,
    updated: row.updated_at.slice(0, 10),
    subject: row.subject || "",
    body: row.body || "",
    segmentId: row.segment_id,
    scheduledAt: row.scheduled_at ?? null,
  });
  const reload = () => Promise.all([listCampaignRows(), listSegments()]).then(([rows, nextSegments]) => {
    setSegments(nextSegments);
    const next = rows.map((row) => mapRow(row, nextSegments.find((segment) => segment.id === row.segment_id)?.name));
    setCampaigns(next);
    setSelectedId((current) => next.some((campaign) => campaign.id === current) ? current : next[0]?.id || "");
  });
  useEffect(() => {
    reload().catch((error: unknown) => onToast(failureMessage(error)));
    campaignTransport().then((result) => setTransport(`${result.mode}${result.ready ? " · ready" : ""}${result.detail ? ` · ${result.detail}` : ""}`)).catch((error: unknown) => setTransport(failureMessage(error)));
  }, [onToast]);
  const filtered = useMemo(() => campaigns.filter((campaign) =>
    `${campaign.name} ${campaign.audience} ${campaign.owner}`.toLowerCase().includes(search.toLowerCase()) &&
    (status === "All statuses" || campaign.status === status),
  ), [campaigns, search, status]);
  const openEditor = (campaign?: Campaign) => {
    setEditing(campaign || null);
    setName(campaign?.name || "");
    setSubject(campaign?.subject || "");
    setContent(campaign?.body || "");
    setSegmentId(campaign?.segmentId || "");
    setEditorOpen(true);
  };
  const save = () => {
    const body = { name, subject, body: content, segment_id: segmentId || null };
    const request = editing ? updateCampaignRow(editing.id, body) : createCampaignRow(body);
    void request.then((row) => {
      const next = mapRow(row);
      setCampaigns((current) => editing ? current.map((campaign) => campaign.id === row.id ? { ...next, recipients: campaign.recipients } : campaign) : [next, ...current]);
      setSelectedId(row.id);
      setEditorOpen(false);
      onToast(editing ? "Campaign updated" : "Campaign draft created");
    }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const duplicate = () => {
    if (!selected.id) return;
    void createCampaignRow({ name: `${selected.name} copy`.slice(0, 120), subject: selected.subject || "Copy", body: selected.body, segment_id: selected.segmentId }).then((row) => {
      setCampaigns((current) => [mapRow(row), ...current]);
      setSelectedId(row.id);
      onToast("Campaign draft duplicated");
    }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  useEffect(() => {
    if (!selected.id) return;
    previewCampaignRow(selected.id).then((result) => {
      setPreview(result);
      setCampaigns((current) => current.map((campaign) => campaign.id === selected.id ? { ...campaign, recipients: result.eligible } : campaign));
    }).catch(() => setPreview(null));
  }, [selected.id]);
  const requestApproval = () => {
    if (!selected.id) return;
    setLoading(true);
    void scheduleCampaignSandbox(selected.id).then(() => { onToast("Sandbox schedule recorded. Live delivery stayed disabled."); return reload(); }).catch((error: unknown) => onToast(failureMessage(error))).finally(() => setLoading(false));
  };
  const cancelSchedule = () => {
    if (!selected.id) return;
    setLoading(true);
    void cancelCampaignRow(selected.id).then(() => { onToast("Campaign schedule cancelled"); return reload(); }).catch((error: unknown) => onToast(failureMessage(error))).finally(() => setLoading(false));
  };
  useEffect(() => {
    if (!previewOpen || !selected.id) return;
    listCampaignDeliveries(selected.id).then(setDeliveries).catch(() => setDeliveries([]));
  }, [previewOpen, selected.id]);
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
          <div className="campaign-actions"><Button size="sm" disabled={selected.restricted || !selected.id} onClick={() => openEditor(selected)}><Edit3 size={13} /> Edit</Button><Button size="sm" disabled={!selected.id} onClick={duplicate}><Copy size={13} /> Duplicate</Button><Button size="sm" disabled={!selected.id} onClick={() => setPreviewOpen(true)}><Eye size={13} /> Review</Button>{selected.status === "Scheduled" ? <Button size="sm" disabled={loading} onClick={cancelSchedule}>Cancel schedule</Button> : <Button size="sm" variant="primary" disabled={selected.restricted || selected.status !== "Draft" || !selected.id || loading} onClick={requestApproval}>{loading ? <LoaderCircle size={13} /> : <BadgeCheck size={13} />} Request approval</Button>}</div>
          <div className="delivery-unavailable"><Link2Off size={17} /><div><strong>Delivery transport</strong><p>{transport}. Live customer delivery stays disabled.</p></div><Badge tone="amber">{transport.startsWith("live") ? "Live" : "Sandbox"}</Badge></div>
          {selected.restricted && <div className="permission-state campaign-state"><ShieldCheck size={17} /><span><strong>Restricted campaign</strong><small>Only campaign administrators can edit this record or change its audience.</small></span></div>}
          {selected.status === "Failed" && <div className="state-banner error"><AlertTriangle size={16} /><span><strong>Prototype execution failed</strong><small>No delivery provider is connected, so this sandbox execution could not continue.</small></span><Button size="sm" disabled>Retry delivery</Button></div>}
          <div className="campaign-grid">
            <section><div className="section-title"><h3>Audience</h3><Users size={15} /></div><div className="audience-card"><div><strong>{selected.audience}</strong><Badge tone="blue">{selected.recipients} recipients</Badge></div><p>Contacts with recorded marketing consent who are not suppressed.</p><button onClick={() => setPreviewOpen(true)}>Preview recipients <ChevronRight size={13} /></button></div></section>
            <section><div className="section-title"><h3>Consent and suppression</h3><ShieldCheck size={15} /></div><div className="consent-stats"><div><strong>{preview?.eligible ?? "—"}</strong><span>Eligible</span></div><div><strong>{preview?.suppressed ?? "—"}</strong><span>Suppressed</span></div><div><strong>{preview?.missing_consent ?? "—"}</strong><span>Missing consent</span></div></div><div className="suppression-note"><Ban size={14} /> Suppressed contacts are always excluded.</div></section>
            <section className="campaign-content-section"><div className="section-title"><h3>Message content</h3><Mail size={15} /></div><div className="message-preview"><small>Subject</small><strong>{selected.subject || "No subject"}</strong><p style={{ whiteSpace: "pre-wrap" }}>{selected.body || "No message body is stored."}</p><span>Stored draft · No live delivery</span></div></section>
            <section><div className="section-title"><h3>Schedule</h3><CalendarClock size={15} /></div><div className="schedule-card"><strong>{selected.scheduledAt ? new Date(selected.scheduledAt).toLocaleString() : "Not scheduled"}</strong><span>{selected.status === "Scheduled" ? "Stored schedule" : "A sandbox schedule can be recorded from this draft"}</span></div><Button size="sm" disabled>Configure live schedule</Button></section>
          </div>
        </section>
      </div>

      <Modal open={editorOpen} title={editing ? "Edit campaign" : "New campaign"} description="Create a local campaign draft for review. No message will be delivered." onClose={() => setEditorOpen(false)}>
        <div className="dialog-body campaign-editor"><label className="field"><span>Campaign name</span><input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="Campaign name" /></label><label className="field"><span>Audience segment</span><select value={segmentId} onChange={(event) => setSegmentId(event.target.value)}><option value="">No segment</option>{segments.map((segment) => <option key={segment.id} value={segment.id}>{segment.name}</option>)}</select></label><div className="recipient-preview"><Users size={16} /><span><strong>{editing && preview ? `${preview.eligible} eligible recipients` : "Counted after save"}</strong><small>Consent and suppression come from the saved segment.</small></span></div><label className="field"><span>Subject</span><input value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Message subject" /></label><label className="field"><span>Content</span><textarea value={content} onChange={(event) => setContent(event.target.value)} /></label><div className="validation-summary"><CheckCircle2 size={16} /><span><strong>Consent rules enabled</strong><small>Suppressed and non-consented contacts stay excluded.</small></span></div></div>
        <div className="dialog-footer"><Button onClick={() => setEditorOpen(false)}>Cancel</Button><Button variant="primary" disabled={name.trim().length < 3 || subject.trim().length < 3} onClick={save}><Save size={14} /> Save draft</Button></div>
      </Modal>

      {previewOpen && <><button className="drawer-backdrop" aria-label="Close campaign review" onClick={() => setPreviewOpen(false)} /><aside className="drawer campaign-review"><div className="drawer-header"><div><h2>Campaign review</h2><p>{selected.name} · Stored preview</p></div><Button size="icon" variant="ghost" aria-label="Close campaign review" onClick={() => setPreviewOpen(false)}><X size={17} /></Button></div><div className="drawer-content"><div className="delivery-unavailable compact"><Link2Off size={16} /><div><strong>{transport}</strong><p>Live customer delivery stays disabled.</p></div></div><section className="drawer-section"><h3>Recipient preview</h3><div className="consent-stats"><div><strong>{preview?.eligible ?? "—"}</strong><span>Eligible</span></div><div><strong>{preview?.suppressed ?? "—"}</strong><span>Suppressed</span></div><div><strong>{preview?.missing_consent ?? "—"}</strong><span>Missing consent</span></div></div>{deliveries.length ? <div className="recipient-list">{deliveries.map((delivery) => <div key={delivery.id}><Avatar initials={delivery.email.slice(0, 2).toUpperCase()} tone="blue" /><span><strong>{delivery.email}</strong><small>{delivery.status}</small></span><Check size={14} /></div>)}</div> : <p className="detail-copy">No delivery rows are stored for this campaign.</p>}</section><section className="drawer-section"><h3>Content review</h3><div className="message-preview"><small>Subject</small><strong>{selected.subject || "No subject"}</strong><p style={{ whiteSpace: "pre-wrap" }}>{selected.body || "No message body is stored."}</p></div></section></div><div className="drawer-footer"><Button onClick={() => setPreviewOpen(false)}>Close</Button><Button variant="primary" disabled={selected.restricted || selected.status !== "Draft"} onClick={() => { setPreviewOpen(false); requestApproval(); }}>Submit for approval</Button></div></aside></>}
    </main>
  );
}
