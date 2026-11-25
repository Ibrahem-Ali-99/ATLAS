import { apiFetch } from "@/lib/api";

export type WorkflowDefinition = { id: string; name: string; slug: string; description: string | null; version: number; active: boolean; definition: { trigger: string; schedule?: string; actions: { type: string; [key: string]: unknown }[] }; created_at: string; updated_at: string };
const path = (id: string) => `/api/v1/organizations/${id}/workflow-definitions`;
export const listWorkflowDefinitions = (id: string) => apiFetch<WorkflowDefinition[]>(path(id));
export const createWorkflowDefinition = (id: string, body: unknown) => apiFetch<WorkflowDefinition>(path(id), { method: "POST", body: JSON.stringify(body) });
export const updateWorkflowDefinition = (id: string, workflowId: string, body: unknown) => apiFetch<WorkflowDefinition>(`${path(id)}/${workflowId}`, { method: "PATCH", body: JSON.stringify(body) });
export const workflowAction = (id: string, workflowId: string, action: "activate" | "pause" | "duplicate") => apiFetch<WorkflowDefinition>(`${path(id)}/${workflowId}/${action}`, { method: "POST" });
export const deleteWorkflowDefinition = (id: string, workflowId: string) => apiFetch<void>(`${path(id)}/${workflowId}`, { method: "DELETE" });
export type WorkflowTask = { id: string; workflow_run_id: string | null; lead_id: string | null; contact_id: string | null; opportunity_id: string | null; assignee_user_id: string | null; title: string; description: string | null; status: string; priority: string; source: string; due_at: string | null; created_at: string; updated_at: string };
export const listWorkflowTasks = (id: string) => apiFetch<WorkflowTask[]>(`/api/v1/organizations/${id}/workflow-tasks`);
export const createWorkflowTask = (id: string, body: { title: string; description?: string; priority?: string; due_at?: string }) => apiFetch<WorkflowTask>(`/api/v1/organizations/${id}/workflow-tasks`, { method: "POST", body: JSON.stringify(body) });
export const updateWorkflowTask = (id: string, taskId: string, status: string) => apiFetch<{ id: string; status: string }>(`/api/v1/organizations/${id}/workflow-tasks/${taskId}`, { method: "PATCH", body: JSON.stringify({ status }) });
export const listOpportunityTasks = (id: string, opportunityId: string) => apiFetch<WorkflowTask[]>(`/api/v1/organizations/${id}/workflow-tasks?opportunity_id=${encodeURIComponent(opportunityId)}`);
export const createOpportunityTask = (id: string, opportunityId: string, title: string) => apiFetch<WorkflowTask>(`/api/v1/organizations/${id}/workflow-tasks`, { method: "POST", body: JSON.stringify({ opportunity_id: opportunityId, title }) });
