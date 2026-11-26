"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { DataScopeControl } from "@/components/data-scope";
import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { sessionQueryOptions } from "@/lib/api";
import { isDemoSession } from "@/lib/demo-session";
import { getDiagnosticRun, getDiagnostics, listEvaluations, startEvaluation, type DiagnosticRun } from "@/lib/intelligence";
import type { DataScope } from "@/lib/provenance";
import { useWorkspace } from "@/lib/use-workspace";

export function MonitoringScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  return organizationId ? (
    <MonitoringWorkspace key={organizationId} organizationId={organizationId} isAdmin={workspace.role === "admin"} />
  ) : <Skeleton className="h-40 w-full" />;
}

function MonitoringWorkspace({ organizationId, isAdmin }: { organizationId: string; isAdmin: boolean }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const runId = useSearchParams().get("run");
  const [scope, setScope] = useState<DataScope>("operational");
  const [checksOpen, setChecksOpen] = useState(false);
  const [eventSearch, setEventSearch] = useState("");
  const session = useQuery(sessionQueryOptions);
  const demonstration = isDemoSession(session.data);
  const diagnostics = useQuery({
    queryKey: ["diagnostics", organizationId, scope],
    queryFn: () => getDiagnostics(organizationId ?? "", scope),
    enabled: Boolean(organizationId),
  });
  const evaluations = useQuery({
    queryKey: ["evaluations", organizationId],
    queryFn: () => listEvaluations(organizationId ?? ""),
    enabled: Boolean(organizationId && checksOpen),
  });
  const detail = useQuery({
    queryKey: ["diagnostic-run", organizationId, runId],
    queryFn: () => getDiagnosticRun(organizationId ?? "", runId ?? ""),
    enabled: Boolean(organizationId && runId),
  });
  const evaluate = useMutation({
    mutationFn: () => startEvaluation(organizationId ?? ""),
    onSuccess: async () => {
      window.setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: ["evaluations", organizationId] });
      }, 1500);
    },
  });
  if (!organizationId || diagnostics.isPending) {
    return <Skeleton className="h-40 w-full" />;
  }
  if (diagnostics.isError) {
    return <RequestError error={diagnostics.error} />;
  }
  const data = diagnostics.data;
  const platform = session.isSuccess && !demonstration && data.platform_visible !== false;
  const currentWorkers = data.workers.filter((worker) => worker.generation !== "previous");
  const earlierWorkers = data.workers.filter((worker) => worker.generation === "previous");
  const latest = evaluations.data?.items[0];
  const needle = eventSearch.trim().toLowerCase();
  const failedRuns = data.failed_runs.filter((run) => [run.id, run.error_code, run.hint].some(
    (value) => value?.toLowerCase().includes(needle),
  ));
  const setRunId = (id: string | null) => router.replace(
    id ? `/monitoring?run=${encodeURIComponent(id)}` : "/monitoring", { scroll: false },
  );
  return (
    <div className="w-full min-w-0 space-y-6">
      <PageHeader title="Monitoring" eyebrow="Workspace operations">
        {platform
          ? "Review recorded failures, worker health, and work that needs a decision."
          : "Review recorded issues for this workspace."}
      </PageHeader>
      <div className={`grid gap-3 ${platform ? "md:grid-cols-3" : "md:grid-cols-2"}`}>
        <Stat label="Recorded failures" value={String(data.failed_runs.length)} detail="Open one to see what was stored. A listed failure is not still running." />
        <Stat label="Uncertain outcomes" value={String(data.retries)} detail="Attempts whose result could not be confirmed." />
        {platform ? (
          <Stat
            label="Recorded cost"
            value={data.cost_usd === null ? "Not recorded" : String(data.cost_usd)}
            detail={data.cost_notice}
          />
        ) : null}
      </div>
      <section className={`grid gap-4 ${platform ? "lg:grid-cols-2" : ""}`}>
        {platform ? (
          <div className="min-w-0 space-y-3 rounded-xl border border-border bg-card p-5">
            <h2 className="font-semibold">Background work</h2>
            <p className="text-sm text-muted-foreground">A stopped process is not a current failure. A failed status is the last error that process reported.</p>
            {currentWorkers.length === 0 ? <p className="text-sm text-muted-foreground">No background work has been recorded.</p> : null}
            {currentWorkers.map((worker) => {
              const presentation = workerPresentation(worker.status);
              return (
                <div key={worker.id} className="flex flex-wrap items-start justify-between gap-2 border-t border-border pt-3 text-sm">
                  <div className="min-w-0">
                    <p className="font-medium capitalize">{worker.kind.replaceAll("_", " ")}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Last update <time dateTime={worker.heartbeat_at}>{new Date(worker.heartbeat_at).toLocaleString()}</time>
                    </p>
                    {worker.status === "error" && worker.last_error_code ? <p className="mt-1 break-words text-xs text-destructive">{worker.last_error_code}</p> : null}
                  </div>
                  <Badge variant="secondary" className={presentation.tone}>{presentation.label}</Badge>
                </div>
              );
            })}
            {earlierWorkers.length > 0 ? (
              <details className="border-t border-border pt-3">
                <summary className="cursor-pointer text-sm text-muted-foreground">Earlier processes ({earlierWorkers.length})</summary>
                <ul className="mt-3 space-y-2">
                  {earlierWorkers.map((worker) => (
                    <li key={worker.id} className="text-sm text-muted-foreground">
                      <span className="capitalize text-foreground">{worker.kind.replaceAll("_", " ")}</span>
                      {" · replaced "}
                      <time dateTime={worker.heartbeat_at}>{new Date(worker.heartbeat_at).toLocaleString()}</time>
                      {worker.last_error_code ? <span className="mt-1 block text-xs">Recorded error: {worker.last_error_code}</span> : null}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </div>
        ) : null}
        <div className="min-w-0 space-y-3 rounded-xl border border-border bg-card p-5">
          <h2 className="font-semibold">Document indexing</h2>
          {data.ingestion_jobs.length === 0 ? <p className="text-sm text-muted-foreground">No documents are waiting to be indexed.</p> : null}
          {data.ingestion_jobs.slice(0, 8).map((job) => (
            <div key={job.id} className="flex items-center justify-between gap-3 text-sm">
              <span className="truncate">{platform ? job.document_id : "Document"}</span>
              <span className={job.status === "failed" ? "text-destructive" : "text-muted-foreground"}>{job.status} · {job.attempts}/{job.max_attempts}</span>
            </div>
          ))}
        </div>
      </section>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.8fr)]">
        <section className="min-w-0 space-y-3 rounded-xl border border-border bg-card p-5">
          <h2 className="font-semibold">Historical failures</h2>
          {data.failed_runs.length ? <Input aria-label="Search failed runs" placeholder="Search failed runs" value={eventSearch} onChange={(event) => setEventSearch(event.target.value)} /> : null}
          {failedRuns.length === 0 ? <p className="text-sm text-muted-foreground">{needle ? "No failed runs match your search." : "No failed agent runs are stored."}</p> : null}
          {failedRuns.map((run) => (
            <button
              key={run.id}
              type="button"
              aria-current={run.id === runId || undefined}
              className={`block w-full rounded-[10px] px-3 py-3 text-left text-sm ${run.id === runId ? "bg-accent" : "bg-secondary"}`}
              onClick={() => setRunId(run.id)}
            >
              <span className="font-medium">{run.error_code ?? "failed"}</span>
              {run.hint ? <span className="mt-1 block leading-5 text-muted-foreground">{run.hint}</span> : null}
            </button>
          ))}
        </section>
        <section className="min-w-0 space-y-3 rounded-xl border border-border bg-card p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">Trace</h2>
            {runId ? <Button type="button" variant="outline" size="sm" onClick={() => setRunId(null)}>Close trace</Button> : null}
          </div>
          {!runId ? <p className="text-sm text-muted-foreground">Select a failed run to see its inquiry, steps, and recorded operations.</p> : null}
          {detail.isPending && runId ? <Skeleton className="h-24 w-full" /> : null}
          {detail.isError ? <RequestError error={detail.error} /> : null}
          {detail.data ? <TraceDetail detail={detail.data} platform={platform} /> : null}
        </section>
      </div>
      <section className={`grid gap-4 ${platform ? "lg:grid-cols-2" : ""}`}>
        <div className="space-y-2 rounded-xl border border-border bg-card p-4">
          <h2 className="text-base font-semibold text-foreground">Needs attention</h2>
          {data.needs_attention.length === 0 ? <p className="text-sm text-muted-foreground">Nothing is waiting on an uncertain outcome.</p> : null}
          {data.needs_attention.map((item) => (
            <div key={item.id} className="text-sm leading-6 text-muted-foreground">
              <Link className="font-medium text-foreground underline" href={`/approvals?approval=${item.id}`}>
                {item.action_type.replaceAll("_", " ")}
              </Link>
              {item.hint ? `. ${item.hint}` : ". Review this approval before trying again."}
            </div>
          ))}
        </div>
        {platform ? <div className="space-y-2 rounded-xl border border-border bg-card p-4">
          <h2 className="text-base text-foreground">Operation timing</h2>
          <p className="text-xs leading-5 text-muted-foreground">How long recorded steps took. A missing measurement is omitted.</p>
          {data.duration_buckets.map((bucket) => (
            <p key={bucket.bucket} className="flex justify-between gap-3 text-sm text-muted-foreground">
              <span>{bucket.bucket.replaceAll("_", " ")}</span>
              <span className="tabular-nums text-foreground">{bucket.count}</span>
            </p>
          ))}
        </div> : null}
      </section>
      {platform ? <section className="space-y-2 rounded-xl border border-border bg-card p-4">
        <h2 className="text-base text-foreground">Slowest recorded steps</h2>
        {data.slowest_steps.length === 0 ? <p className="text-sm text-muted-foreground">No operation traces with latency are stored.</p> : null}
        {data.slowest_steps.map((step, index) => (
          <p key={`${step.operation}-${index}`} className="text-sm text-muted-foreground">
            {step.operation}: {step.latency_ms === null ? "latency was not recorded" : `${step.latency_ms} ms`}
            {step.agent_run_id ? (
              <>
                {" "}
                <Link className="text-primary underline" href={`/agent-runs?run=${step.agent_run_id}`}>Open the run</Link>
              </>
            ) : null}
          </p>
        ))}
      </section> : null}
      <section className="space-y-2 rounded-xl border border-border bg-card p-4">
        <h2 className="text-base font-semibold text-foreground">Integration issues</h2>
        {data.integration_failures.length === 0 ? <p className="text-sm text-muted-foreground">No failed or needs-attention workflows are stored.</p> : null}
        {data.integration_failures.map((item) => (
          <p key={item.id} className="text-sm leading-6 text-muted-foreground">
            <span className="font-medium text-foreground">{item.status}</span>
            {": "}
            {item.error ?? "no error code"}
            {item.hint ? `. ${item.hint}` : ""}
          </p>
        ))}
      </section>
      {platform ? <details className="rounded-xl border border-border bg-card p-4" onToggle={(event) => setChecksOpen(event.currentTarget.open)}>
        <summary className="cursor-pointer text-sm font-medium">Advanced diagnostics</summary>
        <DataScopeControl value={scope} onChange={setScope} advanced />
        <div className="mt-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base text-foreground">Service checks</h2>
          {isAdmin ? (
            <Button type="button" disabled={evaluate.isPending} onClick={() => evaluate.mutate()}>
              {evaluate.isPending ? "Starting" : "Run checks"}
            </Button>
          ) : (
            <p className="text-sm text-muted-foreground">An administrator can run these checks.</p>
          )}
        </div>
        {evaluations.data ? <p className="text-sm leading-6 text-muted-foreground">{evaluations.data.notice}</p> : null}
        {evaluate.isError ? <RequestError error={evaluate.error} /> : null}
        {evaluations.isPending ? <Skeleton className="h-16 w-full" /> : evaluations.isError ? (
          <RequestError error={evaluations.error} />
        ) : latest ? (
          <div className="rounded-[10px] bg-secondary p-4 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{latest.dataset_version}</span>
              <span className="text-xs uppercase tracking-[0.12em] text-subtle">{latest.method}</span>
            </div>
            <p className="mt-2 leading-6 text-muted-foreground">
              {latest.passed_count} of {latest.executed_count} checks passed. Configuration: {latest.model_configuration}.
            </p>
            {latest.results.notice ? <p className="mt-2 leading-6 text-muted-foreground">{latest.results.notice}</p> : null}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No evaluation has been stored for this organization.</p>
        )}
        </div>
      </details> : null}
    </div>
  );
}

function workerPresentation(status: string): { label: string; tone: string } {
  if (status === "error") return { label: "Failed", tone: "text-destructive" };
  if (status === "stopped") return { label: "Not running", tone: "text-muted-foreground" };
  if (status === "replaced") return { label: "Replaced", tone: "text-muted-foreground" };
  return { label: "Running", tone: "" };
}

function Stat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <section className="rounded-[10px] bg-muted p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{detail}</p>
    </section>
  );
}

function TraceDetail({ detail, platform }: { detail: DiagnosticRun; platform: boolean }) {
  return (
    <div className="space-y-3 text-sm">
      <p className="leading-6 text-muted-foreground">{detail.hint_notice}</p>
      <dl className="space-y-2">
        <div>
          <dt className="text-muted-foreground">Inquiry</dt>
          <dd>{detail.inquiry?.subject ?? "unavailable"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Run</dt>
          <dd>
            {detail.run.status}
            {detail.run.error_code ? ` · ${detail.run.error_code}` : ""}
            {" · "}
            <Link className="text-primary underline" href={`/agent-runs?run=${detail.run.id}`}>Open the run</Link>
          </dd>
        </div>
      </dl>
      {detail.run.hint ? <p className="leading-6 text-muted-foreground">{detail.run.hint}</p> : null}
      <p>Events: {detail.events.map((event) => `${event.step} (${event.status})`).join(", ") || "none"}</p>
      <p>Approvals: {detail.approvals.map((item) => `${item.action_type.replaceAll("_", " ")} ${item.status}`).join(", ") || "none"}</p>
      <p>Workflows: {detail.workflows.map((item) => `${item.status}${item.error ? ` (${item.error})` : ""}`).join(", ") || "none"}</p>
      <p>Email records: {detail.emails.length}. Calendar records: {detail.bookings.length}.</p>
      {detail.traces.length === 0 ? <p className="text-muted-foreground">No operation trace is stored for this run.</p> : null}
      {detail.traces.map((trace, index) => (
        <p key={`${trace.operation}-${index}`} className="leading-6 text-muted-foreground">
          {trace.operation} {trace.status}.
          {platform && trace.latency_ms !== null ? ` ${trace.latency_ms} ms.` : ""}
          {platform && (trace.tokens_in !== null || trace.tokens_out !== null)
            ? ` Tokens ${trace.tokens_in ?? 0}/${trace.tokens_out ?? 0}.`
            : ""}
          {platform && trace.cost_usd !== null ? ` Cost ${trace.cost_usd}.` : ""}
          {trace.error_code ? ` ${trace.error_code}.` : ""}
        </p>
      ))}
    </div>
  );
}
