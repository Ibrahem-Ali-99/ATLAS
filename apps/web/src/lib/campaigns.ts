import { apiFetch } from "@/lib/api";
export type Segment = { id: string; name: string; definition: { logic: string; conditions: { field: string; operator: string; value: string }[] }; preview: { contacts: number; leads: number } };
export type Campaign = { id: string; name: string; status: string; channel: string; segment_id: string | null; subject: string | null };
const base = (id: string) => `/api/v1/organizations/${id}`;
export const listSegments = (id: string) => apiFetch<Segment[]>(`${base(id)}/segments`);
export const createSegment = (id: string, body: unknown) => apiFetch<Segment>(`${base(id)}/segments`, { method: "POST", body: JSON.stringify(body) });
export const listCampaigns = (id: string) => apiFetch<Campaign[]>(`${base(id)}/campaigns`);
export const createCampaign = (id: string, body: unknown) => apiFetch<Campaign>(`${base(id)}/campaigns`, { method: "POST", body: JSON.stringify(body) });
