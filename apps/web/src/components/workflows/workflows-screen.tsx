"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cancelBooking, getAutomations, type AutomationSnapshot, type WorkflowRun } from "@/lib/automations";
import { useWorkspace } from "@/lib/use-workspace";

export function WorkflowsScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<string | null>(null);
  const automations = useQuery({
    queryKey: ["automations", organizationId],
    queryFn: () => getAutomations(organizationId ?? ""),
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
      kind={kind}
      onKind={setKind}
      isAdmin={workspace.role === "admin"}
      cancelPending={cancel.isPending}
      cancelError={cancel.error}
      onCancel={(bookingId) => cancel.mutate(bookingId)}
    />
  );
}

function WorkflowsBody({
  data,
  kind,
  onKind,
  isAdmin,
  cancelPending,
  cancelError,
  onCancel,
}: {
  data: AutomationSnapshot;
  kind: string | null;
  onKind: (kind: string | null) => void;
  isAdmin: boolean;
  cancelPending: boolean;
  cancelError: unknown;
  onCancel: (bookingId: string) => void;
}) {
  const visible = kind ? data.runs.filter((run) => run.kind === kind) : data.runs;
  const focus = data.automations.find((item) => item.kind === kind);
  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <header>
        <h1 className="text-[31px] leading-none text-foreground">Automations</h1>
        <p className="mt-3 max-w-4xl text-sm text-muted-foreground">
          Installed business processes, observable outcomes and safe recovery actions.
        </p>
        <p className="mt-2 max-w-4xl text-xs leading-5 text-subtle">{configurationCopy(data)}</p>
      </header>
      <section className="grid gap-4 lg:grid-cols-2">
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
      </section>
      <section id="execution-history" className="rounded-[10px] bg-muted px-5 py-6">
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
        </div>
        {visible.length === 0 ? (
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
              {visible.map((run) => (
                <HistoryRow key={run.id} run={run} />
              ))}
            </ul>
          </div>
        )}
      </section>
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

function HistoryRow({ run }: { run: WorkflowRun }) {
  const record = run.company_name ?? run.lead_title ?? "No CRM record";
  return (
    <li className="border-b border-border/50 px-1 py-4 last:border-0 md:px-4">
      <div className="grid gap-2 md:grid-cols-[minmax(8rem,1fr)_minmax(10rem,1.3fr)_minmax(8rem,1fr)_6rem] md:items-center md:gap-3">
        <p className="text-[13px] text-foreground">{processLabel(run.kind)}</p>
        <p className="text-[13px] text-muted-foreground">
          {run.lead_id ? (
            <Link href="/crm?tab=leads" className="hover:text-foreground">
              {record}
            </Link>
          ) : (
            record
          )}
        </p>
        <p className={`text-xs ${statusClass(run.status)}`}>{statusLabel(run.status)}</p>
        <p className="text-[11px] text-subtle">{activityTime(run.created_at)}</p>
      </div>
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
