"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useRef, useState } from "react";

import { Pager } from "@/components/pager";
import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { executionSummary, type Approval, type ApprovalStatus } from "@/lib/agent";
import { decideApproval, executeApproval, listApprovals, resumeAgentRun } from "@/lib/agent-api";
import { getAutomations } from "@/lib/automations";
import { useWorkspace } from "@/lib/use-workspace";
import { actionLabel, proposalChange, proposalRisk, proposalTarget } from "@/lib/approval-presentation";

const selectClass =
  "flex h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground";

export function ApprovalsScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const [status, setStatus] = useState<ApprovalStatus | "">("pending");
  const requested = useSearchParams().get("approval");
  const [selectedId, setSelectedId] = useState<string | null>(requested);
  const [note, setNote] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  if (!organizationId) {
    return <Skeleton className="h-40 w-full" />;
  }
  return (
    <ApprovalsBody
      organizationId={organizationId}
      isAdmin={workspace.role === "admin"}
      status={status}
      onStatus={setStatus}
      selectedId={selectedId}
      onSelect={setSelectedId}
      note={note}
      onNote={setNote}
      notice={notice}
      onNotice={setNotice}
    />
  );
}

function ApprovalsBody({
  organizationId,
  isAdmin,
  status,
  onStatus,
  selectedId,
  onSelect,
  note,
  onNote,
  notice,
  onNotice,
}: {
  organizationId: string;
  isAdmin: boolean;
  status: ApprovalStatus | "";
  onStatus: (status: ApprovalStatus | "") => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  note: string;
  onNote: (note: string) => void;
  notice: string | null;
  onNotice: (notice: string | null) => void;
}) {
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
  const automations = useQuery({
    queryKey: ["automations", organizationId],
    queryFn: () => getAutomations(organizationId),
  });
  const needle = query.trim().toLowerCase();
  const visible = (approvals.data?.items ?? []).filter((approval) => {
    if (needle.length === 0) {
      return true;
    }
    const haystack = `${approval.action_type} ${JSON.stringify(approval.payload)}`.toLowerCase();
    return haystack.includes(needle);
  });
  const selected = visible.find((item) => item.id === selectedId)
    ?? approvals.data?.items.find((item) => item.id === selectedId)
    ?? null;
  const decide = useMutation({
    mutationFn: (decision: "approve" | "reject") => {
      if (!selected) {
        throw new Error("Select an approval first");
      }
      return decideApproval(organizationId, selected.id, decision, note);
    },
    onSuccess: async (_approval, decision) => {
      onNote("");
      // Keep the decided proposal visible and selected. The default Pending
      // filter would otherwise remove it from the loaded list immediately,
      // unmounting the detail panel before the operator can execute it.
      onStatus("");
      onNotice(
        decision === "approve"
          ? "Approved. Execute writes the stored payload. Nothing is sent until then."
          : "Rejected. No CRM change or external action was written.",
      );
      await queryClient.invalidateQueries({ queryKey: ["approvals", organizationId] });
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
      onNotice(
        approval.status === "executing"
          ? "Queued. The sandbox worker is processing the stored result."
          : "Executed. The stored result is on this approval.",
      );
      await queryClient.invalidateQueries({ queryKey: ["approvals", organizationId] });
      await queryClient.invalidateQueries({ queryKey: ["agent-runs", organizationId] });
      await queryClient.invalidateQueries({ queryKey: ["automations", organizationId] });
      if (approval.action_type === "create_lead" || approval.action_type === "update_lead") {
        await queryClient.invalidateQueries({ queryKey: ["leads", organizationId] });
      }
    },
  });

  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
    <header>
      <h1 className="text-[31px] leading-none text-foreground">Decisions</h1>
      <p className="mt-3 max-w-3xl text-sm text-muted-foreground">
        A person approves, rejects, or executes the stored proposal. Approve stores a decision. Execute writes the payload. Reject writes nothing.
      </p>
    </header>
    <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <section className="min-w-0 rounded-[10px] bg-muted">
        <div className="flex flex-col gap-3 p-4">
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
              onStatus(event.target.value as ApprovalStatus | "");
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
              className={`block w-full px-4 py-3 text-left ${approval.id === selectedId ? "bg-accent/40" : ""}`}
              onClick={() => onSelect(approval.id)}
            >
              <span className="font-medium">{actionLabel(approval.action_type)}</span>
              <span className="mt-1 block text-sm text-muted-foreground">
                {scopeLabel(approval.action_type, automations.data?.email_mode, automations.data?.calendar_provider)}
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
      <section className="rounded-[10px] bg-muted p-4">
        {notice ? <p className="mb-3 text-sm text-muted-foreground">{notice}</p> : null}
        {!selected ? <p className="text-sm text-muted-foreground">Select a proposal to review the requested change and its impact.</p> : null}
        {selected ? (
          <ApprovalDetail
            approval={selected}
            isAdmin={isAdmin}
            emailMode={automations.data?.email_mode}
            calendarProvider={automations.data?.calendar_provider}
            note={note}
            onNote={onNote}
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
  emailMode,
  calendarProvider,
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
  emailMode: string | undefined;
  calendarProvider: string | undefined;
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
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">{actionLabel(approval.action_type)}</h2>
          <p className={`mt-1 text-xs uppercase tracking-[0.12em] ${approval.action_type === "prepare_customer_response" || approval.action_type === "request_appointment" ? "text-warning" : "text-success"}`}>
            {scopeLabel(approval.action_type, emailMode, calendarProvider)}
          </p>
          <p className="text-sm text-muted-foreground">Requested {new Date(approval.created_at).toLocaleString()}</p>
        </div>
        <p className={`text-xs uppercase tracking-[0.12em] ${statusClass(approval.status)}`}>{approval.status}</p>
      </div>
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
      <p className="text-xs text-subtle">Previous field values are not stored on this proposal. The fields below are the stored payload.</p>
      <p className="text-sm leading-6 text-muted-foreground">{sideEffect(approval.action_type, approval.status)}</p>
      {isAdmin ? (
        <details className="rounded-[10px] border border-border bg-background p-3">
          <summary className="cursor-pointer text-sm font-medium">Technical details</summary>
          <pre className="mt-3 overflow-x-auto text-xs">{JSON.stringify(approval.payload, null, 2)}</pre>
        </details>
      ) : null}
      {executionSummary(approval.execution_result) ? (
        <p className="text-sm text-muted-foreground">{executionSummary(approval.execution_result)}</p>
      ) : null}
      {approval.execution_error ? <p className="text-sm text-red-300">{approval.execution_error}</p> : null}
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

function scopeLabel(actionType: string, emailMode: string | undefined, calendarProvider: string | undefined): string {
  if (actionType === "create_lead" || actionType === "update_lead") {
    return "Internal CRM write";
  }
  if (actionType === "prepare_customer_response") {
    if (emailMode === "live") {
      return "External email";
    }
    if (emailMode === "sandbox") {
      return "Sandbox email";
    }
    return "Email on execute";
  }
  if (actionType === "request_appointment") {
    if (calendarProvider === "simulation") {
      return "Simulated calendar";
    }
    if (calendarProvider) {
      return "External calendar";
    }
    return "Calendar on execute";
  }
  return "Stored action";
}

function sideEffect(actionType: string, status: string): string {
  if (status === "needs_attention") {
    return "The outcome could not be confirmed, so this was not marked successful. Check Workflows before running it again.";
  }
  if (actionType === "prepare_customer_response") {
    return "Approve stores this text. Execute sends it through the configured email mode. Sandbox mode reaches the local mailbox, not a customer inbox. Reject sends nothing.";
  }
  if (actionType === "request_appointment") {
    return "Approve stores this time. Execute writes a simulated calendar booking in ATLAS. No external calendar is contacted. Reject books nothing.";
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
