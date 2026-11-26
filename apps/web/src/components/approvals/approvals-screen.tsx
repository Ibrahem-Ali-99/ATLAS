"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useRef, useState } from "react";

import { Pager } from "@/components/pager";
import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { executionSummary, type Approval, type ApprovalStatus } from "@/lib/agent";
import { decideApproval, executeApproval, getApproval, listApprovals, resumeAgentRun } from "@/lib/agent-api";
import { useWorkspace } from "@/lib/use-workspace";
import { actionLabel, proposalChange, proposalRisk, proposalTarget } from "@/lib/approval-presentation";
import { listWorkflowReviews } from "@/lib/workflow-definitions";

const selectClass =
  "flex h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground";

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

  return (
    <div className="flex w-full min-w-0 flex-col gap-5">
    <PageHeader title="Approvals" eyebrow="Governed actions" actions={
      <Button asChild variant="outline"><Link href="/agent-runs">View execution history</Link></Button>
    }>Review proposed workspace changes before applying them.</PageHeader>
    {workflowReviews.error ? <RequestError error={workflowReviews.error} /> : null}
    {workflowReviews.data?.length ? <aside className="rounded-xl border border-border bg-card p-4" aria-label="Pending workflow approvals">
      <h2 className="text-sm font-semibold">Workflows awaiting approval</h2>
      <ul className="mt-2 grid gap-2 sm:grid-cols-2">
        {workflowReviews.data.map((entry) => <li key={entry.id}>
          <Link className="block rounded-md border border-border px-3 py-2 hover:bg-accent"
            href={`/workflows?workflow=${entry.workflow_id}&run=${entry.id}${entry.archived ? "&archived=1" : ""}`}>
            <span className="block break-words text-sm font-medium">{entry.name}</span>
            {entry.note ? <span className="mt-0.5 block break-words text-xs text-muted-foreground">{entry.note}</span> : null}
          </Link>
        </li>)}
      </ul>
    </aside> : null}
    <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <section className="min-w-0 overflow-hidden rounded-lg border border-border bg-card shadow-sm">
        <div className="flex flex-col gap-3 border-b border-border bg-muted/40 p-4">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter loaded decisions"
            aria-label="Filter loaded decisions"
          />
          <select
            className={selectClass}
            aria-label="Filter approvals"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as ApprovalStatus | "");
              setPage(1);
            }}
          >
            <option value="">All decisions</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="executed">Executed</option>
            <option value="executing">Executing</option>
            <option value="failed">Failed</option>
            <option value="needs_attention">Needs attention</option>
            <option value="expired">Expired</option>
          </select>
        </div>
        {approvals.isPending ? <div className="px-4 pb-4"><Skeleton className="h-8 w-full" /></div> : null}
        {approvals.isError ? <div className="px-4 pb-4"><RequestError error={approvals.error} /></div> : null}
        {approvals.data && visible.length === 0 ? (
          <p className="px-4 pb-6 text-sm text-muted-foreground">No approvals match this filter.</p>
        ) : null}
        <div>
          {visible.map((approval) => (
            <button
              key={approval.id}
              type="button"
              data-approval-id={approval.id}
              aria-current={approval.id === selectedId || undefined}
              className={`block w-full px-4 py-3 text-left ${approval.id === selectedId ? "bg-accent/40" : ""}`}
              onClick={() => select(approval.id)}
            >
              <span className="font-medium">{actionLabel(approval.action_type)}</span>
              <span className="mt-1 block text-sm text-muted-foreground">
                {scopeLabel(approval)}
                {" · "}
                <span className={statusClass(approval.status)}>{approval.status}</span>
              </span>
            </button>
          ))}
        </div>
        {approvals.data ? (
          <Pager page={approvals.data.page} pageSize={approvals.data.page_size} total={approvals.data.total} onPage={setPage} />
        ) : null}
      </section>
      <section aria-label="Approval details" className="min-w-0 rounded-lg border border-border bg-card p-5 shadow-sm">
        {selectedId ? <Button className="mb-3" size="sm" variant="outline" onClick={() => select(null)}>Close approval details</Button> : null}
        {notice && notice.id === selectedId ? <p className="mb-3 text-sm text-muted-foreground" role="status">{notice.text}</p> : null}
        {detail.isError ? <RequestError error={detail.error} /> : null}
        {selectedId && !selected && detail.isPending ? <Skeleton className="h-24" /> : null}
        {!selectedId ? <p className="text-sm text-muted-foreground">Select a proposal to review the requested change and its impact.</p> : null}
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
      </section>
    </div>
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
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">{actionLabel(approval.action_type)}</h2>
          <p className={`mt-1 text-xs uppercase tracking-[0.12em] ${approval.action_type === "prepare_customer_response" || approval.action_type === "request_appointment" ? "text-warning" : "text-success"}`}>
            {scopeLabel(approval)}
          </p>
          <p className="text-sm text-muted-foreground">Requested {new Date(approval.created_at).toLocaleString()}</p>
        </div>
        <p className={`text-xs uppercase tracking-[0.12em] ${statusClass(approval.status)}`}>{approval.status}</p>
      </div>
      {message ? (
        <section aria-label="Approved message preview" className="rounded-lg border border-border bg-background p-4">
          <h3 className="text-sm font-semibold">Message preview</h3>
          <dl className="mt-2 grid gap-2 text-sm">
            <div><dt className="text-muted-foreground">Recipient</dt><dd className="break-all">{String(message.to ?? message.recipient ?? "Unavailable")}</dd></div>
            {!whatsapp && message.subject ? <div><dt className="text-muted-foreground">Subject</dt><dd className="break-words">{String(message.subject)}</dd></div> : null}
            {template ? <div><dt className="text-muted-foreground">WhatsApp template</dt><dd className="break-words">{template} · {String(message.template_language ?? "en_US")}</dd></div> : null}
          </dl>
          {template ? <p className="mt-3 text-sm text-muted-foreground">Review this template in WhatsApp Business before approving.</p> :
            <p className="mt-3 max-h-72 overflow-y-auto whitespace-pre-wrap break-words text-sm">{typeof message.body === "string" ? message.body : "Message is unavailable."}</p>}
        </section>
      ) : null}
      {approval.action_type === "request_appointment" ? (
        <dl className="grid gap-2 rounded-lg border border-border bg-background p-4 text-sm sm:grid-cols-2">
          {(["starts_at", "ends_at"] as const).map((key) => {
            const date = approval.payload[key];
            return typeof date === "string" ? <div key={key}>
              <dt className="text-muted-foreground">{key === "starts_at" ? "Starts at" : "Ends at"}</dt>
              <dd><time dateTime={date}>{new Date(date).toLocaleString()}</time></dd>
            </div> : null;
          })}
        </dl>
      ) : null}
      <div className="rounded-lg border border-border bg-card p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Proposed action</p>
        <p className="mt-2 text-sm font-medium">{proposalChange(approval.action_type, approval.payload)}</p>
        <p className="mt-3 text-sm text-muted-foreground"><span className="font-medium text-foreground">Affected:</span> {proposalTarget(approval.payload)}</p>
        <p className="mt-3 text-sm leading-6 text-muted-foreground"><span className="font-medium text-foreground">Impact:</span> {proposalRisk(approval.action_type)}</p>
      </div>
      <dl className="space-y-1 text-sm text-muted-foreground">
        <div>Target {targetLabel(approval.payload)}</div>
        <div>Expires {new Date(approval.expires_at).toLocaleString()}</div>
        {approval.decided_at ? <div>Decided {new Date(approval.decided_at).toLocaleString()}</div> : null}
        {approval.executed_at ? <div>Executed {new Date(approval.executed_at).toLocaleString()}</div> : null}
        {approval.decision_note ? <div>Note: {approval.decision_note}</div> : null}
      </dl>
      <p className="text-sm leading-6 text-muted-foreground">{sideEffect(approval)}</p>
      {isAdmin ? (
        <details className="rounded-[10px] border border-border bg-background p-3">
          <summary className="cursor-pointer text-sm font-medium">Technical details</summary>
          <pre className="mt-3 overflow-x-auto text-xs">{JSON.stringify(approval.payload, null, 2)}</pre>
        </details>
      ) : null}
      {executionSummary(approval.execution_result) ? (
        <p className="text-sm text-muted-foreground">{executionSummary(approval.execution_result)}</p>
      ) : null}
      {approval.execution_error ? <p className="text-sm text-destructive">{approval.execution_error}</p> : null}
      {approval.status === "pending" && isAdmin ? (
        <div className="space-y-3">
          <Textarea value={note} onChange={(event) => onNote(event.target.value)} placeholder="Optional note" aria-label="Decision note" />
          <div className="flex gap-2">
            <Button type="button" disabled={deciding} onClick={() => onDecide("approve")}>
              {deciding ? "Saving" : "Approve"}
            </Button>
            <Button type="button" variant="outline" disabled={deciding} onClick={() => onDecide("reject")}>
              Reject
            </Button>
          </div>
        </div>
      ) : null}
      {approval.status === "pending" && !isAdmin ? (
        <p className="text-sm text-muted-foreground">An admin has to approve or reject this action.</p>
      ) : null}
      {approval.status === "approved" && isAdmin ? (
        <div className="space-y-2">
          <Button type="button" disabled={executing} onClick={() => {
            if (window.confirm("Execute this approved action? This will apply the stored change.")) onExecute();
          }}>
          {executing ? "Executing" : "Execute"}
          </Button>
          <p className="text-xs text-muted-foreground">Execution is the step that applies the approved change.</p>
        </div>
      ) : null}
      {approval.status === "executed" ? <Link className="inline-block text-sm text-primary underline" href={updatedRecordHref(approval)}>View updated CRM record</Link> : null}
      {approval.status !== "pending" ? (
        <Button type="button" variant="outline" disabled={resuming} onClick={onResume}>
          {resuming ? "Resuming" : "Resume agent run"}
        </Button>
      ) : null}
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

function statusClass(status: string): string {
  if (status === "executed" || status === "approved" || status === "succeeded") {
    return "text-success";
  }
  if (status === "failed" || status === "needs_attention" || status === "rejected") {
    return "text-destructive";
  }
  if (status === "pending" || status === "expired") {
    return "text-warning";
  }
  return "text-primary";
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
