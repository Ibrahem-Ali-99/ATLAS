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
import { getDiagnosticRun, getDiagnostics, listEvaluations, startEvaluation, type DiagnosticRun, type WorkspaceActivity } from "@/lib/intelligence";
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
  const [scope, setScope] = useState<DataScope>("all");
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
      <PageHeader title="Monitoring" eyebrow="Workspace operations" actions={
        demonstration ? undefined : <DataScopeControl value={scope} onChange={setScope} />
      }>
        {data.activity?.notice ?? "Current health is the latest stored state. Earlier records stay in the history below."}
        {platform ? " Infrastructure diagnostics are limited to administrators." : ""}
      </PageHeader>
      <div className="health-grid" aria-label="Recorded outcomes">
        <Stat label="Recorded failures" value={String(data.failed_runs.length)} detail="Open one to see what was stored. A listed failure is not still running." />
        <Stat label="Uncertain outcomes" value={String(data.retries)} detail="Attempts whose result could not be confirmed." />
      </div>
      {data.activity ? <ActivityHealth activity={data.activity} /> : null}
      <section className="grid gap-4">
        <div className="min-w-0 space-y-3 rounded-xl border border-border bg-card p-5">
          <h2 className="font-semibold">Document indexing</h2>
          {data.ingestion_jobs.length === 0 ? <p className="text-sm text-muted-foreground">No documents are waiting to be indexed.</p> : null}
          {data.ingestion_jobs.slice(0, 8).map((job) => (
            <div key={job.id} className="flex items-center justify-between gap-3 text-sm">
              <span className="truncate">Document</span>
              <span className={job.status === "failed" ? "text-destructive" : "text-muted-foreground"}>{job.status} · {job.attempts}/{job.max_attempts}</span>
            </div>
          ))}
        </div>
      </section>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.8fr)]">
        <section className="min-w-0 space-y-3 rounded-xl border border-border bg-card p-5">
          <h2 className="font-semibold">Earlier incidents</h2>
          <p className="text-sm text-muted-foreground">Failed agent runs stay here after they stop. Opening one does not mean it is still running.</p>
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
              <span className="font-medium">{run.hint ?? "Failed run"}</span>
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
          {detail.data ? <TraceDetail detail={detail.data} /> : null}
        </section>
      </div>
      <section className="grid gap-4">
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
      </section>
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
        <div className="space-y-2 border-t border-border pt-3">
          <h2 className="text-base text-foreground">Recorded cost</h2>
          <p className="text-sm text-muted-foreground">{data.cost_usd === null ? "Not recorded" : String(data.cost_usd)}. {data.cost_notice}</p>
        </div>
        <div className="space-y-3 border-t border-border pt-3">
          <h2 className="text-base text-foreground">Background work</h2>
          <p className="text-sm text-muted-foreground">A stopped process is not a current failure. A failed status is the last error that process reported.</p>
          {currentWorkers.length === 0 ? <p className="text-sm text-muted-foreground">No background work has been recorded.</p> : null}
          {currentWorkers.map((worker) => {
            const presentation = workerPresentation(worker.status);
            return (
              <div key={worker.id} className="flex flex-wrap items-start justify-between gap-2 text-sm">
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
            <ul className="space-y-2">
              {earlierWorkers.map((worker) => (
                <li key={worker.id} className="text-sm text-muted-foreground">
                  <span className="capitalize text-foreground">{worker.kind.replaceAll("_", " ")}</span>
                  {" · replaced "}
                  <time dateTime={worker.heartbeat_at}>{new Date(worker.heartbeat_at).toLocaleString()}</time>
                  {worker.last_error_code ? <span className="mt-1 block text-xs">Recorded error: {worker.last_error_code}</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <div className="space-y-2 border-t border-border pt-3">
          <h2 className="text-base text-foreground">Operation timing</h2>
          {data.duration_buckets.map((bucket) => (
            <p key={bucket.bucket} className="flex justify-between gap-3 text-sm text-muted-foreground">
              <span>{bucket.bucket.replaceAll("_", " ")}</span>
              <span className="tabular-nums text-foreground">{bucket.count}</span>
            </p>
          ))}
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
        </div>
        </div>
      </details> : null}
    </div>
  );
}

function ActivityHealth({ activity }: { activity: WorkspaceActivity }) {
  const assistant = assistantHealth(activity.assistant.status);
  return (
    <section className="space-y-4" aria-label="Current service health">
      <div>
        <h2 className="text-base font-semibold">Current health</h2>
        <p className="mt-1 text-sm text-muted-foreground">These figures are the latest stored state for this workspace. They are not a live probe of an outside provider.</p>
      </div>
      <div className="health-grid" aria-label="Current service health">
        <HealthCard title="Assistant" value={assistant.label} detail={assistantDetail(activity)} tone={assistant.tone} />
        <HealthCard
          title="Knowledge indexing"
          value={activity.knowledge.indexing + activity.knowledge.retrying > 0 ? "Indexing" : activity.knowledge.failed > 0 ? "Failed documents" : "Idle"}
          detail={`${activity.knowledge.ready} ready, ${activity.knowledge.indexing} indexing, ${activity.knowledge.failed} failed, ${activity.knowledge.retrying} jobs still open.`}
        />
        <HealthCard
          title="Workflow executions"
          value={String(activity.workflows.running + activity.workflows.needs_attention)}
          detail={`${activity.workflows.running} in progress, ${activity.workflows.needs_attention} need attention, ${activity.workflows.failed} failed, ${activity.workflows.completed} completed.`}
        />
        <HealthCard
          title="Connections"
          value={connectionSummary(activity)}
          detail="Configured, verified, unavailable, and authentication states come from the last stored check. Monitoring does not send a message or start a payment."
        />
        <HealthCard
          title="Message delivery"
          value={String(activity.delivery.sent + activity.delivery.failed + activity.delivery.needs_attention)}
          detail={`${activity.delivery.sent} sent, ${activity.delivery.failed} failed, ${activity.delivery.needs_attention} need attention. Simulated campaign rows are not included.`}
        />
        <HealthCard
          title="Approval delays"
          value={String(activity.approvals.delayed)}
          detail={approvalDetail(activity)}
        />
      </div>
      <ConnectionList activity={activity} />
      <div className="rounded-xl border border-border bg-card p-4">
        <h3 className="text-base font-semibold">Recoverable failures</h3>
        {activity.recoverable.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">Nothing stored can be retried from here.</p> : null}
        <ul className="mt-2 space-y-2">
          {activity.recoverable.map((item) => (
            <li key={`${item.kind}-${item.id ?? item.summary}`} className="text-sm text-muted-foreground">
              {item.kind === "approval" && item.id ? (
                <Link className="font-medium text-foreground underline" href={`/approvals?approval=${item.id}`}>{item.summary.replaceAll("_", " ")}</Link>
              ) : item.kind === "indexing" ? (
                <Link className="font-medium text-foreground underline" href="/knowledge">Document indexing</Link>
              ) : (
                <span className="font-medium text-foreground">{item.kind}</span>
              )}
              {` · ${item.summary.replaceAll("_", " ")}`}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function connectionSummary(activity: WorkspaceActivity): string {
  if (activity.integrations.length === 0) {
    return "None stored";
  }
  const verified = activity.integrations.filter((item) => (item.health ?? (item.verified ? "connected" : "configured")) === "connected").length;
  return `${verified} verified`;
}

function connectionLabel(health: string | undefined, verified: boolean): string {
  if (health === "connected" || (!health && verified)) {
    return "Connected and verified";
  }
  if (health === "authentication_required") {
    return "Authentication required";
  }
  if (health === "unavailable") {
    return "Temporarily unavailable";
  }
  if (health === "failed") {
    return "Failed operation";
  }
  return "Configured";
}

function ConnectionList({ activity }: { activity: WorkspaceActivity }) {
  const incidents = activity.connection_incidents ?? [];
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-xl border border-border bg-card p-4">
        <h3 className="text-base font-semibold">Connection checks</h3>
        {activity.integrations.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No connection is stored.</p> : null}
        <ul className="mt-2 space-y-3">
          {activity.integrations.map((item) => (
            <li key={`${item.type}-${item.provider}`} className="text-sm">
              <p className="font-medium capitalize">{item.provider} · {connectionLabel(item.health, item.verified)}</p>
              <p className="mt-1 text-muted-foreground">
                {item.verified_at ? (
                  <>Last verified <time dateTime={item.verified_at}>{new Date(item.verified_at).toLocaleString()}</time></>
                ) : "No successful verification is stored."}
              </p>
              {item.recovery && item.recovery_href ? (
                <Link className="mt-1 inline-block underline" href={item.recovery_href}>{item.recovery}</Link>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
      <div className="rounded-xl border border-border bg-card p-4">
        <h3 className="text-base font-semibold">Historical incidents</h3>
        <p className="mt-1 text-sm text-muted-foreground">Failures older than the current health window. They do not change the connection state above.</p>
        {incidents.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No older connection failure is stored.</p> : null}
        <ul className="mt-2 space-y-2">
          {incidents.map((item) => (
            <li key={`${item.provider}-${item.at}`} className="text-sm text-muted-foreground">
              <span className="font-medium capitalize text-foreground">{item.provider}</span>
              {" · "}
              {item.error_code ?? item.operation}
              {" · "}
              <time dateTime={item.at}>{new Date(item.at).toLocaleString()}</time>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function assistantHealth(status: WorkspaceActivity["assistant"]["status"]): { label: string; tone?: string } {
  if (status === "errors") return { label: "Latest reply failed", tone: "text-destructive" };
  if (status === "available") return { label: "Latest reply stored", tone: "text-success" };
  return { label: "No recent reply" };
}

function assistantDetail(activity: WorkspaceActivity): string {
  const assistant = activity.assistant;
  const current = `${assistant.recent_replies} replies in the last 24 hours, ${assistant.recent_errors} failed.`;
  const code = assistant.last_error_code ? ` Latest error code: ${assistant.last_error_code}.` : "";
  const earlier = assistant.earlier_errors > 0
    ? ` ${assistant.earlier_errors} older assistant failures stay in the history and are not the current status.`
    : "";
  return `${current}${code}${earlier}`;
}

function approvalDetail(activity: WorkspaceActivity): string {
  const pending = activity.approvals.pending;
  const hours = activity.approvals.oldest_pending_hours;
  const age = hours === null ? "No pending approval is stored." : `Oldest pending approval is ${hours} hours old.`;
  return `${pending} pending. ${activity.approvals.delayed} have waited at least 24 hours. ${age}`;
}

function HealthCard({ title, value, detail, tone }: { title: string; value: string; detail: string; tone?: string }) {
  const badge = tone?.includes("destructive") ? "badge badge-red" : tone?.includes("success") ? "badge badge-green" : "badge badge-neutral";
  return (
    <article className="panel health-card">
      <span className="health-icon badge-blue">{title.slice(0, 1)}</span>
      <div><strong>{title}</strong><small>{detail}</small></div>
      <span className={badge}>{value}</span>
    </article>
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
    <article className="panel health-card">
      <div><strong>{label}</strong><small>{detail}</small></div>
      <span className="badge badge-neutral">{value}</span>
    </article>
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
          {trace.error_code ? ` ${trace.error_code}.` : ""}
        </p>
      ))}
    </div>
  );
}
