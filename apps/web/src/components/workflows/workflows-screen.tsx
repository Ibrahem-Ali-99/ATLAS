"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { WorkflowStudio } from "./workflow-studio";
import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { calendarExportUrl, cancelBooking, getAutomations, type AutomationSnapshot, type WorkflowRun } from "@/lib/automations";
import { useWorkspace } from "@/lib/use-workspace";
import { createWorkflowTask, listWorkflowTasks, updateWorkflowTask } from "@/lib/workflow-definitions";

export function WorkflowsScreen({ requestedWorkflow, requestedRun, showArchived }: {
  requestedWorkflow?: string; requestedRun?: string; showArchived?: boolean;
}) {
  const { organizationId, role } = useWorkspace();
  return (
    <div className="w-full min-w-0 space-y-5">
      {organizationId && role === "admin" ? <WorkflowStudio key={organizationId} organizationId={organizationId} requestedWorkflow={requestedWorkflow} requestedRun={requestedRun} showArchived={showArchived} /> : (
        <header>
          <h1 className="text-2xl font-semibold tracking-tight">Workflows</h1>
          <p className="mt-2 text-sm text-muted-foreground">Track workflow tasks and activity. A workspace administrator manages automation.</p>
        </header>
      )}
      <WorkflowTaskList />
      <section className="rounded-xl border border-border bg-card p-5" aria-labelledby="automation-activity-title">
        <h2 id="automation-activity-title" className="text-base font-semibold">Activity</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">Recorded runs, messages, and bookings for this workspace.</p>
        <BuiltInWorkflows />
      </section>
    </div>
  );
}
function BuiltInWorkflows() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const scope = "operational";
  const automations = useQuery({
    queryKey: ["automations", organizationId, scope],
    queryFn: () => getAutomations(organizationId ?? "", scope),
    enabled: Boolean(organizationId),
    staleTime: 0,
    refetchInterval: (query) => query.state.data?.emails.some(
      ({ state }) => state === "queued" || state === "sending",
    ) ? 2_000 : false,
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
      key={organizationId}
      data={automations.data}
      organizationId={organizationId}
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
  organizationId,
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
  organizationId: string;
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
    <div className="mt-5 flex w-full min-w-0 flex-col gap-5">
      <p className="text-sm text-muted-foreground">{configurationCopy(data)}</p>
      <nav className="flex flex-wrap gap-2 border-b border-border pb-3" aria-label="Automation workspace views">
        {([ ["overview", "Overview"], ["approvals", "Approvals"], ["history", "Execution history"], ["email", "Email activity"] ] as const).map(([id, label]) => (
          <button key={id} type="button" className={`rounded-md px-3 py-2 text-sm ${view === id ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground"}`} aria-pressed={view === id} onClick={() => setView(id)}>{label}</button>
        ))}
      </nav>
      {view === "overview" ? <section className="grid gap-4 lg:grid-cols-2">
        {data.automations.map((automation) => (
          <article key={automation.kind} className="flex min-h-44 flex-col rounded-xl border border-border bg-background px-5 py-5">
            <div className="flex items-start justify-between gap-4">
              <h2 className="text-base font-semibold text-foreground">{automation.name}</h2>
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
      {view === "approvals" ? <section className="rounded-xl border border-border bg-background px-5 py-5"><h2 className="text-base font-semibold text-foreground">Approvals</h2><p className="mt-2 max-w-2xl text-sm text-muted-foreground">Review proposed customer changes before they are applied.</p><Link className="mt-4 inline-block text-sm font-medium text-primary" href="/approvals">Open approvals</Link></section> : null}
      {view === "history" || view === "overview" ? <section id="execution-history" className="rounded-xl border border-border bg-background px-5 py-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-foreground">Execution history</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              These are stored outcomes. This page does not start or retry a run.
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
            Download a workspace reservation to import it into your calendar. Cancelling a Google Calendar booking also removes its event.
          </p>
          <ul className="mt-4 space-y-3">
            {data.bookings.map((booking) => (
              <li key={booking.id} className="flex flex-wrap items-center justify-between gap-3 text-sm">
                <div>
                  <p className="capitalize text-foreground">{booking.status} · {booking.provider === "google" ? "Google Calendar" : "ATLAS workspace"}</p>
                  <p className="text-xs text-subtle">
                    {new Date(booking.starts_at).toLocaleString()} – {new Date(booking.ends_at).toLocaleString()}
                  </p>
                </div>
                {booking.status === "booked" ? <div className="flex flex-wrap gap-2">
                  {booking.provider !== "google" ? <Button asChild variant="outline">
                    <a href={calendarExportUrl(organizationId, booking.id)}>Download calendar event</a>
                  </Button> : null}
                  {isAdmin ? (
                  <Button type="button" variant="outline" disabled={cancelPending} onClick={() => onCancel(booking.id)}>
                    Cancel booking
                  </Button>
                  ) : null}
                </div> : null}
              </li>
            ))}
          </ul>
          {cancelError ? <div className="mt-3"><RequestError error={cancelError} /></div> : null}
        </section>
      ) : null}
    </div>
  );
}

const selectClass = "h-9 w-full rounded-md border border-input bg-background px-2 text-sm";

function WorkflowTaskList() {
  const { organizationId } = useWorkspace();
  const queryClient = useQueryClient();
  const queryKey = ["workflow-tasks", organizationId] as const;
  const tasks = useQuery({
    queryKey,
    queryFn: () => listWorkflowTasks(organizationId ?? ""),
    enabled: Boolean(organizationId),
    refetchInterval: 10_000,
  });
  const [title, setTitle] = useState("");
  const create = useMutation({
    mutationFn: () => createWorkflowTask(organizationId ?? "", { title: title.trim() }),
    onSuccess: () => { setTitle(""); void queryClient.invalidateQueries({ queryKey }); },
  });
  const change = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => updateWorkflowTask(organizationId ?? "", id, status),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey }); },
  });

  return (
    <section className="rounded-xl border border-border bg-card p-5" aria-label="Workflow tasks">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold">Tasks</h2>
        {tasks.data ? <Badge variant="secondary">{tasks.data.length}</Badge> : null}
      </div>
      <form className="mt-3 flex items-center gap-2" onSubmit={(event) => { event.preventDefault(); if (title.trim()) create.mutate(); }}>
        <Input aria-label="New task title" className="min-w-0 flex-1" placeholder="Add a follow-up task" value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} required />
        <Button size="sm" type="submit" disabled={!title.trim() || create.isPending}>Add task</Button>
      </form>
      {tasks.error || create.error ? <div className="mt-3"><RequestError error={tasks.error ?? create.error} /></div> : null}
      {tasks.isPending ? <Skeleton className="mt-3 h-12 w-full" /> : null}
      {tasks.data?.length === 0 ? <p className="mt-3 text-sm text-muted-foreground">No tasks yet.</p> : null}
      {tasks.data?.length ? (
        <ul className="mt-3 space-y-2">
          {tasks.data.map((task) => (
            <li key={task.id} className="rounded-lg border border-border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="break-words text-sm font-medium">{task.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {task.source === "manual" ? "Manual task" : "Workflow task"}{task.priority ? ` · ${task.priority}` : ""}
                    {task.lead_id ? <> · <Link className="text-primary underline" href={`/crm?tab=leads&id=${task.lead_id}`}>Open lead</Link></> : null}
                  </p>
                </div>
                <select aria-label={`Task status for ${task.title}`} className={selectClass} value={task.status} disabled={change.isPending} onChange={(event) => change.mutate({ id: task.id, status: event.target.value })}>
                  <option value="open">To do</option><option value="in_progress">In progress</option><option value="completed">Completed</option>
                </select>
              </div>
              {change.error && change.variables?.id === task.id ? <div className="mt-2"><RequestError error={change.error} /></div> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}


function EmailActivitySection({ emails }: { emails: AutomationSnapshot["emails"] }) {
  if (emails.length === 0) {
    return (
      <section className="rounded-xl border border-border bg-background px-5 py-5" aria-label="Email activity">
        <h2 className="text-base font-semibold text-foreground">Email activity</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Approved customer responses will appear here with their delivery status.
        </p>
      </section>
    );
  }
  return (
    <section className="rounded-xl border border-border bg-background px-5 py-5" aria-label="Email activity">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-foreground">Email activity</h2>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            Review approved messages and their recorded delivery attempts.
          </p>
        </div>
        {emails.every((email) => email.mode === "sandbox") ? (
          <span className="text-xs uppercase tracking-[0.12em] text-subtle">Mailpit sandbox</span>
        ) : null}
      </div>
      <ul className="mt-5 divide-y divide-border/50">
        {emails.map((email) => (
          <li key={email.intent_id ?? email.id} data-approval-id={email.approval_id ?? undefined} className="py-4 first:pt-0 last:pb-0">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-foreground">{email.subject ?? "Customer response"}</p>
                <p className="mt-1 truncate text-xs text-muted-foreground">To {email.recipient ?? "recipient unavailable"}</p>
              </div>
              <span className={`text-xs uppercase tracking-[0.1em] ${emailStateClass(email.state)}`}>
                {emailStateLabel(email.state, email.mode)}
              </span>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-subtle sm:grid-cols-3">
              <span>{email.attempt_count ?? 0} attempt{email.attempt_count === 1 ? "" : "s"}</span>
              <span>Queued {email.queued_at ? new Date(email.queued_at).toLocaleString() : "—"}</span>
              <span>{email.provider_message_id ? (email.mode === "whatsapp" ? "Accepted by WhatsApp" : "Accepted by SMTP server") : "No provider receipt yet"}</span>
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

function emailStateLabel(state?: string | null, mode?: string): string {
  return ({
    awaiting_approval: "Awaiting approval",
    approved: "Approved",
    queued: "Queued",
    sending: "Sending",
    accepted: mode === "whatsapp" ? "Accepted by WhatsApp" : "Accepted by SMTP",
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
      ? "Email can leave this workspace after approval."
      : "Email stays in the sandbox mailbox for this workspace.";
  const calendar =
    data.calendar_provider === "simulation"
      ? "Appointments are stored here and are not sent to Google Calendar."
      : "Approved appointments can be added to Google Calendar.";
  const automation = data.n8n_configured
    ? "An external workflow is connected."
    : "No external workflow is connected.";
  return `${email} ${calendar} ${automation}`;
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
