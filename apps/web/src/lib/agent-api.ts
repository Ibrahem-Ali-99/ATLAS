import { apiFetch } from "@/lib/api";
import type { AgentRunDetail, AgentRunPage, Approval, ApprovalPage, ApprovalStatus, RunStatus } from "@/lib/agent";

function organizationPath(organizationId: string, path: string): string {
  return `/api/v1/organizations/${organizationId}${path}`;
}

export function listAgentRuns(
  organizationId: string,
  params: { status?: RunStatus | ""; page?: number } = {},
): Promise<AgentRunPage> {
  const search = new URLSearchParams();
  search.set("page", String(params.page ?? 1));
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
