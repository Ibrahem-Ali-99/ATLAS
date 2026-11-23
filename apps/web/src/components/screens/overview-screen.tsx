"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { DataScopeControl } from "@/components/data-scope";
import { RequestError } from "@/components/request-error";
import { Skeleton } from "@/components/ui/skeleton";
import type { Approval } from "@/lib/agent";
import { listAgentRuns, listApprovals } from "@/lib/agent-api";
import { getHealth, getReady } from "@/lib/api";
import { getAutomations, type WorkflowRun } from "@/lib/automations";
import { getAnalytics, type AnalyticsSnapshot, type StatusCount } from "@/lib/intelligence";
import type { DataScope } from "@/lib/provenance";
import { useWorkspace } from "@/lib/use-workspace";

const PIPELINE = [
  { status: "new", label: "New", bar: "bg-primary" },
  { status: "qualified", label: "Qualified", bar: "bg-success" },
  { status: "contacted", label: "Contacted", bar: "bg-primary" },
] as const;

export function OverviewScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const [scope, setScope] = useState<DataScope>("operational");
  const analytics = useQuery({
    queryKey: ["analytics", organizationId, scope],
    queryFn: () => getAnalytics(organizationId ?? "", scope),
    enabled: Boolean(organizationId),
  });
  const approvals = useQuery({
    queryKey: ["inbox-approvals", organizationId],
    queryFn: () => listApprovals(organizationId ?? "", { status: "pending" }),
    enabled: Boolean(organizationId),
  });
  const failures = useQuery({
    queryKey: ["inbox-runs", organizationId, "failed", scope],
    queryFn: () => listAgentRuns(organizationId ?? "", { status: "failed", scope }),
    enabled: Boolean(organizationId),
  });
  const automations = useQuery({
    queryKey: ["automations", organizationId, scope],
    queryFn: () => getAutomations(organizationId ?? "", scope),
    enabled: Boolean(organizationId),
  });
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, retry: false });
  const ready = useQuery({ queryKey: ["ready"], queryFn: getReady, retry: false });

  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <header>
        <h1 className="text-[31px] leading-none text-foreground">Operations overview</h1>
        <p className="mt-3 max-w-3xl text-[13px] text-muted-foreground">
          Decisions, customer activity and execution health
        </p>
        <DataScopeControl value={scope} onChange={setScope} />
        <Link href="/setup" className="mt-3 inline-block text-xs text-primary">Open first-run setup checklist →</Link>
        {analytics.data ? (
          <p className="mt-2 max-w-3xl text-xs leading-5 text-subtle">{analytics.data.provenance_notice}</p>
        ) : null}
      </header>
      {analytics.isPending ? <Skeleton className="h-36 w-full" /> : null}
      {analytics.isError ? <RequestError error={analytics.error} /> : null}
      {analytics.data ? (
        <>
          <MetricRow data={analytics.data} />
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(16rem,0.7fr)]">
            <PriorityInbox
              approvals={approvals.data?.items ?? []}
              approvalsPending={approvals.isPending}
              approvalsError={approvals.error}
              failures={failures.data?.items ?? []}
              failuresPending={failures.isPending}
              failuresError={failures.error}
            />
            <Pipeline data={analytics.data} />
          </div>
          <RecentActivity
            runs={automations.data?.runs ?? []}
            pendingApprovals={analytics.data.approvals.pending}
            pending={automations.isPending}
            error={automations.error}
          />
        </>
      ) : null}
      <p className="text-xs text-subtle">
        API {health.isError ? "unreachable" : health.data?.status ?? "checking"}. Database{" "}
        {ready.isError ? "not ready" : ready.data?.database ?? "checking"}.
      </p>
    </div>
  );
}

function MetricRow({ data }: { data: AnalyticsSnapshot }) {
  const active =
    statusCount(data.lead_status, "new") +
    statusCount(data.lead_status, "contacted") +
    statusCount(data.lead_status, "qualified");
  const recorded = data.automation.succeeded + data.automation.failed;
  const rate =
    data.automation.success_rate === null ? "—" : `${Math.round(data.automation.success_rate * 100)}%`;
  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Metric
        href="/approvals"
        label="Pending approvals"
        value={pad(data.approvals.pending)}
        detail="Needs your decision"
        detailClass="text-warning"
      />
      <Metric
        href="/crm?tab=leads"
        label="Active leads"
        value={pad(active)}
        detail="Across the pipeline"
        detailClass="text-primary"
      />
      <Metric
        href="/monitoring"
        label="Agent failures"
        value={pad(data.failed_runs)}
        detail="Historical / review"
        detailClass="text-destructive"
      />
      <Metric
        href="/workflows"
        label="Automation success"
        value={rate}
        detail={recorded === 0 ? "No completed or failed runs" : `${data.automation.succeeded} of ${recorded} recorded`}
        detailClass="text-success"
      />
    </section>
  );
}

function Metric({
  href,
  label,
  value,
  detail,
  detailClass,
}: {
  href: string;
  label: string;
  value: string;
  detail: string;
  detailClass: string;
}) {
  return (
    <Link href={href} className="rounded-[10px] bg-muted px-5 py-6 transition-colors hover:bg-accent">
      <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{label}</p>
      <p className="mt-4 text-[34px] leading-none text-foreground tabular-nums">{value}</p>
      <p className={`mt-5 text-[11px] ${detailClass}`}>{detail}</p>
    </Link>
  );
}

function PriorityInbox({
  approvals,
  approvalsPending,
  approvalsError,
  failures,
  failuresPending,
  failuresError,
}: {
  approvals: Approval[];
  approvalsPending: boolean;
  approvalsError: unknown;
  failures: { id: string; inquiry_subject: string; error_code: string | null; error_message: string | null }[];
  failuresPending: boolean;
  failuresError: unknown;
}) {
  const items = inboxItems(approvals, failures);
  return (
    <section className="rounded-[10px] bg-muted px-6 py-6">
      <h2 className="text-xl text-foreground">Priority inbox</h2>
      <p className="mt-2 text-xs text-muted-foreground">Decisions that need a human</p>
      {approvalsPending || failuresPending ? <Skeleton className="mt-6 h-16 w-full" /> : null}
      {approvalsError ? <div className="mt-4"><RequestError error={approvalsError} /></div> : null}
      {failuresError ? <div className="mt-4"><RequestError error={failuresError} /></div> : null}
      {!approvalsPending && !failuresPending && items.length === 0 ? (
        <p className="mt-6 text-sm text-muted-foreground">Nothing is waiting for a decision.</p>
      ) : null}
      <ul className="mt-4 divide-y divide-border/60">
        {items.map((item) => (
          <li key={item.id} className="grid gap-2 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
            <div className="min-w-0">
              <p className="truncate text-[15px] text-foreground">{item.title}</p>
              <p className="mt-1 truncate text-[11px] text-muted-foreground">{item.detail}</p>
            </div>
            <Link href={item.href} className="text-xs text-primary">
              View →
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Pipeline({ data }: { data: AnalyticsSnapshot }) {
  const counts = PIPELINE.map((stage) => statusCount(data.lead_status, stage.status));
  const max = Math.max(1, ...counts);
  return (
    <section className="rounded-[10px] bg-muted px-6 py-6">
      <h2 className="text-xl text-foreground">Lead pipeline</h2>
      <p className="mt-2 text-xs text-muted-foreground">Current CRM records</p>
      <ul className="mt-6 space-y-5">
        {PIPELINE.map((stage, index) => (
          <li key={stage.status}>
            <Link href={`/crm?tab=leads`} className="block">
              <span className="flex items-center justify-between gap-3 text-[13px] text-foreground">
                <span>{stage.label}</span>
                <span className="tabular-nums">{counts[index]}</span>
              </span>
              <span className="mt-2 block h-2 rounded-full bg-secondary">
                <span
                  className={`block h-2 rounded-full ${stage.bar}`}
                  style={{ width: counts[index] === 0 ? "0%" : `${(counts[index] / max) * 100}%` }}
                />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function RecentActivity({
  runs,
  pendingApprovals,
  pending,
  error,
}: {
  runs: WorkflowRun[];
  pendingApprovals: number;
  pending: boolean;
  error: unknown;
}) {
  const lines = activityLines(runs, pendingApprovals);
  return (
    <section className="rounded-[10px] bg-muted px-6 py-5">
      <h2 className="text-[19px] text-foreground">Recent activity</h2>
      {pending ? <Skeleton className="mt-4 h-6 w-64" /> : null}
      {error ? <div className="mt-4"><RequestError error={error} /></div> : null}
      {!pending && lines.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">No automation activity is stored yet.</p>
      ) : null}
      {lines.length > 0 ? (
        <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          {lines.map((line) => (
            <Link key={line.text} href={line.href} className={`text-[13px] ${line.className}`}>
              {line.text}
            </Link>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function inboxItems(
  approvals: Approval[],
  failures: { id: string; inquiry_subject: string; error_code: string | null; error_message: string | null }[],
): { id: string; title: string; detail: string; href: string }[] {
  const decisions = approvals.slice(0, 3).map((approval) => ({
    id: approval.id,
    title: approvalTitle(approval),
    detail: "Awaiting approval",
    href: `/approvals?approval=${approval.id}`,
  }));
  const remaining = 4 - decisions.length;
  const problems = failures.slice(0, remaining).map((run) => ({
    id: run.id,
    title: run.inquiry_subject || "Investigate agent failure",
    detail: run.error_code ?? run.error_message ?? "Failed run",
    href: `/monitoring?run=${run.id}`,
  }));
  return [...decisions, ...problems];
}

function approvalTitle(approval: Approval): string {
  const title = payloadText(approval.payload, "title");
  const subject = payloadText(approval.payload, "subject");
  if (approval.action_type === "create_lead") {
    return title ? `Approve ${title}` : "Approve lead creation";
  }
  if (approval.action_type === "update_lead") {
    return "Review lead update";
  }
  if (approval.action_type === "prepare_customer_response") {
    return subject ? `Review ${subject}` : "Review follow-up proposal";
  }
  return "Review appointment request";
}

function payloadText(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function activityLines(runs: WorkflowRun[], pendingApprovals: number): { text: string; href: string; className: string }[] {
  const lines: { text: string; href: string; className: string }[] = [];
  const completed = runs.find((run) => run.status === "completed");
  const attention = runs.find((run) => run.status === "needs_attention" || run.status === "failed");
  if (completed) {
    const record = completed.company_name ?? completed.lead_title;
    const outcome =
      completed.kind === "lead_processing" && !record ? "Signed callback recorded" : record ?? completed.status;
    lines.push({
      text: `${processName(completed.kind)} completed · ${outcome}`,
      href: "/workflows",
      className: "text-success",
    });
  }
  if (attention) {
    lines.push({
      text: `${processName(attention.kind)} · ${attention.last_error ?? statusLabel(attention.status)}`,
      href: "/workflows",
      className: "text-destructive",
    });
  } else if (pendingApprovals > 0) {
    lines.push({
      text: pendingApprovals === 1 ? "1 approval is waiting" : `${pendingApprovals} approvals are waiting`,
      href: "/approvals",
      className: "text-warning",
    });
  }
  return lines.slice(0, 2);
}

function processName(kind: string): string {
  if (kind === "lead_processing") {
    return "Lead processing";
  }
  if (kind === "follow_up") {
    return "Follow-up";
  }
  return kind.replaceAll("_", " ");
}

function statusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

function statusCount(items: StatusCount[], status: string): number {
  return items.find((item) => item.status === status)?.count ?? 0;
}

function pad(value: number): string {
  if (value >= 100) {
    return String(value);
  }
  return String(value).padStart(2, "0");
}
