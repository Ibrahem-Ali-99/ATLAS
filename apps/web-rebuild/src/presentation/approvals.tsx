import { useEffect, useMemo, useState } from "react";
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
import { decideApprovalRow, executeApprovalRow, failureMessage, listApprovalRows, loadTeam } from "@/data/resources";
import { appConfig } from "./appConfig";
import { Avatar, Badge, Button, Modal, type Tone } from "./components";

type ApprovalStatus = "Pending" | "Approved" | "Rejected" | "Executed" | "Failed";
type Approval = {
  id: string;
  title: string;
  action: string;
  requester: string;
  company: string;
  status: ApprovalStatus;
  created: string;
  destination: string;
  rationale: string;
  restricted?: boolean;
  payload: Record<string, unknown>;
};

function mapApproval(row: { id: string; status: string; action_type: string; payload: Record<string, unknown>; created_at: string; decision_note: string | null; execution_error: string | null; requested_by: string }, names: Map<string, string>): Approval {
  const text = (key: string) => typeof row.payload[key] === "string" ? String(row.payload[key]) : "";
  const statusMap: Record<string, ApprovalStatus> = { pending: "Pending", approved: "Approved", rejected: "Rejected", executed: "Executed", failed: "Failed", executing: "Approved", needs_attention: "Failed", expired: "Rejected" };
  return { id: row.id, title: text("title") || text("subject") || row.action_type.replaceAll("_", " "), action: text("body") || text("summary") || row.action_type.replaceAll("_", " "), requester: names.get(row.requested_by) || "Workspace member", company: text("company_name") || text("recipient") || "Workspace record", status: statusMap[row.status] || "Pending", created: row.created_at.slice(0, 10), destination: row.action_type.replaceAll("_", " "), rationale: row.decision_note || row.execution_error || "Stored approval request.", payload: row.payload };
}

const toneFor = (status: ApprovalStatus): Tone =>
  status === "Pending" ? "amber" : status === "Executed" || status === "Approved" ? "green" : "red";

export function ApprovalsWorkspace({ onToast, onOpenCrm }: { onToast: (message: string) => void; onOpenCrm?: (query: string) => void }) {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All statuses");
  const [selected, setSelected] = useState<Approval | null>(null);
  const [reviewed, setReviewed] = useState<string[]>([]);
  const [confirm, setConfirm] = useState<"approve" | "reject" | null>(null);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const filtered = useMemo(() => approvals.filter((approval) =>
    `${approval.title} ${approval.company} ${approval.requester}`.toLowerCase().includes(search.toLowerCase()) &&
    (status === "All statuses" || approval.status === status),
  ), [approvals, search, status]);
  const reload = () => Promise.all([listApprovalRows(), loadTeam()]).then(([rows, team]) => setApprovals(rows.map((row) => mapApproval(row, new Map(team.map((member) => [member.user_id, member.full_name]))))));
  useEffect(() => { reload().catch((error: unknown) => onToast(failureMessage(error))); }, [onToast]);
  const decide = () => {
    if (!selected || !confirm) return;
    setLoading(true);
    void decideApprovalRow(selected.id, confirm, reason).then(() => { onToast(confirm === "approve" ? "Approval confirmed" : "Request rejected"); setConfirm(null); setReason(""); return reload(); }).catch((error: unknown) => onToast(failureMessage(error))).finally(() => setLoading(false));
  };
  const retry = () => {
    if (!selected) return;
    setLoading(true);
    void executeApprovalRow(selected.id).then(() => { onToast("Execution recorded"); return reload(); }).catch((error: unknown) => onToast(failureMessage(error))).finally(() => setLoading(false));
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
          <section className="approval-detail-section"><h3>Affected records</h3><button className="affected-record" onClick={() => onOpenCrm ? onOpenCrm(selected.company) : onToast(selected.company)}><Building2 size={15} /><span><strong>{selected.company}</strong><small>{selected.destination}</small></span><ChevronRight size={14} /></button></section>
          <section className="approval-detail-section"><h3>Payload</h3><pre><code><Code2 size={13} />{JSON.stringify(selected.payload, null, 2)}</code></pre></section>
          {selected.status === "Failed" && <div className="state-banner error"><CircleAlert size={16} /><span><strong>Execution failed</strong><small>{selected.rationale}</small></span><Button size="sm" disabled={loading} onClick={retry}>{loading ? <LoaderCircle size={13} /> : <ArrowRight size={13} />} Retry</Button></div>}
          {selected.status === "Executed" && <div className="execution-result"><CheckCircle2 size={17} /><span><strong>Execution completed</strong><small>The reviewed action was applied to {selected.destination}.</small></span></div>}
          {selected.status === "Rejected" && <div className="execution-result rejected"><XCircle size={17} /><span><strong>Request rejected</strong><small>No workspace changes were applied.</small></span></div>}
          {selected.status === "Pending" && !reviewed.includes(selected.id) && <div className="review-gate"><ShieldCheck size={18} /><div><strong>Review required</strong><p>Inspect the rationale, evidence, affected records, destination, and payload before continuing.</p></div><Button size="sm" onClick={() => setReviewed([...reviewed, selected.id])}><Check size={13} /> Mark review complete</Button></div>}
        </div>
        <div className="drawer-footer">{selected.status === "Approved" ? <Button variant="primary" disabled={loading} onClick={retry}>{loading ? <LoaderCircle size={14} /> : <Check size={14} />} Execute stored action</Button> : <><Button disabled={selected.status !== "Pending" || selected.restricted || !reviewed.includes(selected.id)} onClick={() => setConfirm("reject")}><Ban size={14} /> Reject</Button><Button variant="primary" disabled={selected.status !== "Pending" || selected.restricted || !reviewed.includes(selected.id)} onClick={() => setConfirm("approve")}><Check size={14} /> Approve</Button></>}</div>
      </aside></>}

      <Modal open={confirm !== null} title={confirm === "approve" ? "Approve request?" : "Reject request?"} description={confirm === "approve" ? "The request will be approved for controlled execution." : "Explain why this request should not proceed."} onClose={() => setConfirm(null)}>
        <div className="dialog-body">{confirm === "approve" ? <div className="review-callout"><ShieldCheck size={17} /><span><strong>Review complete</strong><p>You reviewed the evidence, affected records, destination, and payload.</p></span></div> : <label className="field"><span>Rejection reason</span><textarea autoFocus value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Provide a reason for the requester" /></label>}</div>
        <div className="dialog-footer"><Button onClick={() => setConfirm(null)}>Cancel</Button><Button variant={confirm === "approve" ? "primary" : "danger"} disabled={confirm === "reject" && reason.trim().length < 8} onClick={decide}>{confirm === "approve" ? "Confirm approval" : "Reject request"}</Button></div>
      </Modal>
    </main>
  );
}
