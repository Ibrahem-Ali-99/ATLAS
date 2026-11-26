import { apiFetch } from "@/lib/api";

export type PipelineStage = { key: string; label: string; position: number; probability: number | null; active: boolean };
export type Opportunity = { id: string; title: string; value: number | null; currency: string; stage: string; probability: number | null; owner_user_id: string; company_id: string | null; contact_id: string | null; lead_id: string | null; expected_close_date: string | null; loss_reason?: string | null; archived_at?: string | null };
const base = (id: string) => `/api/v1/organizations/${id}`;
export const listPipelineStages = (id: string) => apiFetch<PipelineStage[]>(`${base(id)}/pipeline/stages`);
export const listOpportunities = (id: string, includeArchived = false) => apiFetch<Opportunity[]>(`${base(id)}/opportunities${includeArchived ? "?include_archived=true" : ""}`);
export const archiveOpportunity = (id: string, opportunityId: string) => apiFetch<void>(`${base(id)}/opportunities/${opportunityId}`, { method: "DELETE" });
export const restoreOpportunity = (id: string, opportunityId: string) => apiFetch<Opportunity>(`${base(id)}/opportunities/${opportunityId}/restore`, { method: "POST" });
export const createOpportunity = (id: string, body: Record<string, unknown>) => apiFetch<Opportunity>(`${base(id)}/opportunities`, { method: "POST", body: JSON.stringify(body) });
export const updateOpportunity = (id: string, opportunityId: string, body: Record<string, unknown>) => apiFetch<Opportunity>(`${base(id)}/opportunities/${opportunityId}`, { method: "PATCH", body: JSON.stringify(body) });
export const updatePipelineStage = (id: string, key: string, body: { label: string; position: number; probability?: number | null }) => apiFetch<PipelineStage>(`${base(id)}/pipeline/stages/${key}`, { method: "PATCH", body: JSON.stringify(body) });
export const createPipelineStage = (id: string, body: { label: string; position: number; probability?: number | null }) => apiFetch<PipelineStage>(`${base(id)}/pipeline/stages`, { method: "POST", body: JSON.stringify(body) });
export const deletePipelineStage = (id: string, key: string) => apiFetch<void>(`${base(id)}/pipeline/stages/${key}`, { method: "DELETE" });
export const reorderPipelineStages = (id: string, keys: string[]) => apiFetch<PipelineStage[]>(`${base(id)}/pipeline/stages/reorder`, { method: "POST", body: JSON.stringify({ keys }) });
