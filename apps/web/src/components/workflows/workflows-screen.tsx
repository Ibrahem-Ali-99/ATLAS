"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { DataScopeControl } from "@/components/data-scope";
import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cancelBooking, getAutomations, type AutomationSnapshot, type WorkflowRun } from "@/lib/automations";
import type { DataScope } from "@/lib/provenance";
import { useWorkspace } from "@/lib/use-workspace";
import { createWorkflowDefinition, createWorkflowTask, deleteWorkflowDefinition, listWorkflowDefinitions, listWorkflowTasks, updateWorkflowTask, workflowAction } from "@/lib/workflow-definitions";

export function WorkflowsScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [scope, setScope] = useState<DataScope>("operational");
  const automations = useQuery({
    queryKey: ["automations", organizationId, scope],
    queryFn: () => getAutomations(organizationId ?? "", scope),
    enabled: Boolean(organizationId),
  });
  const cancel = useMutation({
    mutationFn: (bookingId: string) => cancelBooking(organizationId ?? "", bookingId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["automations", organizationId] });
    },
  });
  if (!organizationId || automations.isPending) {
    return <Skeleton className="h-40 w-full" />;
  }
  if (automations.isError) {
    return <RequestError error={automations.error} />;
  }
  return (
    <WorkflowsBody
      data={automations.data}
      scope={scope}
      onScope={setScope}
      kind={kind}
      onKind={setKind}
      status={status}
      onStatus={setStatus}
      isAdmin={workspace.role === "admin"}
      cancelPending={cancel.isPending}
      cancelError={cancel.error}
      onCancel={(bookingId) => cancel.mutate(bookingId)}
    />
  );
}

function WorkflowsBody({
  data,
  scope,
  onScope,
  kind,
  onKind,
  status,
  onStatus,
  isAdmin,
  cancelPending,
  cancelError,
  onCancel,
}: {
  data: AutomationSnapshot;
  scope: DataScope;
  onScope: (scope: DataScope) => void;
  kind: string | null;
  onKind: (kind: string | null) => void;
  status: string | null;
  onStatus: (status: string | null) => void;
  isAdmin: boolean;
  cancelPending: boolean;
  cancelError: unknown;
  onCancel: (bookingId: string) => void;
}) {
  const [view, setView] = useState<"overview" | "approvals" | "history" | "email">("overview");
  const [search, setSearch] = useState("");
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null);
  const visible = data.runs.filter((run) => (!kind || run.kind === kind) && (!status || run.status === status));
  const searched = visible.filter((run) => `${run.kind} ${run.lead_title ?? ""} ${run.company_name ?? ""} ${run.status}`.toLowerCase().includes(search.trim().toLowerCase()));
  const focus = data.automations.find((item) => item.kind === kind);
  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <header>
        <h1 className="text-3xl font-semibold leading-tight text-foreground">Workflows</h1>
        <p className="mt-3 max-w-4xl text-sm text-muted-foreground">
          Read-only workflow topology and observable execution outcomes.
        </p>
        <p className="mt-2 max-w-4xl text-xs leading-5 text-subtle">{configurationCopy(data)}</p>
        <DataScopeControl value={scope} onChange={onScope} />
      </header>
      <WorkflowTopology data={data} />
      {isAdmin ? <WorkflowBuilder /> : null}
      <WorkflowTaskList />
      <nav className="flex flex-wrap gap-2 border-b border-border pb-3" aria-label="Automation workspace views">
        {([ ["overview", "Overview"], ["approvals", "Approvals"], ["history", "Execution history"], ["email", "Email activity"] ] as const).map(([id, label]) => (
          <button key={id} type="button" className={`rounded-md px-3 py-2 text-sm ${view === id ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground"}`} aria-pressed={view === id} onClick={() => setView(id)}>{label}</button>
        ))}
      </nav>
      {view === "overview" ? <section className="grid gap-4 lg:grid-cols-2">
        {data.automations.map((automation) => (
          <article key={automation.kind} className="flex min-h-52 flex-col rounded-[10px] bg-muted px-6 py-6">
            <div className="flex items-start justify-between gap-4">
              <h2 className="text-[21px] text-foreground">{automation.name}</h2>
              <p className={`text-[11px] uppercase tracking-[0.12em] ${automation.configured ? "text-success" : "text-warning"}`}>
                {automation.configured ? "Active" : "Not configured"}
              </p>
            </div>
            <p className="mt-5 text-[11px] uppercase tracking-[0.12em] text-subtle">
              Trigger / {triggerLabel(automation.trigger)}
            </p>
            <p className="mt-3 text-[13px] text-muted-foreground">{automation.description}</p>
            <div className="mt-auto flex items-center justify-between gap-3 pt-8">
              {automation.awaiting_review > 0 ? (
                <Link href="/approvals" className="text-base text-foreground">
                  {outcomeCopy(automation)}
                </Link>
              ) : (
                <p className="text-base text-foreground">{outcomeCopy(automation)}</p>
              )}
              <button
                type="button"
                className="text-xs text-primary"
                onClick={() => {
                  onKind(automation.kind);
                  document.getElementById("execution-history")?.scrollIntoView({ block: "start" });
                }}
              >
                Inspect runs →
              </button>
            </div>
          </article>
        ))}
      </section> : null}
      {view === "approvals" ? <section className="rounded-[10px] bg-muted px-5 py-6"><h2 className="text-xl text-foreground">Human approvals</h2><p className="mt-2 max-w-2xl text-sm text-muted-foreground">Review proposed CRM changes and customer responses in the existing approval workspace. Approval and execution permissions remain enforced by the API.</p><Link className="mt-5 inline-block text-sm text-primary underline" href="/approvals">Open approvals →</Link></section> : null}
      {view === "history" || view === "overview" ? <section id="execution-history" className="rounded-[10px] bg-muted px-5 py-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-[22px] text-foreground">Execution history</h2>
            <p className="mt-2 text-xs text-muted-foreground">
              Actual outcomes are stored. This page does not start, edit, or retry a run.
            </p>
          </div>
          {focus ? (
            <button type="button" className="text-xs text-primary" onClick={() => onKind(null)}>
              Show all · {focus.name}
            </button>
          ) : null}
          <label className="text-xs text-muted-foreground">Search
            <input aria-label="Search execution history" className="ml-2 h-8 rounded-md border border-border bg-background px-2 text-xs text-foreground" placeholder="Customer or process" value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
          <label className="text-xs text-muted-foreground">
            Status
            <select aria-label="Filter execution history" className="ml-2 h-8 rounded-md border border-border bg-background px-2 text-xs text-foreground" value={status ?? ""} onChange={(event) => onStatus(event.target.value || null)}>
              <option value="">All statuses</option>
              <option value="running">Running</option>
              <option value="awaiting_approval">Awaiting approval</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="executing">Executing</option>
              <option value="queued">Queued</option>
              <option value="dispatching">Dispatching</option>
              <option value="completed">Completed</option>
              <option value="accepted">Accepted by SMTP</option>
              <option value="rejected">Rejected</option>
              <option value="failed">Failed</option>
              <option value="needs_attention">Needs attention</option>
            </select>
          </label>
        </div>
        {searched.length === 0 ? (
          <p className="mt-6 text-sm text-muted-foreground">No workflow runs are stored for this view.</p>
        ) : (
          <div className="mt-5 overflow-x-auto">
            <div className="hidden min-w-[40rem] grid-cols-[minmax(8rem,1fr)_minmax(10rem,1.3fr)_minmax(8rem,1fr)_6rem] gap-3 rounded-[10px] bg-secondary px-4 py-3 text-[10px] uppercase tracking-[0.12em] text-subtle md:grid">
              <span>Process</span>
              <span>Business record</span>
              <span>Status</span>
              <span>Time</span>
            </div>
            <ul className="min-w-0 md:min-w-[40rem]">
                {searched.map((run) => (
                <HistoryRow key={run.id} run={run} onSelect={setSelectedRun} />
              ))}
            </ul>
          </div>
        )}
      </section> : null}
      {selectedRun ? <ExecutionDetail run={selectedRun} onClose={() => setSelectedRun(null)} /> : null}
      {view === "email" || view === "overview" ? <EmailActivitySection emails={data.emails} /> : null}
      {data.bookings.length > 0 ? (
        <section className="rounded-[10px] bg-muted px-5 py-6">
          <h2 className="text-lg text-foreground">Calendar bookings</h2>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            {data.calendar_provider === "simulation"
              ? "These are simulated ATLAS records. Cancel removes the stored booking. No external calendar is contacted."
              : `Bookings use ${data.calendar_provider}.`}
          </p>
          <ul className="mt-4 space-y-3">
            {data.bookings.map((booking) => (
              <li key={booking.id} className="flex flex-wrap items-center justify-between gap-3 text-sm">
                <div>
                  <p className="text-foreground">{booking.status}</p>
                  <p className="text-xs text-subtle">
                    {new Date(booking.starts_at).toLocaleString()} – {new Date(booking.ends_at).toLocaleString()}
                  </p>
                </div>
                {isAdmin && booking.status === "booked" ? (
                  <Button type="button" variant="outline" disabled={cancelPending} onClick={() => onCancel(booking.id)}>
                    Cancel booking
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
          {cancelError ? <div className="mt-3"><RequestError error={cancelError} /></div> : null}
        </section>
      ) : null}
    </div>
  );
}

function WorkflowBuilder() {
  const workspace = useWorkspace();
  const id = workspace.organizationId ?? "";
  const queryClient = useQueryClient();
  const definitions = useQuery({ queryKey: ["workflow-definitions", id], queryFn: () => listWorkflowDefinitions(id), enabled: Boolean(id) });
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState("lead_created");
  const [action, setAction] = useState("update_lead");
  const [message, setMessage] = useState("");
  const create = useMutation({ mutationFn: () => createWorkflowDefinition(id, { name, slug: name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "workflow", definition: { trigger, actions: [{ type: action }] } }), onSuccess: () => { setName(""); setMessage("Workflow saved as a draft."); void queryClient.invalidateQueries({ queryKey: ["workflow-definitions", id] }); }, onError: (e) => setMessage(e instanceof Error ? e.message : "Workflow could not be saved.") });
  return <section className="rounded-xl border border-border bg-card p-5" aria-label="Workflow builder" data-testid="workflow-builder"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-base font-semibold text-foreground">Workflow builder</h2><p className="mt-1 text-sm text-muted-foreground">Create a validated draft from a trigger and action. Activation remains administrator-controlled.</p></div><span className="text-xs text-muted-foreground">{definitions.data?.length ?? 0} saved</span></div><div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto_auto_auto]" ><input aria-label="Workflow name" className="h-10 rounded-md border border-input bg-background px-3 text-sm" placeholder="Follow up new leads" value={name} onChange={(e) => setName(e.target.value)} /><select aria-label="Workflow trigger" value={trigger} onChange={(e) => setTrigger(e.target.value)}><option value="lead_created">Lead created</option><option value="lead_status_changed">Lead status changed</option><option value="schedule">Scheduled</option></select><select aria-label="Workflow action" value={action} onChange={(e) => setAction(e.target.value)}><option value="update_lead">Update CRM lead</option><option value="create_task">Create task</option><option value="prepare_follow_up">Prepare follow-up for approval</option></select><Button size="sm" onClick={() => create.mutate()} disabled={!name.trim() || create.isPending}>Create draft</Button></div>{message ? <p className="mt-3 text-xs text-muted-foreground" role="status">{message}</p> : null}<div className="mt-4 space-y-2">{(definitions.data ?? []).map((item) => <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-muted p-3 text-sm"><span><strong>{item.name}</strong><span className="ml-2 text-muted-foreground">v{item.version} · {item.active ? "Active" : "Draft"}</span></span><div className="flex gap-2">{item.active ? <Button size="sm" variant="outline" onClick={() => void workflowAction(id, item.id, "pause").then(() => queryClient.invalidateQueries({ queryKey: ["workflow-definitions", id] }))}>Pause</Button> : <Button size="sm" onClick={() => void workflowAction(id, item.id, "activate").then(() => queryClient.invalidateQueries({ queryKey: ["workflow-definitions", id] }))}>Activate</Button>}<Button size="sm" variant="ghost" onClick={() => void workflowAction(id, item.id, "duplicate").then(() => queryClient.invalidateQueries({ queryKey: ["workflow-definitions", id] }))}>Duplicate</Button><Button size="sm" variant="ghost" onClick={() => { if (window.confirm("Delete this workflow?")) void deleteWorkflowDefinition(id, item.id).then(() => queryClient.invalidateQueries({ queryKey: ["workflow-definitions", id] })); }}>Delete</Button></div></div>)}</div></section>;
}

function WorkflowTaskList() {
  const { organizationId } = useWorkspace();
  const tasks = useQuery({ queryKey: ["workflow-tasks", organizationId], queryFn: () => listWorkflowTasks(organizationId ?? ""), enabled: Boolean(organizationId) });
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const create = useMutation({ mutationFn: () => createWorkflowTask(organizationId ?? "", { title }), onSuccess: () => { setTitle(""); void queryClient.invalidateQueries({ queryKey: ["workflow-tasks", organizationId] }); } });
  return <section className="rounded-xl border border-border bg-card p-5" aria-label="Workflow tasks"><div className="flex items-center justify-between"><h2 className="text-base font-semibold text-foreground">Tasks</h2><span className="text-xs text-muted-foreground">{tasks.data?.length ?? 0}</span></div><div className="mt-3 flex gap-2"><input aria-label="New task title" className="h-9 min-w-0 flex-1 rounded-md border border-input bg-background px-3 text-sm" placeholder="Add a follow-up task" value={title} onChange={(e) => setTitle(e.target.value)} /><Button size="sm" onClick={() => create.mutate()} disabled={!title.trim() || create.isPending}>Add task</Button></div>{tasks.isError ? <RequestError error={tasks.error} /> : null}{tasks.isPending ? <Skeleton className="mt-3 h-12 w-full" /> : null}{tasks.data?.length === 0 ? <p className="mt-3 text-sm text-muted-foreground">No tasks yet.</p> : <div className="mt-3 space-y-2">{tasks.data?.map((task) => <article key={task.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-muted p-3 text-sm"><div><p className="font-medium text-foreground">{task.title}</p><p className="text-xs text-muted-foreground">{task.source === "manual" ? "Manual task" : "Workflow task"}{task.priority ? ` · ${task.priority}` : ""}{task.lead_id ? ` · Lead ${task.lead_id.slice(0, 8)}` : ""}</p></div><select aria-label={`Task status for ${task.title}`} value={task.status} onChange={(e) => void updateWorkflowTask(organizationId ?? "", task.id, e.target.value).then(() => queryClient.invalidateQueries({ queryKey: ["workflow-tasks", organizationId] }))}><option value="open">To Do</option><option value="in_progress">In Progress</option><option value="completed">Completed</option></select></article>)}</div>}</section>;
}

function WorkflowTopology({ data }: { data: AutomationSnapshot }) {
  return (
    <section className="rounded-xl border border-border bg-card p-5 shadow-[0_18px_60px_rgba(0,0,0,0.18)]" aria-label="Workflow topology" data-testid="workflow-topology">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-foreground">Workflow topology</h2>
          <p className="mt-1 text-sm text-muted-foreground">These connected stages reflect the workflows currently exposed by ATLAS. Editing definitions is not enabled in this environment.</p>
        </div>
        <span className="rounded-full border border-border bg-muted px-2.5 py-1 text-xs text-subtle">Read only</span>
      </div>
      <div className="relative mt-5 grid gap-3 md:grid-cols-3 md:items-center md:gap-8">
        <svg className="pointer-events-none absolute inset-x-[16%] top-1/2 hidden h-8 w-[68%] -translate-y-1/2 md:block" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 5 H100" fill="none" stroke="currentColor" strokeDasharray="2 2" strokeWidth="0.7" className="text-primary/60" />
          <path d="M33 2 L37 5 L33 8 M63 2 L67 5 L63 8" fill="none" stroke="currentColor" strokeWidth="0.7" className="text-primary" />
        </svg>
        {[
          ["trigger", "CRM event", "Lead created"],
          ["process", "AI processing", "Lead intake"],
          ["outcome", "Human review", "Approval or execution"],
        ].map(([key, eyebrow, label]) => (
          <div key={key} className="contents">
            <div className="rounded-lg border border-border bg-muted p-4" data-testid={`workflow-node-${key}`}>
              <p className="text-[11px] uppercase tracking-[0.14em] text-primary">{eyebrow}</p>
              <p className="mt-2 text-sm font-medium text-foreground">{label}</p>
              <p className="mt-1 text-xs text-muted-foreground">{nodeDetail(data, key)}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function nodeDetail(data: AutomationSnapshot, key: string): string {
  if (key === "trigger") return `${data.runs.length} recorded run${data.runs.length === 1 ? "" : "s"}`;
  if (key === "process") return `${data.automations.length} configured process${data.automations.length === 1 ? "" : "es"}`;
  const approvals = data.automations.reduce((total, item) => total + item.awaiting_review, 0);
  return `${approvals} approval${approvals === 1 ? "" : "s"} requiring review`;
}

function EmailActivitySection({ emails }: { emails: AutomationSnapshot["emails"] }) {
  if (emails.length === 0) {
    return (
      <section className="rounded-[10px] bg-muted px-5 py-6">
        <h2 className="text-[22px] text-foreground">Email activity</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Approved customer responses will appear here. ATLAS sends only through the local sandbox mailbox.
        </p>
      </section>
    );
  }
  return (
    <section className="rounded-[10px] bg-muted px-5 py-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-[22px] text-foreground">Email activity</h2>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            A durable history of approved sandbox messages. SMTP acceptance is not inbox delivery.
          </p>
        </div>
        <span className="text-xs uppercase tracking-[0.12em] text-subtle">Mailpit sandbox</span>
      </div>
      <ul className="mt-5 divide-y divide-border/50">
        {emails.map((email) => (
          <li key={email.intent_id ?? email.id} className="py-4 first:pt-0 last:pb-0">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-foreground">{email.subject ?? "Customer response"}</p>
                <p className="mt-1 truncate text-xs text-muted-foreground">To {email.recipient ?? "recipient unavailable"}</p>
              </div>
              <span className={`text-xs uppercase tracking-[0.1em] ${emailStateClass(email.state)}`}>
                {emailStateLabel(email.state)}
              </span>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-subtle sm:grid-cols-3">
              <span>{email.attempt_count ?? 0} attempt{email.attempt_count === 1 ? "" : "s"}</span>
              <span>Queued {email.queued_at ? new Date(email.queued_at).toLocaleString() : "—"}</span>
              <span>{email.provider_message_id ? "Accepted by SMTP server" : "No provider receipt yet"}</span>
            </div>
            {email.error ? <p className="mt-2 text-xs leading-5 text-destructive">{email.error}</p> : null}
            {email.attempts && email.attempts.length > 0 ? (
              <details className="mt-3 text-xs text-subtle">
                <summary className="cursor-pointer text-primary">View attempt history</summary>
                <ul className="mt-2 space-y-1 pl-4">
                  {email.attempts.map((attempt) => <li key={`${email.id}-${attempt.started_at}`}>{attempt.outcome}{attempt.error ? `: ${attempt.error}` : ""}</li>)}
                </ul>
              </details>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-3 text-xs">
              {email.approval_id ? <Link className="text-primary underline" href={`/approvals?approval=${email.approval_id}`}>Open approval</Link> : null}
              {email.lead_id ? <Link className="text-primary underline" href={`/crm?tab=leads&id=${email.lead_id}`}>Open lead</Link> : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function emailStateLabel(state?: string | null): string {
  return ({
    awaiting_approval: "Awaiting approval",
    approved: "Approved",
    queued: "Queued",
    sending: "Sending",
    accepted: "Accepted by SMTP",
    failed: "Failed",
    needs_attention: "Needs attention",
  } as Record<string, string>)[state ?? ""] ?? "Recorded";
}

function emailStateClass(state?: string | null): string {
  if (state === "accepted") return "text-success";
  if (state === "failed" || state === "needs_attention") return "text-destructive";
  return "text-warning";
}

function HistoryRow({ run, onSelect }: { run: WorkflowRun; onSelect: (run: WorkflowRun) => void }) {
  const record = run.company_name ?? run.lead_title ?? "No CRM record";
  return (
    <li className="border-b border-border/50 px-1 py-4 last:border-0 md:px-4">
      <button type="button" className="w-full text-left" onClick={() => onSelect(run)} aria-label={`Inspect ${record} ${statusLabel(run.status)}`}>
      <div className="grid gap-2 md:grid-cols-[minmax(8rem,1fr)_minmax(10rem,1.3fr)_minmax(8rem,1fr)_6rem] md:items-center md:gap-3">
        <p className="text-[13px] text-foreground">{processLabel(run.kind)}</p>
        <p className="text-[13px] text-muted-foreground">
          {run.lead_id ? (
            <Link href={`/crm?tab=leads&id=${run.lead_id}`} className="hover:text-foreground">
              {record}
            </Link>
          ) : (
            record
          )}
        </p>
        <p className={`text-xs ${statusClass(run.status)}`}>{statusLabel(run.status)}</p>
        <p className="text-[11px] text-subtle">{activityTime(run.created_at)}</p>
      </div>
      </button>
      {run.last_error ? <p className="mt-2 text-xs leading-5 text-destructive">{run.last_error}</p> : null}
      {run.attempts.length > 0 ? (
        <ul className="mt-2 space-y-1 text-xs text-subtle">
          {run.attempts.map((attempt) => (
            <li key={`${run.id}-${attempt.started_at}`}>
              {attempt.outcome}
              {attempt.error ? `: ${attempt.error}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function ExecutionDetail({ run, onClose }: { run: WorkflowRun; onClose: () => void }) {
  const record = run.company_name ?? run.lead_title ?? "No CRM record";
  return <section className="rounded-[10px] border border-primary/30 bg-background px-5 py-5" aria-label="Execution details"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs uppercase tracking-[0.12em] text-subtle">Execution detail</p><h2 className="mt-1 text-xl text-foreground">{processLabel(run.kind)} · {record}</h2><p className={`mt-2 text-sm ${statusClass(run.status)}`}>{statusLabel(run.status)}</p></div><button type="button" className="text-xs text-primary" onClick={onClose}>Close</button></div><dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3"><div><dt className="text-xs text-subtle">Created</dt><dd>{activityTime(run.created_at)}</dd></div><div><dt className="text-xs text-subtle">Attempts</dt><dd>{run.attempt_count}</dd></div><div><dt className="text-xs text-subtle">Next action</dt><dd>{run.status === "needs_attention" || run.status === "failed" ? "Review before retrying" : run.status === "awaiting_approval" ? "Open approval" : "No action required"}</dd></div></dl>{run.lead_id ? <Link className="mt-4 inline-block text-sm text-primary underline" href={`/crm?tab=leads&id=${run.lead_id}`}>Open related lead →</Link> : null}{run.last_error ? <p className="mt-4 rounded-md bg-destructive/10 p-3 text-sm text-destructive">{run.last_error}</p> : null}{run.attempts.length > 0 ? <div className="mt-4"><h3 className="text-sm font-medium">Execution steps</h3><ul className="mt-2 space-y-2 text-sm text-muted-foreground">{run.attempts.map((attempt) => <li key={`${run.id}-detail-${attempt.started_at}`}>{attempt.outcome}{attempt.error ? ` · ${attempt.error}` : ""}</li>)}</ul></div> : null}</section>;
}

function configurationCopy(data: AutomationSnapshot): string {
  const email =
    data.email_mode === "live"
      ? "Live email is enabled."
      : "Sandbox email reaches the local mailbox, not a customer inbox.";
  const calendar =
    data.calendar_provider === "simulation"
      ? "Calendar bookings are simulated in ATLAS."
      : `Calendar provider: ${data.calendar_provider}.`;
  const n8n = data.n8n_configured
    ? "A lead webhook URL is configured."
    : "The lead webhook URL is empty, so new runs are stored as not configured.";
  const key = data.webhook_configured
    ? "A webhook key is installed for signed callbacks."
    : "No webhook key is installed, so ATLAS cannot sign an outbound call.";
  return `${email} ${calendar} ${n8n} ${key}`;
}

function outcomeCopy(automation: AutomationSnapshot["automations"][number]): string {
  if (automation.kind === "follow_up" && automation.awaiting_review > 0) {
    return `${automation.awaiting_review} awaiting review`;
  }
  if (automation.needs_attention > 0 && automation.completed === 0) {
    return `${automation.needs_attention} need attention`;
  }
  if (automation.failed > 0 && automation.completed === 0) {
    return `${automation.failed} failed`;
  }
  return `${automation.completed} completed`;
}

function triggerLabel(trigger: string): string {
  if (trigger === "lead_created") {
    return "CRM lead created";
  }
  if (trigger === "schedule") {
    return "n8n follow-up event";
  }
  return trigger.replaceAll("_", " ");
}

function processLabel(kind: string): string {
  if (kind === "lead_processing") {
    return "Lead intake";
  }
  if (kind === "follow_up") {
    return "Follow-up";
  }
  return kind.replaceAll("_", " ");
}

function statusLabel(status: string): string {
  return status.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusClass(status: string): string {
  if (status === "completed" || status === "accepted") {
    return "text-success";
  }
  if (status === "failed" || status === "needs_attention") {
    return "text-destructive";
  }
  if (status === "pending" || status === "dispatching") {
    return "text-warning";
  }
  return "text-subtle";
}

function activityTime(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(start);
  yesterday.setDate(yesterday.getDate() - 1);
  if (date >= start) {
    const time = date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
    return `Today ${time}`;
  }
  if (date >= yesterday) {
    return "Yesterday";
  }
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
