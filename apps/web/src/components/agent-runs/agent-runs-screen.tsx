"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Bot, ChevronRight, Filter, Search } from "lucide-react";
import { useState } from "react";

import { DataScopeControl } from "@/components/data-scope";
import { Pager } from "@/components/pager";
import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { sessionQueryOptions } from "@/lib/api";
import { isDemoSession } from "@/lib/demo-session";
import { getAgentRun, listAgentRuns, listAssistantExecutions, resumeAgentRun, startAgentRun, type AssistantExecution } from "@/lib/agent-api";
import { executionSummary, type AgentEvent, type AgentRunDetail, type RunStatus } from "@/lib/agent";
import { getDiagnosticRun } from "@/lib/intelligence";
import { listInquiries } from "@/lib/records-api";
import type { DataScope } from "@/lib/provenance";
import { useWorkspace } from "@/lib/use-workspace";
import { actionLabel, proposalChange, proposalRisk, proposalTarget } from "@/lib/approval-presentation";

const selectClass =
  "flex h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground";

export function AgentRunsScreen() {
  const { organizationId } = useWorkspace();
  return organizationId ? <AgentRunsWorkspace key={organizationId} organizationId={organizationId} /> : <Skeleton className="h-40 w-full" />;
}

function AgentRunsWorkspace({ organizationId }: { organizationId: string }) {
  const router = useRouter();
  const selectedId = useSearchParams().get("run");
  const [status, setStatus] = useState<RunStatus | "">("");
  const [open, setOpen] = useState(false);
  return (
    <AgentRunsBody
      organizationId={organizationId}
      status={status}
      onStatus={setStatus}
      selectedId={selectedId}
      onSelect={(id) => router.replace(id ? `/agent-runs?run=${encodeURIComponent(id)}` : "/agent-runs", { scroll: false })}
      open={open}
      onOpen={setOpen}
    />
  );
}

function AgentRunsBody({
  organizationId,
  status,
  onStatus,
  selectedId,
  onSelect,
  open,
  onOpen,
}: {
  organizationId: string;
  status: RunStatus | "";
  onStatus: (status: RunStatus | "") => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  open: boolean;
  onOpen: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const session = useQuery(sessionQueryOptions);
  const demonstration = isDemoSession(session.data);
  const [scope, setScope] = useState<DataScope>("all");
  const recordScope = demonstration ? "all" : scope;
  const [page, setPage] = useState(1);
  const [inquiryQuery, setInquiryQuery] = useState("");
  const runs = useQuery({
    queryKey: ["agent-runs", organizationId, status, page, recordScope],
    queryFn: () => listAgentRuns(organizationId, { status, page, scope: recordScope }),
  });
  const detail = useQuery({
    queryKey: ["agent-run", organizationId, selectedId],
    queryFn: () => getAgentRun(organizationId, selectedId ?? ""),
    enabled: selectedId !== null,
    refetchInterval: (query) => query.state.data?.run.status === "running" ? 2000 : false,
  });
  const resume = useMutation({
    mutationFn: (runId: string) => resumeAgentRun(organizationId, runId),
    onSuccess: async (result) => {
      onSelect(result.run.id);
      await queryClient.invalidateQueries({ queryKey: ["agent-runs", organizationId] });
      await queryClient.invalidateQueries({ queryKey: ["agent-run", organizationId, result.run.id] });
    },
  });

  const needle = inquiryQuery.trim().toLowerCase();
  const visible = (runs.data?.items ?? []).filter((run) =>
    needle.length === 0 ? true : run.inquiry_subject.toLowerCase().includes(needle),
  );

  return (
    <div className="flex w-full min-w-0 flex-col gap-5">
    <PageHeader title="Agent Runs" eyebrow="Agent execution history" actions={
      <Button type="button" onClick={() => onOpen(true)}>Start from inquiry</Button>
    }>Inspect agent activity, evidence, approvals, and execution results.</PageHeader>
    <div>
      <section className="panel operations-panel">
        <div className="operations-toolbar">
          {demonstration ? null : <DataScopeControl value={scope} onChange={(next) => { setScope(next); setPage(1); }} />}
          <label className="module-search"><Search size={15} /><input value={inquiryQuery} onChange={(event) => setInquiryQuery(event.target.value)} placeholder="Search agent runs" aria-label="Search inquiries" /></label>
          <label className="toolbar-select"><Filter size={14} /><select
            aria-label="Filter runs by status"
            value={status}
            onChange={(event) => {
              onStatus(event.target.value as RunStatus | "");
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            <option value="running">Running</option>
            <option value="awaiting_approval">Pending decision</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select></label>
        </div>
        {runs.isPending ? <div className="px-4 pb-4"><Skeleton className="h-8 w-full" /></div> : null}
        {runs.isError ? <div className="px-4 pb-4"><RequestError error={runs.error} /></div> : null}
        <p className="px-4 pb-2 text-xs text-subtle">Newest first.</p>
        {runs.data && visible.length === 0 ? (
          <p className="px-4 pb-6 text-sm text-muted-foreground">No agent runs match this filter.</p>
        ) : null}
        {visible.length > 0 ? (
          <div className="operations-table runs-table" role="table" aria-label="Agent run history">
            <div className="operations-row head" role="row"><span>Run</span><span>Inquiry</span><span>Status</span><span>Started</span><span>Duration</span><span>Result</span><span /></div>
            {visible.map((run) => {
              const presentation = presentedRun(run);
              return (
              <button key={run.id} type="button" role="row" className="operations-row" aria-current={run.id === selectedId || undefined} onClick={() => onSelect(run.id)}>
                <span className="operation-primary"><span className="operation-icon"><Bot size={15} /></span><span><strong>{run.inquiry_subject}</strong><small>{presentation.label}</small></span></span>
                <span>{run.inquiry_subject}</span>
                <span><span className={presentation.tone}>{presentation.label}</span></span>
                <span>{new Date(run.started_at).toLocaleDateString()}</span>
                <span>{runDuration(run.started_at, run.finished_at, run.status)}</span>
                <span>{run.error_code ? "Needs attention" : "Recorded"}</span>
                <ChevronRight size={15} />
              </button>
              );
            })}
          </div>
        ) : null}
        {runs.data ? (
          <Pager page={runs.data.page} pageSize={runs.data.page_size} total={runs.data.total} onPage={setPage} />
        ) : null}
      </section>
      {selectedId ? <button type="button" className="drawer-backdrop" aria-label="Close run details" onClick={() => onSelect(null)} /> : null}
      {selectedId ? (
        <aside className="drawer operations-drawer run-drawer" aria-label="Run details">
          <div className="drawer-header">
            <div>
              <h2>{detail.data?.run.inquiry_subject ?? "Agent run"}</h2>
              <p>{detail.data ? presentedRun(detail.data.run).label : "Loading run"}</p>
            </div>
            <Button size="icon" variant="ghost" aria-label="Close run details" onClick={() => onSelect(null)}>×</Button>
          </div>
          <div className="drawer-content">
            {detail.isPending ? <Skeleton className="h-32 w-full" /> : null}
            {detail.isError ? <RequestError error={detail.error} /> : null}
            {detail.data ? (
              <RunDetail
                organizationId={organizationId}
                detail={detail.data}
                pending={resume.isPending}
                error={resume.error}
                onResume={() => resume.mutate(detail.data.run.id)}
              />
            ) : null}
          </div>
        </aside>
      ) : null}
      <StartDialog
        organizationId={organizationId}
        open={open}
        onOpen={onOpen}
        onStarted={(result) => {
          onSelect(result.run.id);
          onOpen(false);
        }}
      />
    </div>
    <AssistantExecutions organizationId={organizationId} />
    </div>
  );
}

function AssistantExecutions({ organizationId }: { organizationId: string }) {
  const admin = useWorkspace().role === "admin";
  const [selected, setSelected] = useState<string | null>(null);
  const [status, setStatus] = useState<"" | "running" | "completed" | "failed">("");
  const runs = useQuery({
    queryKey: ["assistant-executions", organizationId],
    queryFn: () => listAssistantExecutions(organizationId),
  });
  const items = (runs.data?.items ?? []).filter((item) => status === "" || item.status === status);
  const current = items.find((item) => item.id === selected) ?? null;
  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm" aria-label="Assistant executions">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-base font-semibold">Assistant executions</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Stored tool calls, the records they returned, and whether a person still has to approve an action. The stored execution does not include the originating conversation.
          </p>
        </div>
        <select className={selectClass} aria-label="Filter assistant executions" value={status} onChange={(event) => setStatus(event.target.value as "" | "running" | "completed" | "failed")}>
          <option value="">All outcomes</option>
          <option value="running">Pending</option>
          <option value="completed">Successful</option>
          <option value="failed">Failed</option>
        </select>
      </div>
      {runs.isPending ? <Skeleton className="mt-4 h-8 w-full" /> : null}
      {runs.isError ? <div className="mt-4"><RequestError error={runs.error} /></div> : null}
      {runs.data && items.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">{status ? "No executions match this outcome." : "No assistant executions are stored yet."}</p>
      ) : null}
      {items.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Request</TableHead>
              <TableHead>Tools</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Duration</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell>
                  <button type="button" className="text-left font-medium" aria-current={item.id === selected || undefined} onClick={() => setSelected(item.id)}>
                    {item.request}
                  </button>
                </TableCell>
                <TableCell>{item.tools.length > 0 ? item.tools.join(", ") : "No tool selected"}</TableCell>
                <TableCell className={statusClass(item.status === "running" ? "pending" : item.status)}>{item.status === "running" ? "Pending" : item.status}</TableCell>
                <TableCell>{runDuration(item.started_at, item.finished_at, item.status === "running" ? "running" : "completed")}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
      {current ? <ExecutionDetail execution={current} admin={admin} /> : null}
    </section>
  );
}

function ExecutionDetail({ execution, admin }: { execution: AssistantExecution; admin: boolean }) {
  return (
    <div className="mt-4 space-y-3">
      <p className="text-sm font-medium">{execution.request}</p>
      {execution.error_message ? <p className="text-sm text-destructive">{execution.error_message}</p> : null}
      {execution.steps.length === 0 ? <p className="text-sm text-muted-foreground">No tool step is stored for this request.</p> : null}
      <ol className="space-y-2">
        {execution.steps.map((step) => (
          <li key={`${execution.id}-${step.sequence}`} className="rounded-md border border-border px-3 py-2 text-sm">
            <p className="font-medium">{stepTitle(step.tool_name)} · {step.status === "succeeded" ? "Completed" : step.status === "recovered" ? "Recovered" : "Needs attention"} · {step.duration_ms} ms</p>
            <ArgumentList arguments={step.arguments} />
            {step.recovery ? <p className="mt-1 text-muted-foreground">{step.recovery}</p> : null}
            {step.error_message ? <p className="mt-1 text-destructive">{step.error_message}</p> : null}
            {step.records.length > 0 ? (
              <ul className="mt-2 space-y-1">
                {step.records.slice(0, 6).map((record, index) => (
                  <li key={`${step.sequence}-${index}`}>
                    <EvidenceLink record={record} />
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        ))}
      </ol>
      {admin && (execution.tokens_in !== null || execution.tokens_out !== null) ? (
        <details className="text-sm text-muted-foreground">
          <summary className="cursor-pointer">Administrator usage</summary>
          <p className="mt-2">Tokens in {execution.tokens_in ?? 0}, out {execution.tokens_out ?? 0}. Model reasoning is not stored.</p>
        </details>
      ) : null}
    </div>
  );
}

function ArgumentList({ arguments: values }: { arguments: Record<string, unknown> }) {
  const entries = Object.entries(values).filter((entry) => typeof entry[1] === "string" || typeof entry[1] === "number" || typeof entry[1] === "boolean");
  if (entries.length === 0) {
    return null;
  }
  return (
    <p className="mt-1 text-muted-foreground">
      {entries.map(([key, value]) => `${key}: ${String(value)}`).join(" · ")}
    </p>
  );
}

function EvidenceLink({ record }: { record: Record<string, unknown> }) {
  const title = typeof record.title === "string" ? record.title : typeof record.record_type === "string" ? record.record_type : "Record";
  const excerpt = typeof record.excerpt === "string" && record.excerpt ? ` — ${record.excerpt}` : "";
  const href = recordHref(record);
  return href ? <Link className="underline" href={href}>{title}</Link> : <span>{title}{excerpt}</span>;
}

function recordHref(record: Record<string, unknown>): string | null {
  const kind = typeof record.record_type === "string" ? record.record_type : "";
  const id = typeof record.record_id === "string" ? record.record_id : "";
  if (kind === "approval" && id) {
    return `/approvals?approval=${encodeURIComponent(id)}`;
  }
  if (kind === "document") {
    return "/knowledge";
  }
  if (kind === "lead" || kind === "contact" || kind === "company" || kind === "opportunity") {
    return "/crm";
  }
  return null;
}

function statusBadge(status: string): string {
  if (status === "completed" || status === "executed" || status === "approved") return "badge badge-green";
  if (status === "failed" || status === "needs_attention" || status === "rejected") return "badge badge-red";
  if (status === "awaiting_approval" || status === "pending") return "badge badge-amber";
  return "badge badge-blue";
}

function presentedRun(run: { status: RunStatus; model_steps?: number }): { label: string; tone: string } {
  if (run.status === "completed" && (run.model_steps ?? 0) === 0) {
    return { label: "Recorded, no model steps", tone: "badge" };
  }
  return { label: run.status.replaceAll("_", " "), tone: statusBadge(run.status) };
}

function statusClass(status: string): string {
  if (status === "completed" || status === "executed" || status === "approved") {
    return "text-success";
  }
  if (status === "failed" || status === "needs_attention" || status === "rejected") {
    return "text-destructive";
  }
  if (status === "awaiting_approval" || status === "pending") {
    return "text-warning";
  }
  return "text-primary";
}

const stepLabels: Record<string, string> = {
  load_inquiry: "Inquiry loaded",
  classify: "Inquiry classified",
  retrieve_knowledge: "Company knowledge retrieved",
  lookup_customer: "Customer looked up",
  qualify: "Qualification recorded",
  propose: "Actions proposed",
  await_approval: "Waiting for a person",
  execute: "Approved actions written",
  record_outcome: "Outcome recorded",
  run: "Run stopped",
  lead_score: "Lead score recorded",
};

function stepTitle(step: string): string {
  return stepLabels[step] ?? step.replaceAll("_", " ");
}

function knowledgeHits(detail: Record<string, unknown>): { title: string; excerpt: string }[] {
  const hits = detail.hits;
  if (!Array.isArray(hits)) {
    return [];
  }
  return hits.flatMap((hit) => {
    if (!hit || typeof hit !== "object") {
      return [];
    }
    const row = hit as Record<string, unknown>;
    const title = typeof row.document_title === "string" ? row.document_title : "Untitled document";
    const excerpt = typeof row.excerpt === "string" ? row.excerpt : "";
    return [{ title, excerpt }];
  });
}

function eventOutcome(event: AgentEvent): string {
  if (event.error_message) {
    return event.error_message;
  }
  const detail = event.detail;
  if (event.step === "retrieve_knowledge") {
    const hits = knowledgeHits(detail);
    return hits.length === 0 ? "No matching document was stored." : hits.map((hit) => hit.title).join(", ");
  }
  if (event.step === "lookup_customer") {
    const lead = typeof detail.lead_id === "string" ? `lead ${detail.lead_id}` : "no existing lead";
    const contact = typeof detail.contact_id === "string" ? `contact ${detail.contact_id}` : "no contact";
    return `${contact} · ${lead}`;
  }
  if (event.step === "classify") {
    const category = typeof detail.category === "string" ? detail.category : event.status;
    const contact = typeof detail.contact_name === "string" ? detail.contact_name : "";
    return contact ? `${category} · ${contact}` : category;
  }
  if (event.step === "propose" && Array.isArray(detail.actions)) {
    return detail.actions.filter((item) => typeof item === "string").join(" · ").replaceAll("_", " ");
  }
  if (event.step === "execute") {
    return `${detail.executed ?? 0} executed, ${detail.rejected ?? 0} rejected, ${detail.failed ?? 0} failed`;
  }
  if (typeof detail.outcome === "string" && detail.outcome) {
    return detail.outcome;
  }
  if (typeof detail.qualification === "string") {
    return detail.qualification;
  }
  return event.status;
}

function runReason(detail: AgentRunDetail): string {
  const run = detail.run;
  const pending = detail.approvals.filter((item) => item.status === "pending").length;
  if (run.error_code === "llm_unconfigured") {
    return "The language model key is empty, so this run was stored as failed. No classification was invented.";
  }
  if (run.error_code === "interrupted") {
    return "The API restarted while this run was still marked running. It was not continued automatically.";
  }
  if (run.status === "failed") {
    return run.error_message ?? "The run failed and the failure was stored. Later steps were not written.";
  }
  if (run.status === "awaiting_approval") {
    return `Waiting for an admin. ${pending} proposal${pending === 1 ? "" : "s"} still need a decision in Approvals. Nothing is written until Execute.`;
  }
  if (run.status === "completed" && detail.events.length === 0) {
    return "This run is stored as finished. No model steps were recorded, so it is not a successful language-model execution.";
  }
  if (run.status === "completed") {
    return "The run finished. Executed proposals are listed below. Rejected proposals were not written.";
  }
  return "The run is still in progress. Steps appear as they are stored.";
}

function nextAction(detail: AgentRunDetail): string {
  if (detail.run.status === "awaiting_approval") {
    return "Open Approvals and decide each pending proposal. Execute is the step that writes CRM data or sends sandbox email.";
  }
  if (detail.run.status === "failed") {
    return "This failure stays in the history. Start a new run after the cause is fixed. Resume does not rewrite a failed run.";
  }
  if (detail.run.status === "completed") {
    return "Nothing else is waiting. The execution results below are the stored outcome.";
  }
  return "Resume continues a paused run. A pending proposal still has to be decided first.";
}

function runDuration(started: string, finished: string | null, status: RunStatus): string {
  const start = new Date(started).getTime();
  if (!Number.isFinite(start)) {
    return "Not stored";
  }
  if (!finished && status !== "running" && status !== "awaiting_approval") {
    return "End not stored";
  }
  const end = finished ? new Date(finished).getTime() : Date.now();
  if (!Number.isFinite(end) || end < start) {
    return "Not stored";
  }
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) {
    return finished ? `${seconds}s` : `${seconds}s so far`;
  }
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  const clock = rest === 0 ? `${minutes}m` : `${minutes}m ${rest}s`;
  return finished ? clock : `${clock} so far`;
}

const toolSteps = new Set(["classify", "retrieve_knowledge", "lookup_customer"]);

function ToolCalls({ events }: { events: AgentEvent[] }) {
  const calls = events.filter((event) => toolSteps.has(event.step));
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium">Tool calls</h3>
      {calls.length === 0 ? (
        <p className="text-sm text-muted-foreground">No tool call is stored for this run.</p>
      ) : null}
      {calls.map((event) => (
        <p key={event.id} className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{stepTitle(event.step)}</span>
          {` · ${eventOutcome(event)}`}
        </p>
      ))}
    </div>
  );
}

function SupportingRecords({ detail }: { detail: AgentRunDetail }) {
  const documents = detail.events.flatMap((event) => knowledgeHits(event.detail).map((hit) => hit.title));
  const leadId = relatedLeadId(detail) ?? lookupLead(detail);
  const titles = [...new Set(documents)];
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium">Supporting records</h3>
      <p className="text-sm text-muted-foreground">
        Inquiry: {detail.run.inquiry_subject}.{" "}
        <Link className="underline" href="/crm?tab=inquiries">Open inquiries</Link>
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        Lead: {leadId ?? "not stored on this run"}.
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        Documents: {titles.length === 0 ? "none stored on the knowledge step" : titles.join(", ")}
      </p>
    </div>
  );
}

function lookupLead(detail: AgentRunDetail): string | null {
  for (const event of detail.events) {
    if (event.step === "lookup_customer" && typeof event.detail.lead_id === "string" && event.detail.lead_id) {
      return event.detail.lead_id;
    }
  }
  return null;
}

function relatedLeadId(detail: AgentRunDetail): string | null {
  for (const approval of detail.approvals) {
    const leadId = approval.payload.lead_id ?? approval.execution_result?.lead_id;
    if (typeof leadId === "string" && leadId) {
      return leadId;
    }
  }
  return null;
}

function RunDetail({
  organizationId,
  detail,
  pending,
  error,
  onResume,
}: {
  organizationId: string;
  detail: AgentRunDetail;
  pending: boolean;
  error: unknown;
  onResume: () => void;
}) {
  const trace = useQuery({
    queryKey: ["diagnostic-run", organizationId, detail.run.id],
    queryFn: () => getDiagnosticRun(organizationId, detail.run.id),
  });
  const waiting = detail.approvals.some((item) => item.status === "pending");
  const canResume = detail.run.status === "awaiting_approval" || detail.run.status === "running";
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg text-foreground">{detail.run.inquiry_subject}</h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">{runReason(detail)}</p>
          <p className="mt-1 text-sm leading-6 text-primary">Next: {nextAction(detail)}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            <Link className="underline" href="/crm?tab=inquiries">Inquiries</Link>
            {" · "}
            Related lead {relatedLeadId(detail) ?? "not in the proposal yet"}.
          </p>
          {detail.run.error_code ? (
            <p className="mt-1 text-sm text-muted-foreground">Code: {detail.run.error_code}</p>
          ) : null}
        </div>
        <p className={`text-xs uppercase tracking-[0.12em] ${statusClass(detail.run.status)}`}>{detail.run.status.replaceAll("_", " ")}</p>
      </div>
      {canResume ? (
        <div className="space-y-2">
          <Button type="button" disabled={pending || waiting} onClick={onResume}>
            {pending ? "Resuming" : "Resume run"}
          </Button>
          {waiting ? (
            <p className="text-sm text-muted-foreground">An admin has to approve or reject the proposed actions.</p>
          ) : null}
          {error ? <RequestError error={error} /> : null}
        </div>
      ) : null}
      {trace.data ? (
        <div>
          <h3 className="mb-2 text-sm font-medium">Recorded operations</h3>
          <p className="mb-2 text-sm text-muted-foreground">{trace.data.hint_notice}</p>
          {trace.data.traces.length === 0 ? <p className="text-sm text-muted-foreground">No operation trace is stored for this run.</p> : null}
          {trace.data.traces.map((item, index) => (
            <p key={`${item.operation}-${index}`} className="text-sm text-muted-foreground">
              {item.operation} {item.status}.
              {item.latency_ms !== null ? ` ${item.latency_ms} ms.` : ""}
              {item.error_code ? ` ${item.error_code}.` : ""}
            </p>
          ))}
        </div>
      ) : null}
      <ToolCalls events={detail.events} />
      <SupportingRecords detail={detail} />
      <div>
        <h3 className="mb-2 text-sm font-medium">Timeline</h3>
        <ol className="space-y-2">
          {detail.events.length === 0 ? <li className="text-sm text-muted-foreground">No steps are stored for this run.</li> : null}
          {detail.events.map((event) => (
            <li key={event.id} className="rounded-[10px] bg-secondary px-3 py-2 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{stepTitle(event.step)}</span>
                <span className={`text-xs uppercase tracking-[0.12em] ${statusClass(event.status)}`}>{event.status}</span>
              </div>
              <p className="mt-1 text-muted-foreground">{eventOutcome(event)}</p>
              <p className="mt-1 text-xs text-subtle">{new Date(event.created_at).toLocaleString()}</p>
              {knowledgeHits(event.detail).map((hit) => (
                <p key={`${event.id}-${hit.title}`} className="mt-2 whitespace-pre-wrap text-muted-foreground">
                  {hit.title}{hit.excerpt ? ` — ${hit.excerpt}` : ""}
                </p>
              ))}
            </li>
          ))}
        </ol>
      </div>
      <div>
        <h3 className="mb-2 text-sm font-medium">Proposed actions</h3>
        {detail.approvals.length === 0 ? <p className="text-sm text-muted-foreground">No actions have been proposed.</p> : null}
        <div className="space-y-3">
          {detail.approvals.map((approval) => (
            <article key={approval.id} className="rounded-[10px] bg-secondary p-3 text-sm">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="font-medium">{actionLabel(approval.action_type)}</span>
                <span className={`text-xs uppercase tracking-[0.12em] ${statusClass(approval.status)}`}>{approval.status}</span>
              </div>
              <p className="text-sm font-medium">{proposalChange(approval.action_type, approval.payload)}</p>
              <p className="mt-1 text-sm text-muted-foreground">Affected: {proposalTarget(approval.payload)}</p>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">{proposalRisk(approval.action_type)}</p>
              <Link className="mt-3 inline-block text-sm text-primary underline" href={`/approvals?approval=${approval.id}`}>Review proposal</Link>
              {executionSummary(approval.execution_result) ? (
                <p className="mt-2 text-muted-foreground">{executionSummary(approval.execution_result)}</p>
              ) : null}
              {approval.execution_error ? <p className="mt-2 text-destructive">{approval.execution_error}</p> : null}
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}

function StartDialog({
  organizationId,
  open,
  onOpen,
  onStarted,
}: {
  organizationId: string;
  open: boolean;
  onOpen: (open: boolean) => void;
  onStarted: (result: AgentRunDetail) => void;
}) {
  const queryClient = useQueryClient();
  const [inquiryId, setInquiryId] = useState("");
  const inquiries = useQuery({
    queryKey: ["inquiries", organizationId, "agent-start"],
    queryFn: () => listInquiries(organizationId, { pageSize: 100 }),
    enabled: open,
  });
  const start = useMutation({
    mutationFn: () => startAgentRun(organizationId, inquiryId),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["agent-runs", organizationId] });
      onStarted(result);
    },
    onError: async () => {
      await queryClient.invalidateQueries({ queryKey: ["agent-runs", organizationId] });
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Start an agent run</DialogTitle>
          <DialogDescription>The agent reads the inquiry, then waits for an admin decision before it changes CRM records.</DialogDescription>
        </DialogHeader>
        {inquiries.isPending ? <Skeleton className="h-10 w-full" /> : null}
        {inquiries.isError ? <RequestError error={inquiries.error} /> : null}
        {inquiries.data && inquiries.data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">Create an inquiry in CRM first.</p>
        ) : null}
        {inquiries.data && inquiries.data.items.length > 0 ? (
          <select className={selectClass} aria-label="Inquiry" value={inquiryId} onChange={(event) => setInquiryId(event.target.value)}>
            <option value="">Select an inquiry</option>
            {inquiries.data.items.map((inquiry) => (
              <option key={inquiry.id} value={inquiry.id}>{inquiry.subject}</option>
            ))}
          </select>
        ) : null}
        {start.isError ? <RequestError error={start.error} /> : null}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpen(false)}>Cancel</Button>
          <Button type="button" disabled={!inquiryId || start.isPending} onClick={() => start.mutate()}>
            {start.isPending ? "Starting" : "Start"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
