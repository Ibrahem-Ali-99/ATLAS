"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getAgentRun, listAgentRuns, resumeAgentRun, startAgentRun } from "@/lib/agent-api";
import type { AgentRunDetail, RunStatus } from "@/lib/agent";
import { listInquiries } from "@/lib/records-api";
import { useWorkspace } from "@/lib/use-workspace";

const selectClass =
  "flex h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground";

export function AgentRunsScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const [status, setStatus] = useState<RunStatus | "">("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  if (!organizationId) {
    return <Skeleton className="h-40 w-full" />;
  }
  return (
    <AgentRunsBody
      organizationId={organizationId}
      status={status}
      onStatus={setStatus}
      selectedId={selectedId}
      onSelect={setSelectedId}
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
  const runs = useQuery({
    queryKey: ["agent-runs", organizationId, status],
    queryFn: () => listAgentRuns(organizationId, { status }),
  });
  const detail = useQuery({
    queryKey: ["agent-run", organizationId, selectedId],
    queryFn: () => getAgentRun(organizationId, selectedId ?? ""),
    enabled: selectedId !== null,
  });
  const resume = useMutation({
    mutationFn: (runId: string) => resumeAgentRun(organizationId, runId),
    onSuccess: async (result) => {
      onSelect(result.run.id);
      await queryClient.invalidateQueries({ queryKey: ["agent-runs", organizationId] });
      await queryClient.invalidateQueries({ queryKey: ["agent-run", organizationId, result.run.id] });
    },
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(22rem,0.9fr)]">
      <section className="rounded-xl border border-border bg-card">
        <div className="flex flex-col gap-3 p-4 sm:flex-row">
          <select
            className={selectClass}
            aria-label="Filter runs by status"
            value={status}
            onChange={(event) => onStatus(event.target.value as RunStatus | "")}
          >
            <option value="">All statuses</option>
            <option value="running">Running</option>
            <option value="awaiting_approval">Awaiting approval</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
          <Button type="button" onClick={() => onOpen(true)}>
            Start from inquiry
          </Button>
        </div>
        {runs.isPending ? <div className="px-4 pb-4"><Skeleton className="h-8 w-full" /></div> : null}
        {runs.isError ? <div className="px-4 pb-4"><RequestError error={runs.error} /></div> : null}
        {runs.data && runs.data.items.length === 0 ? (
          <p className="px-4 pb-6 text-sm text-muted-foreground">No agent runs match this filter.</p>
        ) : null}
        {runs.data && runs.data.items.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Inquiry</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.data.items.map((run) => (
                <TableRow key={run.id} className={run.id === selectedId ? "bg-accent/40" : undefined}>
                  <TableCell>
                    <button type="button" className="text-left font-medium" onClick={() => onSelect(run.id)}>
                      {run.inquiry_subject}
                    </button>
                  </TableCell>
                  <TableCell><Badge>{run.status.replaceAll("_", " ")}</Badge></TableCell>
                  <TableCell>{new Date(run.started_at).toLocaleString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </section>
      <section className="rounded-xl border border-border bg-card p-4">
        {detail.isPending && selectedId ? <Skeleton className="h-32 w-full" /> : null}
        {detail.isError ? <RequestError error={detail.error} /> : null}
        {!selectedId ? <p className="text-sm text-muted-foreground">Select a run to inspect its steps.</p> : null}
        {detail.data ? (
          <RunDetail
            detail={detail.data}
            pending={resume.isPending}
            error={resume.error}
            onResume={() => resume.mutate(detail.data.run.id)}
          />
        ) : null}
      </section>
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
  );
}

function RunDetail({
  detail,
  pending,
  error,
  onResume,
}: {
  detail: AgentRunDetail;
  pending: boolean;
  error: unknown;
  onResume: () => void;
}) {
  const waiting = detail.approvals.some((item) => item.status === "pending");
  const canResume = detail.run.status === "awaiting_approval" || detail.run.status === "running";
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{detail.run.inquiry_subject}</h2>
          <p className="text-sm text-muted-foreground">
            {detail.run.qualification ? `Qualification: ${detail.run.qualification}. ` : ""}
            {detail.run.error_message ?? "Steps are stored as the run proceeds."}
          </p>
        </div>
        <Badge>{detail.run.status.replaceAll("_", " ")}</Badge>
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
      <div>
        <h3 className="mb-2 text-sm font-medium">Timeline</h3>
        <ol className="space-y-2">
          {detail.events.map((event) => (
            <li key={event.id} className="rounded-md border border-border px-3 py-2 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{event.step}</span>
                <span className="text-muted-foreground">{new Date(event.created_at).toLocaleString()}</span>
              </div>
              <p className="text-muted-foreground">{event.status}{event.error_message ? `: ${event.error_message}` : ""}</p>
              {Object.keys(event.detail).length > 0 ? (
                <pre className="mt-2 overflow-x-auto rounded-md bg-background p-2 text-xs">{JSON.stringify(event.detail, null, 2)}</pre>
              ) : null}
            </li>
          ))}
        </ol>
      </div>
      <div>
        <h3 className="mb-2 text-sm font-medium">Proposed actions</h3>
        {detail.approvals.length === 0 ? <p className="text-sm text-muted-foreground">No actions have been proposed.</p> : null}
        <div className="space-y-3">
          {detail.approvals.map((approval) => (
            <article key={approval.id} className="rounded-md border border-border p-3 text-sm">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="font-medium">{approval.action_type.replaceAll("_", " ")}</span>
                <Badge variant="secondary">{approval.status}</Badge>
              </div>
              <pre className="overflow-x-auto rounded-md bg-background p-2 text-xs">{JSON.stringify(approval.payload, null, 2)}</pre>
              {approval.execution_result ? (
                <p className="mt-2 text-muted-foreground">
                  Lead {approval.execution_result.lead_id ?? "not recorded"}
                  {approval.execution_result.interaction_id ? `, interaction ${approval.execution_result.interaction_id}` : ""}
                </p>
              ) : null}
              {approval.execution_error ? <p className="mt-2 text-red-300">{approval.execution_error}</p> : null}
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
