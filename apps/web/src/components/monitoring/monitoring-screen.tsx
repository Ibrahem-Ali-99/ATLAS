"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getDiagnosticRun, getDiagnostics, listEvaluations, startEvaluation } from "@/lib/intelligence";
import { useWorkspace } from "@/lib/use-workspace";

export function MonitoringScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const queryClient = useQueryClient();
  const [runId, setRunId] = useState<string | null>(null);
  const diagnostics = useQuery({
    queryKey: ["diagnostics", organizationId],
    queryFn: () => getDiagnostics(organizationId ?? ""),
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
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Monitoring</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{data.hint_notice}</p>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <p className="rounded-xl border border-border p-4 text-sm">Failed agent runs: {data.failed_runs.length}</p>
        <p className="rounded-xl border border-border p-4 text-sm">Retry or uncertain attempts: {data.retries}</p>
        <p className="rounded-xl border border-border p-4 text-sm">
          Cost: {data.cost_usd === null ? "unavailable" : data.cost_usd} . {data.cost_notice}
        </p>
      </div>
      <section className="space-y-2">
        <h2 className="text-lg font-medium">Failed runs</h2>
        {data.failed_runs.length === 0 ? <p className="text-sm text-muted-foreground">No failed agent runs are stored.</p> : null}
        {data.failed_runs.map((run) => (
          <button key={run.id} type="button" className="block w-full rounded-md border border-border p-3 text-left text-sm" onClick={() => setRunId(run.id)}>
            <span className="font-medium">{run.error_code ?? "failed"}</span>
            {run.hint ? <span className="mt-1 block text-muted-foreground">{run.hint}</span> : null}
          </button>
        ))}
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-medium">Slowest recorded steps</h2>
        {data.slowest_steps.length === 0 ? <p className="text-sm text-muted-foreground">No operation traces with latency are stored.</p> : null}
        {data.slowest_steps.map((step, index) => (
          <p key={`${step.operation}-${index}`} className="text-sm text-muted-foreground">
            {step.operation}: {step.latency_ms ?? "unavailable"} ms
          </p>
        ))}
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-medium">Integration failures</h2>
        {data.integration_failures.length === 0 ? <p className="text-sm text-muted-foreground">No failed or needs-attention workflows are stored.</p> : null}
        {data.integration_failures.map((item) => (
          <p key={item.id} className="text-sm text-muted-foreground">
            {item.status}: {item.error ?? "no error code"}{item.hint ? `. Hint: ${item.hint}` : ""}
          </p>
        ))}
      </section>
      {detail.data ? (
        <section className="space-y-2 rounded-xl border border-border p-4">
          <h2 className="text-lg font-medium">Trace</h2>
          <p className="text-sm text-muted-foreground">{detail.data.hint_notice}</p>
          <p className="text-sm">Inquiry: {detail.data.inquiry?.subject ?? "unavailable"}</p>
          <p className="text-sm">Run status: {detail.data.run.status}. Error: {detail.data.run.error_code ?? "none"}</p>
          {detail.data.run.hint ? <p className="text-sm text-muted-foreground">Hint: {detail.data.run.hint}</p> : null}
          <p className="text-sm">Events: {detail.data.events.map((event) => event.step).join(", ") || "none"}</p>
          <p className="text-sm">Approvals: {detail.data.approvals.map((item) => `${item.action_type} ${item.status}`).join(", ") || "none"}</p>
          <p className="text-sm">Workflows: {detail.data.workflows.map((item) => item.status).join(", ") || "none"}</p>
          <p className="text-sm">Email records: {detail.data.emails.length}. Calendar records: {detail.data.bookings.length}</p>
          {detail.data.traces.map((trace, index) => (
            <p key={`${trace.operation}-${index}`} className="text-sm text-muted-foreground">
              {trace.operation} {trace.status}. Tokens in: {trace.tokens_in ?? "unavailable"}. Tokens out: {trace.tokens_out ?? "unavailable"}. Cost: {trace.cost_usd ?? "unavailable"}. Langfuse: {trace.langfuse_status}
            </p>
          ))}
        </section>
      ) : null}
      {detail.isError ? <RequestError error={detail.error} /> : null}
      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-medium">Evaluation</h2>
          {workspace.role === "admin" ? (
            <Button type="button" disabled={evaluate.isPending} onClick={() => evaluate.mutate()}>
              {evaluate.isPending ? "Starting" : "Run checks"}
            </Button>
          ) : null}
        </div>
        <p className="text-sm text-muted-foreground">{evaluations.data.notice}</p>
        {latest ? (
          <div className="rounded-xl border border-border p-4 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span>{latest.dataset_version}</span>
              <Badge variant="secondary">{latest.method}</Badge>
            </div>
            <p className="mt-2 text-muted-foreground">
              {latest.passed_count} of {latest.executed_count} checks passed. Configuration: {latest.model_configuration}.
            </p>
            {latest.results.notice ? <p className="mt-2 text-muted-foreground">{latest.results.notice}</p> : null}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No evaluation has been stored for this organization.</p>
        )}
      </section>
    </div>
  );
}
