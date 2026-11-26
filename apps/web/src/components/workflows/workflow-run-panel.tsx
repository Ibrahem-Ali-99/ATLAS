"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, Clock3, Play } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { listOpportunities } from "@/lib/opportunities";
import { listLeads } from "@/lib/records-api";
import { listWorkflowRuns, retryWorkflowRun, reviewWorkflowRun, startWorkflowRun, type WorkflowDefinition, type WorkflowRunDetail } from "@/lib/workflow-definitions";

const runStatuses: Record<string, string> = {
  pending: "Queued", dispatching: "Running", awaiting_approval: "Awaiting approval",
  completed: "Completed", simulated: "Preview only", skipped: "Conditions did not match", rejected: "Rejected",
  failed: "Failed", needs_attention: "Needs attention",
};
const stepStatuses: Record<string, string> = {
  completed: "Saved", simulated: "Preview only", failed: "Failed", rolled_back: "Undone",
  matched: "Matched", not_matched: "Did not match", awaiting_approval: "Waiting for approval",
};
const errors: Record<string, string> = {
  workflow_lead_missing: "The selected lead is no longer available.",
  workflow_opportunity_missing: "The selected opportunity is no longer available.",
  follow_up_contact_missing: "The lead has no linked contact.",
  follow_up_recipient_unavailable: "Link a contact email and an inquiry to draft the follow-up.",
  follow_up_drafting_failed: "Drafting failed. Check the language provider connection in Integrations.",
  execution_uncertain: "The worker stopped before it could confirm the outcome. Review the CRM record before running again.",
};

export function WorkflowRunPanel({ organizationId, workflow, dirty, labels, requestedRun }: {
  organizationId: string; workflow: WorkflowDefinition; dirty: boolean; labels: Record<string, string>; requestedRun?: string;
}) {
  const client = useQueryClient();
  const queryKey = ["workflow-runs", organizationId, workflow.id];
  const [testOpen, setTestOpen] = useState(false);
  const [selected, setSelected] = useState(requestedRun);
  const runs = useQuery({ queryKey: [...queryKey, requestedRun], queryFn: () => listWorkflowRuns(organizationId, workflow.id, requestedRun), refetchInterval: 2500 });
  const run = selected ? runs.data?.find((result) => result.id === selected) : runs.data?.[0];
  const [decision, setDecision] = useState<"approve" | "reject" | null>(null);
  const remember = (result: WorkflowRunDetail) => {
    client.setQueryData<WorkflowRunDetail[]>([...queryKey, requestedRun], (current) => [result, ...(current ?? []).filter(({ id }) => id !== result.id)]);
    void client.invalidateQueries({ queryKey });
    void client.invalidateQueries({ queryKey: ["workflow-tasks", organizationId] });
    void client.invalidateQueries({ queryKey: ["workflow-reviews", organizationId] });
  };
  const retry = useMutation({
    mutationFn: (id: string) => retryWorkflowRun(organizationId, workflow.id, id),
    onSuccess: remember,
  });
  const review = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approve" | "reject" }) => reviewWorkflowRun(organizationId, workflow.id, id, decision),
    onSuccess: (result) => { remember(result); setDecision(null); },
  });
  return (
    <div className="grid min-w-0 gap-4 p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h3 className="text-sm font-semibold">Execution history</h3><p className="mt-1 text-xs text-muted-foreground">Most recent runs for this workflow.</p></div>
        {!workflow.archived_at ? <Dialog open={testOpen} onOpenChange={setTestOpen}>
          <DialogTrigger asChild><Button size="sm" disabled={dirty}><Play className="size-4" />Test workflow</Button></DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Test workflow</DialogTitle><DialogDescription>Preview checks the path without saving tasks, lead changes, or follow-up drafts. Running the workflow can save those actions. Customer messages still wait for a separate approval.</DialogDescription></DialogHeader>
            <ManualTest organizationId={organizationId} workflow={workflow} onStarted={(result) => {
              remember(result); setSelected(result.id); setTestOpen(false);
            }} />
          </DialogContent>
        </Dialog> : null}
      </div>
      {dirty ? <p className="text-xs text-warning">Save your changes before testing.</p> : null}
      {runs.error ? <RequestError error={runs.error} /> : null}
      {runs.isPending ? <Skeleton className="h-32" /> : null}
      {selected && runs.data && !run ? <p className="text-sm text-muted-foreground" role="status">This run is unavailable. <Button size="sm" variant="outline" onClick={() => setSelected(undefined)}>Show latest run</Button></p> : null}
      {runs.data?.length === 0 ? <div className="rounded-lg border border-dashed border-border p-6 text-center"><Clock3 className="mx-auto mb-2 size-5 text-muted-foreground" aria-hidden="true" /><p className="text-sm font-medium">No runs yet</p><p className="mt-1 text-xs text-muted-foreground">A run appears when the trigger fires or you start a test.</p></div> : null}
      {run ? <div className="grid min-w-0 gap-4 md:grid-cols-[minmax(12rem,1fr)_minmax(0,2fr)]">
        <ul className="max-h-80 divide-y divide-border overflow-y-auto rounded-lg border border-border">
          {runs.data?.map((entry) => <li key={entry.id}>
            <button type="button" aria-pressed={entry.id === run.id} onClick={() => { setSelected(entry.id); setDecision(null); review.reset(); }}
              className="grid w-full gap-1 px-3 py-3 text-left hover:bg-muted aria-pressed:bg-accent">
              <span className="text-sm font-medium">{runStatuses[entry.status] ?? entry.status}</span>
              <span className="text-xs text-muted-foreground">{entry.manual ? "Manual test" : "Trigger run"} · {new Date(entry.created_at).toLocaleString()}</span>
            </button>
          </li>)}
        </ul>
        <section className="min-w-0 rounded-lg border border-border p-4" aria-label="Run inspection">
          <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">Run details</h4><Badge variant="secondary">{runStatuses[run.status] ?? run.status}</Badge></div>
          {run.lead_id ? <Link className="mt-2 inline-block text-xs text-primary underline" href={`/crm?tab=leads&id=${run.lead_id}`}>Open lead</Link> : null}
          {run.opportunity_id ? <Link className="mt-2 inline-block text-xs text-primary underline" href={`/crm?tab=opportunities&id=${run.opportunity_id}`}>Open opportunity</Link> : null}
          {run.dry_run ? <p className="mt-3 text-sm text-muted-foreground">Preview only. No task, lead change, or follow-up draft was saved.</p> : null}
          {run.branch === "matched" ? <p className="mt-3 text-sm">Followed the matching path.</p> : null}
          {run.branch === "otherwise" ? <p className="mt-3 text-sm">Followed the otherwise path.</p> : null}
          {run.error ? <p className="mt-3 flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive"><CircleAlert className="mt-0.5 size-4 shrink-0" />{errors[run.error] ?? "This run could not finish. Review the steps before retrying."}</p> : null}
          {run.status === "failed" && run.steps.some((step) => step.status === "failed") ? <Button size="sm" className="mt-3" disabled={retry.isPending} onClick={() => retry.mutate(run.id)}>{retry.isPending ? "Queuing…" : "Try again"}</Button> : null}
          {retry.error ? <div className="mt-3"><RequestError error={retry.error} /></div> : null}
          {run.steps.length ? <ol className="mt-3 divide-y divide-border">
            {run.steps.map((step, index) => <li key={`${index}-${step.type}`} className="flex flex-wrap justify-between gap-2 py-2 text-sm"><span>{labels[step.type] ?? step.type}</span><span className="text-muted-foreground">{stepStatuses[step.status] ?? step.status.replaceAll("_", " ")}</span></li>)}
          </ol> : <p className="mt-3 text-xs text-muted-foreground">{["pending", "dispatching"].includes(run.status) ? "Step results will appear here after processing." : "No step results were recorded for this run."}</p>}
          {run.approval_id ? <Link href={`/approvals?approval=${run.approval_id}`} className="mt-3 inline-block text-sm font-medium text-primary underline">Review follow-up draft</Link> : null}
          {run.review ? <p className="mt-3 text-xs text-muted-foreground">{run.review.decision === "approve" ? "Approved" : "Rejected"} · {new Date(run.review.decided_at).toLocaleString()}</p> : null}
          {run.status === "awaiting_approval" ? <div className="mt-4 space-y-2 border-t border-border pt-3">
            {run.review_note ? <p className="whitespace-pre-wrap text-sm">{run.review_note}</p> : null}
            <p className="text-xs text-muted-foreground">{decision === "approve" ? "The remaining actions will run on approval." : decision === "reject" ? "The remaining actions will be discarded." : "An administrator must decide whether to continue this run."}</p>
            <div className="flex flex-wrap gap-2">
              {decision ? <>
                <Button size="sm" disabled={review.isPending} onClick={() => review.mutate({ id: run.id, decision })}>Confirm {decision === "approve" ? "approval" : "rejection"}</Button>
                <Button size="sm" variant="ghost" disabled={review.isPending} onClick={() => setDecision(null)}>Cancel</Button>
              </> : <>
                {!workflow.archived_at ? <Button size="sm" onClick={() => setDecision("approve")}>Approve</Button> : null}
                <Button size="sm" variant="outline" onClick={() => setDecision("reject")}>Reject</Button>
              </>}
            </div>
            {review.error ? <RequestError error={review.error} /> : null}
          </div> : null}
        </section>
      </div> : null}
    </div>
  );
}

function ManualTest({ organizationId, workflow, onStarted }: {
  organizationId: string; workflow: WorkflowDefinition; onStarted: (run: WorkflowRunDetail) => void;
}) {
  const needsLead = ["lead_created", "lead_status_changed"].includes(workflow.definition.trigger);
  const needsOpportunity = workflow.definition.trigger === "opportunity_stage_changed";
  const [record, setRecord] = useState("");
  const [repeat, setRepeat] = useState(false);
  const request = useRef<{ preview?: string; apply?: string; record: string }>({ record: "" });
  const leads = useQuery({ queryKey: ["workflow-test-leads", organizationId], queryFn: () => listLeads(organizationId, { pageSize: 100 }), enabled: needsLead });
  const opportunities = useQuery({ queryKey: ["opportunities", organizationId], queryFn: () => listOpportunities(organizationId), enabled: needsOpportunity });
  function requestId(mode: "preview" | "apply", forceNew: boolean) {
    if (request.current.record !== record) request.current = { record };
    if (forceNew || !request.current[mode]) request.current[mode] = crypto.randomUUID();
    return request.current[mode] ?? crypto.randomUUID();
  }
  const start = useMutation({
    mutationFn: (dryRun: boolean) => startWorkflowRun(organizationId, workflow.id, {
      request_id: requestId(dryRun ? "preview" : "apply", !dryRun && repeat),
      dry_run: dryRun,
      confirm_repeat: !dryRun && repeat,
      ...(needsLead ? { lead_id: record } : needsOpportunity ? { opportunity_id: record } : {}),
    }),
    onSuccess: onStarted,
  });
  const records = needsLead ? leads.data?.items : opportunities.data;
  const requiresRecord = needsLead || needsOpportunity;
  const error = start.error ?? (needsLead ? leads.error : needsOpportunity ? opportunities.error : null);
  return (
    <form className="mt-4 grid gap-3" onSubmit={(event) => event.preventDefault()}>
      {requiresRecord ? <label className="grid gap-1 text-sm">{needsLead ? "Lead" : "Opportunity"}
        <select className="h-9 min-w-0 rounded-md border border-input bg-card px-2 text-sm" required value={record} onChange={(e) => setRecord(e.target.value)} disabled={start.isPending}>
          <option value="">{records ? (records.length ? "Select a CRM record" : "No records available") : "Loading records…"}</option>
          {records?.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
        </select>
      </label> : null}
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={repeat} onChange={(event) => setRepeat(event.target.checked)} /> Run saved actions again when this record was already changed by this workflow</label>
      {error ? <RequestError error={error} /> : null}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" disabled={start.isPending || (requiresRecord && !record)} onClick={() => start.mutate(true)}>{start.isPending ? "Queuing…" : "Preview path"}</Button>
        <Button type="button" disabled={start.isPending || (requiresRecord && !record)} onClick={() => start.mutate(false)}>{start.isPending ? "Queuing…" : "Run on this record"}</Button>
      </div>
    </form>
  );
}
