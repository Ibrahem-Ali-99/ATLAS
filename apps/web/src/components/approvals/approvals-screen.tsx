"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ChevronRight, FileCheck2, Filter, Search } from "lucide-react";
import { useRef, useState } from "react";

import { Pager } from "@/components/pager";
import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { executionSummary, type Approval, type ApprovalStatus } from "@/lib/agent";
import { decideApproval, executeApproval, getApproval, listApprovals, resumeAgentRun } from "@/lib/agent-api";
import { useWorkspace } from "@/lib/use-workspace";
import { actionLabel, proposalChange, proposalRisk, proposalTarget } from "@/lib/approval-presentation";
import { listWorkflowReviews } from "@/lib/workflow-definitions";

export function ApprovalsScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  if (!organizationId) {
    return <Skeleton className="h-40 w-full" />;
  }
  return <ApprovalsBody key={organizationId} organizationId={organizationId} isAdmin={workspace.role === "admin"} />;
}

function ApprovalsBody({ organizationId, isAdmin }: {
  organizationId: string;
  isAdmin: boolean;
}) {
  const router = useRouter();
  const selectedId = useSearchParams().get("approval");
  const [status, setStatus] = useState<ApprovalStatus | "">("pending");
  const [note, setNote] = useState<{ id: string; text: string } | null>(null);
  const [notice, setNotice] = useState<{ id: string; text: string } | null>(null);
  const select = (id: string | null) => {
    setNote(null);
    setNotice(null);
    router.replace(id ? `/approvals?approval=${encodeURIComponent(id)}` : "/approvals", { scroll: false });
  };
  const queryClient = useQueryClient();
  const executeGuard = useRef(false);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const approvals = useQuery({
    queryKey: ["approvals", organizationId, status, page],
    queryFn: () => listApprovals(organizationId, { status, page }),
    refetchInterval: (query) => {
      const selected = query.state.data?.items.find((item) => item.id === selectedId);
      return selected?.status === "executing" ? 1000 : false;
    },
  });
  const detail = useQuery({
    queryKey: ["approval", organizationId, selectedId],
    queryFn: () => getApproval(organizationId, selectedId ?? ""),
    enabled: Boolean(selectedId),
    refetchInterval: (query) => query.state.data?.status === "executing" ? 1000 : false,
  });
  const workflowReviews = useQuery({
    queryKey: ["workflow-reviews", organizationId],
    queryFn: () => listWorkflowReviews(organizationId),
    enabled: isAdmin,
  });
  const needle = query.trim().toLowerCase();
  const visible = (approvals.data?.items ?? []).filter((approval) => {
    if (needle.length === 0) {
      return true;
    }
    const haystack = `${approval.action_type} ${JSON.stringify(approval.payload)}`.toLowerCase();
    return haystack.includes(needle);
  });
  const selected = detail.data ?? visible.find((item) => item.id === selectedId)
    ?? approvals.data?.items.find((item) => item.id === selectedId)
    ?? null;
  const decide = useMutation({
    mutationFn: (decision: "approve" | "reject") => {
      if (!selected) {
        throw new Error("Select an approval first");
      }
      return decideApproval(organizationId, selected.id, decision, note?.id === selected.id ? note.text : "");
    },
    onSuccess: async (approval, decision) => {
      setNote(null);
      // Keep the decided proposal visible and selected. The default Pending
      // filter would otherwise remove it from the loaded list immediately,
      // unmounting the detail panel before the operator can execute it.
      setStatus("");
      queryClient.setQueryData(["approval", organizationId, approval.id], approval);
      setNotice({ id: approval.id, text: decision === "approve"
          ? "Approved. Execute writes the stored payload. Nothing is sent until then."
          : "Rejected. No CRM change or external action was written.",
      });
      await queryClient.invalidateQueries({ queryKey: ["approvals", organizationId] });
      await queryClient.invalidateQueries({ queryKey: ["approval", organizationId, selectedId] });
      await queryClient.invalidateQueries({ queryKey: ["agent-runs", organizationId] });
    },
  });
  const resume = useMutation({
    mutationFn: (runId: string) => resumeAgentRun(organizationId, runId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["approvals", organizationId] });
      await queryClient.invalidateQueries({ queryKey: ["agent-runs", organizationId] });
    },
  });
  const execute = useMutation({
    mutationFn: async (approvalId: string) => {
      if (executeGuard.current) {
        throw new Error("This approval is already being executed.");
      }
      executeGuard.current = true;
      try {
        return await executeApproval(organizationId, approvalId);
      } catch (error) {
        executeGuard.current = false;
        throw error;
      }
    },
    onSuccess: async (approval) => {
      executeGuard.current = false;
      queryClient.setQueryData(["approval", organizationId, approval.id], approval);
      setNotice({ id: approval.id, text: approval.status === "executing"
          ? "Queued. The sandbox worker is processing the stored result."
          : "Executed. The stored result is on this approval.",
      });
      await queryClient.invalidateQueries({ queryKey: ["approvals", organizationId] });
      await queryClient.invalidateQueries({ queryKey: ["agent-runs", organizationId] });
      await queryClient.invalidateQueries({ queryKey: ["automations", organizationId] });
      if (approval.action_type === "create_lead" || approval.action_type === "update_lead") {
        await queryClient.invalidateQueries({ queryKey: ["leads", organizationId] });
      }
    },
  });

  const pendingCount = (approvals.data?.items ?? []).filter((item) => item.status === "pending").length;
  return (
    <div>
    <PageHeader title="Approvals" eyebrow="Governed actions" actions={
      pendingCount > 0 ? <span className="badge badge-amber">{pendingCount} pending</span> : <Button asChild variant="outline"><Link href="/agent-runs">View execution history</Link></Button>
    }>Review proposed workspace changes before they are executed.</PageHeader>
    {workflowReviews.error ? <RequestError error={workflowReviews.error} /> : null}
    {workflowReviews.data?.length ? <aside className="panel" aria-label="Pending workflow approvals" style={{ marginBottom: 12, padding: 14 }}>
      <h2>Workflows awaiting approval</h2>
      <div className="evidence-list" style={{ marginTop: 10 }}>
        {workflowReviews.data.map((entry) => <div key={entry.id}>
          <span>
            <Link href={`/workflows?workflow=${entry.workflow_id}&run=${entry.id}${entry.archived ? "&archived=1" : ""}`}><strong>{entry.name}</strong></Link>
            {entry.note ? <small>{entry.note}</small> : null}
          </span>
        </div>)}
      </div>
    </aside> : null}
    <section className="panel operations-panel">
      <div className="operations-toolbar">
        <label className="module-search">
          <Search size={15} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search approval requests" aria-label="Filter loaded decisions" />
        </label>
        <label className="toolbar-select">
          <Filter size={14} />
          <select aria-label="Filter approvals" value={status} onChange={(event) => { setStatus(event.target.value as ApprovalStatus | ""); setPage(1); }}>
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="executed">Executed</option>
            <option value="executing">Executing</option>
            <option value="failed">Failed</option>
            <option value="needs_attention">Needs attention</option>
            <option value="expired">Expired</option>
          </select>
        </label>
      </div>
      {approvals.isPending ? <div className="module-empty compact" role="status"><strong>Loading requests</strong></div> : null}
      {approvals.isError ? <div style={{ padding: 14 }}><RequestError error={approvals.error} /></div> : null}
      {approvals.data && visible.length === 0 ? (
        <div className="module-empty"><strong>No approval requests found</strong><p>Change the search or status filter to see other requests.</p></div>
      ) : null}
      {visible.length > 0 ? (
        <div className="operations-table approvals-table" role="table" aria-label="Approval review queue">
          <div className="operations-row head" role="row"><span>Request</span><span>Destination</span><span>Account</span><span>Status</span><span>Created</span><span /></div>
          {visible.map((approval) => (
            <button key={approval.id} type="button" role="row" data-approval-id={approval.id} aria-current={approval.id === selectedId || undefined} className="operations-row" onClick={() => select(approval.id)}>
              <span className="operation-primary"><span className="operation-icon"><FileCheck2 size={15} /></span><span><strong>{actionLabel(approval.action_type)}</strong><small>{proposalChange(approval.action_type, approval.payload)}</small></span></span>
              <span>{scopeLabel(approval)}</span>
              <span>{proposalTarget(approval.payload)}</span>
              <span><span className={statusBadge(approval.status)}>{approval.status.replaceAll("_", " ")}</span></span>
              <span>{new Date(approval.created_at).toLocaleDateString()}</span>
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
      ) : null}
      {approvals.data ? <Pager page={approvals.data.page} pageSize={approvals.data.page_size} total={approvals.data.total} onPage={setPage} /> : null}
    </section>
    {selectedId ? <button type="button" className="drawer-backdrop" aria-label="Close approval details" onClick={() => select(null)} /> : null}
    {selectedId ? (
      <aside className="drawer operations-drawer" aria-label="Approval details">
        <div className="drawer-header">
          <div>
            <h2>{selected ? actionLabel(selected.action_type) : "Approval"}</h2>
            <p>{selected ? `Requested ${new Date(selected.created_at).toLocaleString()}` : "Loading request"}</p>
          </div>
          <Button size="icon" variant="ghost" aria-label="Close approval details" onClick={() => select(null)}>×</Button>
        </div>
        <div className="drawer-content">
          {notice && notice.id === selectedId ? <p role="status">{notice.text}</p> : null}
          {detail.isError ? <RequestError error={detail.error} /> : null}
          {selectedId && !selected && detail.isPending ? <Skeleton className="h-24" /> : null}
          {selected ? (
            <ApprovalDetail
              approval={selected}
              isAdmin={isAdmin}
              note={note?.id === selected.id ? note.text : ""}
              onNote={(text) => setNote({ id: selected.id, text })}
              deciding={decide.isPending}
              resuming={resume.isPending}
              executing={execute.isPending}
              error={decide.error ?? resume.error ?? execute.error}
              onDecide={(decision) => decide.mutate(decision)}
              onResume={() => resume.mutate(selected.run_id)}
              onExecute={() => execute.mutate(selected.id)}
            />
          ) : null}
        </div>
      </aside>
    ) : null}
    </div>
  );
}

function ApprovalDetail({
  approval,
  isAdmin,
  note,
  onNote,
  deciding,
  resuming,
  executing,
  error,
  onDecide,
  onResume,
  onExecute,
}: {
  approval: Approval;
  isAdmin: boolean;
  note: string;
  onNote: (note: string) => void;
  deciding: boolean;
  resuming: boolean;
  executing: boolean;
  error: unknown;
  onDecide: (decision: "approve" | "reject") => void;
  onResume: () => void;
  onExecute: () => void;
}) {
  const message = approval.action_type === "prepare_customer_response" ? approval.payload : null;
  const whatsapp = message?.channel === "whatsapp";
  const template = whatsapp && typeof message?.template_name === "string" ? message.template_name : "";
  return (
    <div>
      <div className="detail-status">
        <span className={statusBadge(approval.status)}>{approval.status.replaceAll("_", " ")}</span>
        <span>{scopeLabel(approval)}</span>
      </div>
      {message ? (
        <section className="approval-detail-section" aria-label="Approved message preview">
          <h3>Message preview</h3>
          <div className="message-preview">
            <small>Recipient</small>
            <strong>{String(message.to ?? message.recipient ?? "Unavailable")}</strong>
            {!whatsapp && message.subject ? <p>{String(message.subject)}</p> : null}
            {template ? <p>{template} · {String(message.template_language ?? "en_US")}</p> : null}
            {template ? <span>Review this template in WhatsApp Business before approving.</span> : <p>{typeof message.body === "string" ? message.body : "Message is unavailable."}</p>}
          </div>
        </section>
      ) : null}
      {approval.action_type === "request_appointment" ? (
        <section className="approval-detail-section">
          <h3>Appointment</h3>
          {(["starts_at", "ends_at"] as const).map((key) => {
            const date = approval.payload[key];
            return typeof date === "string" ? <p key={key}><time dateTime={date}>{key === "starts_at" ? "Starts" : "Ends"} {new Date(date).toLocaleString()}</time></p> : null;
          })}
        </section>
      ) : null}
      <section className="approval-detail-section">
        <h3>Proposed action</h3>
        <div className="proposed-change">
          <div>
            <strong>{proposalChange(approval.action_type, approval.payload)}</strong>
            <p>Affected: {proposalTarget(approval.payload)}</p>
          </div>
        </div>
        <p>{proposalRisk(approval.action_type)}</p>
      </section>
      <section className="approval-detail-section">
        <h3>Record</h3>
        <p>Expires {new Date(approval.expires_at).toLocaleString()}</p>
        {approval.decided_at ? <p>Decided {new Date(approval.decided_at).toLocaleString()}</p> : null}
        {approval.executed_at ? <p>Executed {new Date(approval.executed_at).toLocaleString()}</p> : null}
        {approval.decision_note ? <p>Note: {approval.decision_note}</p> : null}
        <p>{sideEffect(approval)}</p>
      </section>
      {isAdmin ? (
        <details>
          <summary>Administrator details</summary>
          <pre><code>{JSON.stringify(approval.payload, null, 2)}</code></pre>
        </details>
      ) : null}
      {executionSummary(approval.execution_result) ? <div className="execution-result"><span><strong>Result recorded</strong><small>{executionSummary(approval.execution_result)}</small></span></div> : null}
      {approval.execution_error ? <div className="state-banner error"><span><strong>Execution failed</strong><small>{approval.execution_error}</small></span></div> : null}
      {approval.status === "pending" && !isAdmin ? <div className="permission-state"><span><strong>Administrator review required</strong><small>You can inspect this request. An administrator approves or rejects it.</small></span></div> : null}
      {approval.status === "pending" && isAdmin ? (
        <div className="field">
          <span>Decision note</span>
          <Textarea value={note} onChange={(event) => onNote(event.target.value)} placeholder="Optional note" aria-label="Decision note" />
          <div className="approval-actions">
            <Button type="button" variant="outline" disabled={deciding} onClick={() => onDecide("reject")}>{deciding ? "Saving" : "Reject"}</Button>
            <Button type="button" disabled={deciding} onClick={() => onDecide("approve")}>{deciding ? "Saving" : "Approve"}</Button>
          </div>
        </div>
      ) : null}
      {approval.status === "approved" && isAdmin ? (
        <div>
          <Button type="button" disabled={executing} onClick={() => { if (window.confirm("Execute this approved action? This will apply the stored change.")) onExecute(); }}>{executing ? "Executing" : "Execute"}</Button>
          <p>Execution applies the approved change.</p>
        </div>
      ) : null}
      {approval.status === "executed" ? <Link className="text-button" href={updatedRecordHref(approval)}>View updated CRM record</Link> : null}
      {approval.status !== "pending" ? <Button type="button" variant="outline" disabled={resuming} onClick={onResume}>{resuming ? "Resuming" : "Resume agent run"}</Button> : null}
      {error ? <RequestError error={error} /> : null}
    </div>
  );
}

function updatedRecordHref(approval: Approval): string {
  const leadId = approval.execution_result?.lead_id ?? approval.payload.lead_id;
  return typeof leadId === "string" && leadId.length > 0
    ? `/crm?tab=leads&id=${encodeURIComponent(leadId)}`
    : "/crm?tab=leads";
}

function statusBadge(status: string): string {
  if (status === "executed" || status === "approved" || status === "succeeded") return "badge badge-green";
  if (status === "failed" || status === "needs_attention" || status === "rejected") return "badge badge-red";
  if (status === "pending" || status === "expired") return "badge badge-amber";
  return "badge badge-blue";
}

function scopeLabel(approval: Approval): string {
  const { action_type: actionType, payload } = approval;
  if (actionType === "create_lead" || actionType === "update_lead") {
    return "Internal CRM write";
  }
  if (actionType === "prepare_customer_response") {
    if (payload.channel === "whatsapp" && payload.whatsapp_delivery === "test") return "Restricted WhatsApp test reply";
    if (payload.channel === "whatsapp") return "WhatsApp reply";
    if (payload.delivery_mode === "live") {
      return "External email";
    }
    return "Sandbox email";
  }
  if (actionType === "request_appointment") {
    return payload.provider_calendar_id ? "Google Calendar" : "ATLAS reservation";
  }
  return "Stored action";
}

function sideEffect(approval: Approval): string {
  const { action_type: actionType, status, payload } = approval;
  if (status === "needs_attention") {
    return "The outcome could not be confirmed, so this was not marked successful. Check Workflows before running it again.";
  }
  if (actionType === "prepare_customer_response") {
    if (payload.channel === "whatsapp" && payload.whatsapp_delivery === "test") return "Execute sends one session message to the approved test recipient. It does not enable customer messaging or a paid template.";
    if (payload.channel === "whatsapp") return "Execute sends the approved WhatsApp reply to the linked phone number.";
    if (payload.delivery_mode === "live") return "Execute submits the approved email to the verified SMTP relay.";
    return "Execute sends the approved email to the local SMTP sink.";
  }
  if (actionType === "request_appointment") {
    if (payload.provider_calendar_id) return "Execute checks the connected Google Calendar again and creates a private event.";
    return "Execute reserves this time in ATLAS. Download the event from Workflows to import it into a calendar.";
  }
  if (actionType === "update_lead" || actionType === "create_lead") {
    return "Approve does not change CRM. Execute writes this payload. Reject writes nothing.";
  }
  return "Execute writes only the payload shown here.";
}

function targetLabel(payload: Record<string, unknown>): string {
  const leadId = payload.lead_id;
  const contactId = payload.contact_id;
  const companyId = payload.company_id;
  const attach = payload.attach_to;
  if (typeof leadId === "string" && leadId) {
    return `lead ${leadId}`;
  }
  if (attach === "run_lead") {
    return "the lead created by this run";
  }
  if (typeof contactId === "string" && contactId) {
    return `contact ${contactId}`;
  }
  if (typeof companyId === "string" && companyId) {
    return `company ${companyId}`;
  }
  return "a new lead";
}
