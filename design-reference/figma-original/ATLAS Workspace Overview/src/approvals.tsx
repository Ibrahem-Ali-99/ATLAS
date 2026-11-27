import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Ban,
  Building2,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  Code2,
  Database,
  FileCheck2,
  Filter,
  LoaderCircle,
  LockKeyhole,
  Search,
  ShieldCheck,
  Target,
  UserRound,
  X,
  XCircle,
} from "lucide-react";
import { appConfig } from "./appConfig";
import { Avatar, Badge, Button, Modal, type Tone } from "./components";

type ApprovalStatus = "Pending" | "Approved" | "Rejected" | "Executed" | "Failed";
type Approval = {
  id: number;
  title: string;
  action: string;
  requester: string;
  company: string;
  status: ApprovalStatus;
  created: string;
  destination: string;
  rationale: string;
  restricted?: boolean;
};

const initialApprovals: Approval[] = [
  { id: 1, title: "Create follow-up task", action: "Create a task due today for Mina Park", requester: "ATLAS Assistant", company: "Arcade", status: "Pending", created: "8 min ago", destination: "CRM · Tasks", rationale: "The enterprise inquiry has not received a staff response." },
  { id: 2, title: "Update opportunity stage", action: "Move Northstar agreement to Qualified", requester: "Qualification workflow", company: "Northstar", status: "Pending", created: "42 min ago", destination: "CRM · Opportunities", rationale: "Required qualification fields are complete and a discovery call was logged.", restricted: true },
  { id: 3, title: "Send inquiry follow-up", action: "Send the reviewed response to Nadia Flores", requester: "Inbox assistant", company: "Northstar", status: "Executed", created: "Yesterday", destination: "Inbox · Email", rationale: "A staff member approved the final response." },
  { id: 4, title: "Archive inactive lead", action: "Archive Ellis Ward’s inactive lead", requester: "Lead hygiene workflow", company: "Layers", status: "Rejected", created: "Feb 20", destination: "CRM · Leads", rationale: "No customer activity has been recorded in the configured review period." },
  { id: 5, title: "Create onboarding task", action: "Create an onboarding preparation task", requester: "Opportunity workflow", company: "Arcade", status: "Failed", created: "Feb 19", destination: "CRM · Tasks", rationale: "The linked opportunity moved to Won." },
  { id: 6, title: "Assign account owner", action: "Assign Maya Chen to the Vertex account", requester: "Routing workflow", company: "Vertex", status: "Approved", created: "Feb 18", destination: "CRM · Companies", rationale: "The security inquiry is currently assigned to Maya Chen." },
];

const toneFor = (status: ApprovalStatus): Tone =>
  status === "Pending" ? "amber" : status === "Executed" || status === "Approved" ? "green" : "red";

export function ApprovalsWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const [approvals, setApprovals] = useState(initialApprovals);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All statuses");
  const [selected, setSelected] = useState<Approval | null>(null);
  const [reviewed, setReviewed] = useState<number[]>([]);
  const [confirm, setConfirm] = useState<"approve" | "reject" | null>(null);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const filtered = useMemo(() => approvals.filter((approval) =>
    `${approval.title} ${approval.company} ${approval.requester}`.toLowerCase().includes(search.toLowerCase()) &&
    (status === "All statuses" || approval.status === status),
  ), [approvals, search, status]);
  const patch = (id: number, nextStatus: ApprovalStatus) => {
    setApprovals((current) => current.map((approval) => approval.id === id ? { ...approval, status: nextStatus } : approval));
    setSelected((current) => current?.id === id ? { ...current, status: nextStatus } : current);
  };
  const decide = () => {
    if (!selected || !confirm) return;
    patch(selected.id, confirm === "approve" ? "Approved" : "Rejected");
    onToast(confirm === "approve" ? "Approval confirmed" : "Request rejected");
    setConfirm(null);
    setReason("");
  };
  const retry = () => {
    if (!selected) return;
    setLoading(true);
    window.setTimeout(() => {
      patch(selected.id, "Executed");
      setLoading(false);
      onToast("Execution retry completed");
    }, 700);
  };
  return (
    <main className="module-main operations-main">
      <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Governed actions</div><h1>Approvals</h1><p>Review proposed workspace changes before they are executed.</p></div><Badge tone="amber">{approvals.filter((item) => item.status === "Pending").length} pending</Badge></div>
      <section className="panel operations-panel">
        <div className="operations-toolbar"><label className="module-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search approval requests" aria-label="Search approval requests" />{search && <button onClick={() => setSearch("")} aria-label="Clear search"><X size={14} /></button>}</label><label className="toolbar-select"><Filter size={14} /><select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter by approval status"><option>All statuses</option><option>Pending</option><option>Approved</option><option>Rejected</option><option>Executed</option><option>Failed</option></select></label></div>
        <div className="operations-table approvals-table" role="table" aria-label="Approval review queue">
          <div className="operations-row head" role="row"><span>Request</span><span>Requester</span><span>Affected account</span><span>Status</span><span>Created</span><span /></div>
          {filtered.length ? filtered.map((approval) => <button className="operations-row" role="row" key={approval.id} onClick={() => { setSelected(approval); setReason(""); }}>
            <span className="operation-primary"><span className="operation-icon"><FileCheck2 size={15} /></span><span><strong>{approval.title}</strong><small>{approval.action}</small></span></span>
            <span>{approval.requester}</span><span>{approval.company}</span><span><Badge tone={toneFor(approval.status)}>{approval.status}</Badge></span><span>{approval.created}</span><ChevronRight size={15} />
          </button>) : <div className="module-empty"><BadgeCheck size={25} /><strong>No approval requests found</strong><p>Change the search or status filter to see other requests.</p><Button size="sm" onClick={() => { setSearch(""); setStatus("All statuses"); }}>Clear filters</Button></div>}
        </div>
      </section>

      {selected && <><button className="drawer-backdrop" aria-label="Close approval details" onClick={() => setSelected(null)} /><aside className="drawer operations-drawer" aria-label={`${selected.title} approval details`}>
        <div className="drawer-header"><div><h2>{selected.title}</h2><p>Approval request AT-{selected.id.toString().padStart(4, "0")}</p></div><Button size="icon" variant="ghost" aria-label="Close approval details" onClick={() => setSelected(null)}><X size={17} /></Button></div>
        <div className="drawer-content">
          <div className="detail-status"><Badge tone={toneFor(selected.status)}>{selected.status}</Badge><span>Created {selected.created}</span></div>
          {selected.restricted && <div className="permission-state"><LockKeyhole size={18} /><span><strong>Administrator review required</strong><small>You can inspect this request, but only an administrator can approve or reject it.</small></span></div>}
          <section className="approval-detail-section"><h3>Proposed action</h3><div className="proposed-change"><Target size={17} /><div><strong>{selected.action}</strong><p>Destination: {selected.destination}</p></div></div></section>
          <section className="approval-detail-section"><h3>Rationale</h3><p>{selected.rationale}</p></section>
          <section className="approval-detail-section"><h3>Evidence</h3><div className="evidence-list"><div><Clock3 size={14} /><span><strong>Recent customer activity</strong><small>Customer timeline · {selected.created}</small></span></div><div><Database size={14} /><span><strong>Linked CRM record</strong><small>{selected.company} · Current workspace record</small></span></div></div></section>
          <section className="approval-detail-section"><h3>Affected records</h3><button className="affected-record" onClick={() => onToast(`Opening ${selected.company} record`)}><Building2 size={15} /><span><strong>{selected.company}</strong><small>Company record</small></span><ChevronRight size={14} /></button></section>
          <section className="approval-detail-section"><h3>Payload</h3><pre><code><Code2 size={13} />{`{\n  "record": "${selected.company}",\n  "action": "${selected.title.toLowerCase()}",\n  "delivery": "sandbox"\n}`}</code></pre></section>
          {selected.status === "Failed" && <div className="state-banner error"><CircleAlert size={16} /><span><strong>Execution failed</strong><small>The destination rejected the request because the linked task was unavailable.</small></span><Button size="sm" disabled={loading} onClick={retry}>{loading ? <LoaderCircle size={13} /> : <ArrowRight size={13} />} Retry</Button></div>}
          {selected.status === "Executed" && <div className="execution-result"><CheckCircle2 size={17} /><span><strong>Execution completed</strong><small>The reviewed action was applied to {selected.destination}.</small></span></div>}
          {selected.status === "Rejected" && <div className="execution-result rejected"><XCircle size={17} /><span><strong>Request rejected</strong><small>No workspace changes were applied.</small></span></div>}
          {selected.status === "Pending" && !reviewed.includes(selected.id) && <div className="review-gate"><ShieldCheck size={18} /><div><strong>Review required</strong><p>Inspect the rationale, evidence, affected records, destination, and payload before continuing.</p></div><Button size="sm" onClick={() => setReviewed([...reviewed, selected.id])}><Check size={13} /> Mark review complete</Button></div>}
        </div>
        <div className="drawer-footer"><Button disabled={selected.status !== "Pending" || selected.restricted || !reviewed.includes(selected.id)} onClick={() => setConfirm("reject")}><Ban size={14} /> Reject</Button><Button variant="primary" disabled={selected.status !== "Pending" || selected.restricted || !reviewed.includes(selected.id)} onClick={() => setConfirm("approve")}><Check size={14} /> Approve</Button></div>
      </aside></>}

      <Modal open={confirm !== null} title={confirm === "approve" ? "Approve request?" : "Reject request?"} description={confirm === "approve" ? "The request will be approved for controlled execution." : "Explain why this request should not proceed."} onClose={() => setConfirm(null)}>
        <div className="dialog-body">{confirm === "approve" ? <div className="review-callout"><ShieldCheck size={17} /><span><strong>Review complete</strong><p>You reviewed the evidence, affected records, destination, and payload.</p></span></div> : <label className="field"><span>Rejection reason</span><textarea autoFocus value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Provide a reason for the requester" /></label>}</div>
        <div className="dialog-footer"><Button onClick={() => setConfirm(null)}>Cancel</Button><Button variant={confirm === "approve" ? "primary" : "danger"} disabled={confirm === "reject" && reason.trim().length < 8} onClick={decide}>{confirm === "approve" ? "Confirm approval" : "Reject request"}</Button></div>
      </Modal>
    </main>
  );
}
