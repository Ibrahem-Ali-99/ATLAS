"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type { Approval, ApprovalStatus } from "@/lib/agent";
import { decideApproval, listApprovals, resumeAgentRun } from "@/lib/agent-api";
import { useWorkspace } from "@/lib/use-workspace";

const selectClass =
  "flex h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground";

export function ApprovalsScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const [status, setStatus] = useState<ApprovalStatus | "">("pending");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [note, setNote] = useState("");
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
}: {
  organizationId: string;
  isAdmin: boolean;
  status: ApprovalStatus | "";
  onStatus: (status: ApprovalStatus | "") => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  note: string;
  onNote: (note: string) => void;
}) {
  const queryClient = useQueryClient();
  const approvals = useQuery({
    queryKey: ["approvals", organizationId, status],
    queryFn: () => listApprovals(organizationId, { status }),
  });
  const selected = approvals.data?.items.find((item) => item.id === selectedId) ?? null;
  const decide = useMutation({
    mutationFn: (decision: "approve" | "reject") => {
      if (!selected) {
        throw new Error("Select an approval first");
      }
      return decideApproval(organizationId, selected.id, decision, note);
    },
    onSuccess: async () => {
      onNote("");
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

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(22rem,0.9fr)]">
      <section className="rounded-xl border border-border bg-card">
        <div className="p-4">
          <select
            className={selectClass}
            aria-label="Filter approvals"
            value={status}
            onChange={(event) => onStatus(event.target.value as ApprovalStatus | "")}
          >
            <option value="">All decisions</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="executed">Executed</option>
            <option value="failed">Failed</option>
            <option value="expired">Expired</option>
          </select>
        </div>
        {approvals.isPending ? <div className="px-4 pb-4"><Skeleton className="h-8 w-full" /></div> : null}
        {approvals.isError ? <div className="px-4 pb-4"><RequestError error={approvals.error} /></div> : null}
        {approvals.data && approvals.data.items.length === 0 ? (
          <p className="px-4 pb-6 text-sm text-muted-foreground">No approvals match this filter.</p>
        ) : null}
        <div className="divide-y divide-border">
          {approvals.data?.items.map((approval) => (
            <button
              key={approval.id}
              type="button"
              className={`block w-full px-4 py-3 text-left ${approval.id === selectedId ? "bg-accent/40" : ""}`}
              onClick={() => onSelect(approval.id)}
            >
              <span className="font-medium">{approval.action_type.replaceAll("_", " ")}</span>
              <span className="mt-1 block text-sm text-muted-foreground">
                {approval.status} · {new Date(approval.created_at).toLocaleString()}
              </span>
            </button>
          ))}
        </div>
      </section>
      <section className="rounded-xl border border-border bg-card p-4">
        {!selected ? <p className="text-sm text-muted-foreground">Select a proposal to see its exact payload.</p> : null}
        {selected ? (
          <ApprovalDetail
            approval={selected}
            isAdmin={isAdmin}
            note={note}
            onNote={onNote}
            deciding={decide.isPending}
            resuming={resume.isPending}
            error={decide.error ?? resume.error}
            onDecide={(decision) => decide.mutate(decision)}
            onResume={() => resume.mutate(selected.run_id)}
          />
        ) : null}
      </section>
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
  error,
  onDecide,
  onResume,
}: {
  approval: Approval;
  isAdmin: boolean;
  note: string;
  onNote: (note: string) => void;
  deciding: boolean;
  resuming: boolean;
  error: unknown;
  onDecide: (decision: "approve" | "reject") => void;
  onResume: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{approval.action_type.replaceAll("_", " ")}</h2>
          <p className="text-sm text-muted-foreground">Requested {new Date(approval.created_at).toLocaleString()}</p>
        </div>
        <Badge>{approval.status}</Badge>
      </div>
      <dl className="space-y-1 text-sm text-muted-foreground">
        <div>Target {targetLabel(approval.payload)}</div>
        <div>Expires {new Date(approval.expires_at).toLocaleString()}</div>
        {approval.decided_at ? <div>Decided {new Date(approval.decided_at).toLocaleString()}</div> : null}
        {approval.executed_at ? <div>Executed {new Date(approval.executed_at).toLocaleString()}</div> : null}
        {approval.decision_note ? <div>Note: {approval.decision_note}</div> : null}
      </dl>
      <pre className="overflow-x-auto rounded-md bg-background p-3 text-xs">{JSON.stringify(approval.payload, null, 2)}</pre>
      {approval.execution_result ? (
        <p className="text-sm text-muted-foreground">
          Lead {approval.execution_result.lead_id ?? "not recorded"}
          {approval.execution_result.interaction_id ? `, interaction ${approval.execution_result.interaction_id}` : ""}
        </p>
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
      {approval.status !== "pending" ? (
        <Button type="button" variant="outline" disabled={resuming} onClick={onResume}>
          {resuming ? "Resuming" : "Resume agent run"}
        </Button>
      ) : null}
      {error ? <RequestError error={error} /> : null}
    </div>
  );
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
