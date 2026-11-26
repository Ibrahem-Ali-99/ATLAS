import { apiFetch } from "@/lib/api";

export type WorkflowTrigger = "lead_created" | "lead_status_changed" | "opportunity_stage_changed" | "schedule" | "manual";
export type WorkflowCondition = { field: "lead_status" | "opportunity_stage"; operator: "equals" | "not_equals"; value: string };
export type WorkflowAction = { type: "create_task" | "update_lead" | "prepare_follow_up" | "require_approval"; title?: string; status?: string; note?: string; description?: string; priority?: "low" | "normal" | "high" | "urgent"; due_in_hours?: number };
export type WorkflowGraph = { trigger: WorkflowTrigger; interval_seconds?: number; conditions?: WorkflowCondition[]; condition_mode?: "all" | "any"; actions: WorkflowAction[]; otherwise_actions?: WorkflowAction[] };
export type WorkflowDefinition = { id: string; name: string; slug: string; description: string | null; version: number; active: boolean; activated_at: string | null; archived_at: string | null; definition: WorkflowGraph; next_run_at: string | null; last_run_at: string | null; created_at: string; updated_at: string };
export type WorkflowRunDetail = {
  id: string; status: string; manual: boolean; dry_run?: boolean; branch?: string | null;
  error: string | null; created_at: string; updated_at: string;
  lead_id: string | null; opportunity_id: string | null; approval_id: string | null; review_note: string | null;
  steps: { type: string; status: string }[]; review: { decision: string; decided_at: string } | null;
};
const path = (id: string) => `/api/v1/organizations/${id}/workflow-definitions`;
export const listWorkflowDefinitions = (id: string) => apiFetch<WorkflowDefinition[]>(path(id));
export const createWorkflowDefinition = (id: string, body: unknown) => apiFetch<WorkflowDefinition>(path(id), { method: "POST", body: JSON.stringify(body) });
export const updateWorkflowDefinition = (id: string, workflowId: string, body: unknown) => apiFetch<WorkflowDefinition>(`${path(id)}/${workflowId}`, { method: "PATCH", body: JSON.stringify(body) });
export const workflowAction = (id: string, workflowId: string, action: "activate" | "pause" | "duplicate") => apiFetch<WorkflowDefinition>(`${path(id)}/${workflowId}/${action}`, { method: "POST" });
export const deleteWorkflowDefinition = (id: string, workflowId: string) => apiFetch<void>(`${path(id)}/${workflowId}`, { method: "DELETE" });
export const validateWorkflow = (id: string, body: unknown) => apiFetch<{ valid: true }>(`${path(id)}/validate`, { method: "POST", body: JSON.stringify(body) });
export const listWorkflowRuns = (id: string, workflowId: string, include?: string) =>
  apiFetch<WorkflowRunDetail[]>(`${path(id)}/${workflowId}/runs${include ? `?include=${encodeURIComponent(include)}` : ""}`);
export const listWorkflowReviews = (id: string) =>
  apiFetch<{ id: string; workflow_id: string; name: string; note: string | null; archived: boolean }[]>(`${path(id)}/reviews`);
export const startWorkflowRun = (id: string, workflowId: string, body: { request_id: string; lead_id?: string; opportunity_id?: string; dry_run?: boolean; confirm_repeat?: boolean }) =>
  apiFetch<WorkflowRunDetail>(`${path(id)}/${workflowId}/runs`, { method: "POST", body: JSON.stringify(body) });
export const retryWorkflowRun = (id: string, workflowId: string, runId: string) =>
  apiFetch<WorkflowRunDetail>(`${path(id)}/${workflowId}/runs/${runId}/retry`, { method: "POST" });
export const reviewWorkflowRun = (id: string, workflowId: string, runId: string, decision: "approve" | "reject") =>
  apiFetch<WorkflowRunDetail>(`${path(id)}/${workflowId}/runs/${runId}/review`, { method: "POST", body: JSON.stringify({ decision }) });
export type WorkflowTask = { id: string; workflow_run_id: string | null; lead_id: string | null; contact_id: string | null; opportunity_id: string | null; assignee_user_id: string | null; title: string; description: string | null; status: string; priority: string; source: string; due_at: string | null; created_at: string; updated_at: string };
export const listWorkflowTasks = (id: string) => apiFetch<WorkflowTask[]>(`/api/v1/organizations/${id}/workflow-tasks`);
export const createWorkflowTask = (id: string, body: { title: string; description?: string; priority?: string; due_at?: string; lead_id?: string; contact_id?: string; assignee_user_id?: string }) => apiFetch<WorkflowTask>(`/api/v1/organizations/${id}/workflow-tasks`, { method: "POST", body: JSON.stringify(body) });
export const updateWorkflowTask = (id: string, taskId: string, status: string) => apiFetch<{ id: string; status: string }>(`/api/v1/organizations/${id}/workflow-tasks/${taskId}`, { method: "PATCH", body: JSON.stringify({ status }) });
export const listOpportunityTasks = (id: string, opportunityId: string) => apiFetch<WorkflowTask[]>(`/api/v1/organizations/${id}/workflow-tasks?opportunity_id=${encodeURIComponent(opportunityId)}`);
export const createOpportunityTask = (id: string, opportunityId: string, input: string | { title: string; priority?: string; due_at?: string | null }) => {
  const body = typeof input === "string" ? { title: input } : input;
  return apiFetch<WorkflowTask>(`/api/v1/organizations/${id}/workflow-tasks`, { method: "POST", body: JSON.stringify({ opportunity_id: opportunityId, ...body }) });
};
