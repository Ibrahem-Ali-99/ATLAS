import { apiFetch } from "@/lib/api";
import type { AgentRunDetail, AgentRunPage, Approval, ApprovalPage, ApprovalStatus, RunStatus } from "@/lib/agent";
import type { DataScope } from "@/lib/provenance";

function organizationPath(organizationId: string, path: string): string {
  return `/api/v1/organizations/${organizationId}${path}`;
}

export type AssistantExecutionStep = {
  sequence: number;
  tool_name: string;
  status: "succeeded" | "failed" | "recovered";
  duration_ms: number;
  arguments: Record<string, unknown>;
  records: Array<Record<string, unknown>>;
  error_message: string | null;
  recovery: string | null;
};

export type AssistantExecution = {
  id: string;
  request: string;
  status: "running" | "completed" | "failed";
  tools: string[];
  tokens_in: number | null;
  tokens_out: number | null;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
  steps: AssistantExecutionStep[];
};

export type AssistantExecutionPage = {
  items: AssistantExecution[];
  page: number;
  page_size: number;
  total: number;
};

export function listAssistantExecutions(
  organizationId: string,
  page = 1,
): Promise<AssistantExecutionPage> {
  return apiFetch(organizationPath(organizationId, `/assistant-executions?page=${page}`));
}

export function listAgentRuns(
  organizationId: string,
  params: { status?: RunStatus | ""; page?: number; scope?: DataScope } = {},
): Promise<AgentRunPage> {
  const search = new URLSearchParams();
  search.set("page", String(params.page ?? 1));
  search.set("scope", params.scope ?? "all");
  if (params.status) {
    search.set("status", params.status);
  }
  return apiFetch(organizationPath(organizationId, `/agent-runs?${search.toString()}`));
}

export function getAgentRun(organizationId: string, runId: string): Promise<AgentRunDetail> {
  return apiFetch(organizationPath(organizationId, `/agent-runs/${runId}`));
}

export function startAgentRun(organizationId: string, inquiryId: string): Promise<AgentRunDetail> {
  return apiFetch(organizationPath(organizationId, "/agent-runs"), {
    method: "POST",
    body: JSON.stringify({ inquiry_id: inquiryId }),
  });
}

export function resumeAgentRun(organizationId: string, runId: string): Promise<AgentRunDetail> {
  return apiFetch(organizationPath(organizationId, `/agent-runs/${runId}/resume`), {
    method: "POST",
  });
}

export function listApprovals(
  organizationId: string,
  params: { status?: ApprovalStatus | ""; page?: number } = {},
): Promise<ApprovalPage> {
  const search = new URLSearchParams();
  search.set("page", String(params.page ?? 1));
  if (params.status) {
    search.set("status", params.status);
  }
  return apiFetch(organizationPath(organizationId, `/approvals?${search.toString()}`));
}

export function executeApproval(organizationId: string, approvalId: string): Promise<Approval> {
  return apiFetch(organizationPath(organizationId, `/approvals/${approvalId}/execute`), {
    method: "POST",
  });
}

export function getApproval(organizationId: string, approvalId: string): Promise<Approval> {
  return apiFetch(organizationPath(organizationId, `/approvals/${approvalId}`));
}

export function decideApproval(
  organizationId: string,
  approvalId: string,
  decision: "approve" | "reject",
  note: string,
): Promise<Approval> {
  return apiFetch(organizationPath(organizationId, `/approvals/${approvalId}/${decision}`), {
    method: "POST",
    body: JSON.stringify({ note: note.trim() ? note.trim() : null }),
  });
}
