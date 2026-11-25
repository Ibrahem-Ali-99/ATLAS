"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { DataScopeControl } from "@/components/data-scope";
import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getDiagnosticRun, getDiagnostics, listEvaluations, startEvaluation, type DiagnosticRun } from "@/lib/intelligence";
import type { DataScope } from "@/lib/provenance";
import { useWorkspace } from "@/lib/use-workspace";

export function MonitoringScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const queryClient = useQueryClient();
  const requestedRun = useSearchParams().get("run");
  const [runId, setRunId] = useState<string | null>(requestedRun);
  const [scope, setScope] = useState<DataScope>("operational");
  const diagnostics = useQuery({
    queryKey: ["diagnostics", organizationId, scope],
    queryFn: () => getDiagnostics(organizationId ?? "", scope),
    enabled: Boolean(organizationId),
  });
  const evaluations = useQuery({
    queryKey: ["evaluations", organizationId],
    queryFn: () => listEvaluations(organizationId ?? ""),
    enabled: Boolean(organizationId),
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
  if (!organizationId || diagnostics.isPending || evaluations.isPending) {
    return <Skeleton className="h-40 w-full" />;
  }
  if (diagnostics.isError) {
    return <RequestError error={diagnostics.error} />;
  }
  if (evaluations.isError) {
    return <RequestError error={evaluations.error} />;
  }
  const data = diagnostics.data;
  const latest = evaluations.data.items[0];
  return (
    <div className="w-full space-y-6">
      <div>
        <h1 className="text-[31px] leading-none text-foreground">Monitoring</h1>
        <DataScopeControl value={scope} onChange={setScope} />
        <p className="mt-3 max-w-3xl text-sm text-muted-foreground">{data.hint_notice}</p>
        <p className="mt-2 max-w-3xl text-xs leading-5 text-subtle">
          Failed runs are historical records. Needs attention and integration failures are outcomes that still need a look.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Stat label="Stored failures" value={String(data.failed_runs.length)} detail="Selecting one opens its recorded trace. It does not mean the failure is still running." />
        <Stat label="Uncertain attempts" value={String(data.retries)} detail="Retries and outcomes that could not be confirmed." />
        <Stat
          label="Recorded cost"
          value={data.cost_usd === null ? "Not recorded" : String(data.cost_usd)}
          detail={data.cost_notice}
        />
      </div>
      <section className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2 rounded-[10px] bg-muted p-4">
          <h2 className="text-base text-foreground">Worker health</h2>
          {data.workers.length === 0 ? <p className="text-sm text-muted-foreground">No worker heartbeat has been recorded.</p> : null}
          {data.workers.map((worker) => (
            <div key={worker.id} className="flex items-center justify-between gap-3 text-sm">
              <span>{worker.kind}</span>
              <span className={worker.status === "stalled" || worker.status === "error" ? "text-destructive" : "text-success"}>{worker.status}</span>
            </div>
          ))}
        </div>
        <div className="space-y-2 rounded-[10px] bg-muted p-4">
          <h2 className="text-base text-foreground">Knowledge jobs</h2>
          {data.ingestion_jobs.length === 0 ? <p className="text-sm text-muted-foreground">No ingestion jobs are recorded.</p> : null}
          {data.ingestion_jobs.slice(0, 8).map((job) => (
            <div key={job.id} className="flex items-center justify-between gap-3 text-sm">
              <span className="truncate">{job.document_id}</span>
              <span className={job.status === "failed" ? "text-destructive" : "text-muted-foreground"}>{job.status} · {job.attempts}/{job.max_attempts}</span>
            </div>
          ))}
        </div>
      </section>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.8fr)]">
        <section className="space-y-3 rounded-[10px] bg-muted p-4">
          <h2 className="text-base text-foreground">Historical failures</h2>
          {data.failed_runs.length === 0 ? <p className="text-sm text-muted-foreground">No failed agent runs are stored.</p> : null}
          {data.failed_runs.map((run) => (
            <button
              key={run.id}
              type="button"
              className={`block w-full rounded-[10px] px-3 py-3 text-left text-sm ${run.id === runId ? "bg-accent" : "bg-secondary"}`}
              onClick={() => setRunId(run.id)}
            >
              <span className="font-medium">{run.error_code ?? "failed"}</span>
              {run.hint ? <span className="mt-1 block leading-5 text-muted-foreground">{run.hint}</span> : null}
            </button>
          ))}
        </section>
        <section className="space-y-3 rounded-[10px] bg-muted p-4">
          <h2 className="text-base text-foreground">Trace</h2>
          {!runId ? <p className="text-sm text-muted-foreground">Select a failed run to see its inquiry, steps, and recorded operations.</p> : null}
          {detail.isPending && runId ? <Skeleton className="h-24 w-full" /> : null}
          {detail.isError ? <RequestError error={detail.error} /> : null}
          {detail.data ? <TraceDetail detail={detail.data} /> : null}
        </section>
      </div>
      <section className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2 rounded-[10px] bg-muted p-4">
          <h2 className="text-base text-foreground">Needs a look</h2>
          {data.needs_attention.length === 0 ? <p className="text-sm text-muted-foreground">No approval is waiting because its outcome was uncertain.</p> : null}
          {data.needs_attention.map((item) => (
            <div key={item.id} className="text-sm leading-6 text-muted-foreground">
              <Link className="font-medium text-foreground underline" href={`/approvals?approval=${item.id}`}>
                {item.action_type.replaceAll("_", " ")}
              </Link>
              {item.hint ? `. ${item.hint}` : ". Review the approval before deciding whether reconciliation is safe."}
            </div>
          ))}
        </div>
        <div className="space-y-2 rounded-[10px] bg-muted p-4">
          <h2 className="text-base text-foreground">Operation latency</h2>
          <p className="text-xs leading-5 text-muted-foreground">Counts of stored traces that reported a latency. A missing price or usage is not shown here.</p>
          {data.duration_buckets.map((bucket) => (
            <p key={bucket.bucket} className="flex justify-between gap-3 text-sm text-muted-foreground">
              <span>{bucket.bucket.replaceAll("_", " ")}</span>
              <span className="tabular-nums text-foreground">{bucket.count}</span>
            </p>
          ))}
        </div>
      </section>
      <section className="space-y-2 rounded-[10px] bg-muted p-4">
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
      </section>
      <section className="space-y-2 rounded-[10px] bg-muted p-4">
        <h2 className="text-base text-foreground">Integration failures</h2>
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
      <section className="space-y-3 rounded-[10px] bg-muted p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base text-foreground">Evaluation</h2>
          {workspace.role === "admin" ? (
            <Button type="button" disabled={evaluate.isPending} onClick={() => evaluate.mutate()}>
              {evaluate.isPending ? "Starting" : "Run checks"}
            </Button>
          ) : (
            <p className="text-sm text-muted-foreground">An admin starts a stored evaluation.</p>
          )}
        </div>
        <p className="text-sm leading-6 text-muted-foreground">{evaluations.data.notice}</p>
        {evaluate.isError ? <RequestError error={evaluate.error} /> : null}
        {latest ? (
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
      </section>
    </div>
  );
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

function TraceDetail({ detail }: { detail: DiagnosticRun }) {
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
          {trace.latency_ms === null ? " Latency was not recorded." : ` ${trace.latency_ms} ms.`}
          {trace.tokens_in === null && trace.tokens_out === null
            ? " Tokens were not recorded."
            : ` Tokens ${trace.tokens_in ?? 0}/${trace.tokens_out ?? 0}.`}
          {trace.cost_usd === null ? " Cost was not recorded." : ` Cost ${trace.cost_usd}.`}
          {` Langfuse ${trace.langfuse_status}.`}
        </p>
      ))}
    </div>
  );
}
