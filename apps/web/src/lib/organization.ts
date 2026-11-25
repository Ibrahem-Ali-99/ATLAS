import { apiFetch } from "@/lib/api";

export type TeamMember = { membership_id: string; user_id: string; email: string; full_name: string; role: "admin" | "staff"; joined_at: string; is_active: boolean };
const base = (id: string) => `/api/v1/organizations/${id}`;
export function updateOrganization(id: string, name: string) { return apiFetch(`${base(id)}`, { method: "PATCH", body: JSON.stringify({ name }) }); }
export function listTeam(id: string) { return apiFetch<TeamMember[]>(`${base(id)}/members`); }
export function updateMemberRole(id: string, memberId: string, role: TeamMember["role"]) { return apiFetch<TeamMember>(`${base(id)}/members/${memberId}`, { method: "PATCH", body: JSON.stringify({ role }) }); }
export function removeMember(id: string, memberId: string) { return apiFetch<void>(`${base(id)}/members/${memberId}`, { method: "DELETE" }); }
