import { apiFetch } from "@/lib/api";

export type CreatedInvitation = { id: string; email: string; role: "staff"; expires_at: string; token: string };
export type AcceptedInvitation = { user: { id: string; email: string; full_name: string }; organization_id: string; organization_name: string };
export type InvitationStatus = { id: string; email: string; role: "staff"; expires_at: string; accepted_at: string | null; created_at: string };

export function createInvitation(organizationId: string, email: string): Promise<CreatedInvitation> {
  return apiFetch<CreatedInvitation>(`/api/v1/organizations/${organizationId}/invitations`, { method: "POST", body: JSON.stringify({ email }) });
}

export function acceptInvitation(token: string, fullName: string, password: string): Promise<AcceptedInvitation> {
  return apiFetch<AcceptedInvitation>("/api/v1/invitations/accept", { method: "POST", body: JSON.stringify({ token, full_name: fullName, password }) });
}

export function listInvitations(organizationId: string): Promise<InvitationStatus[]> {
  return apiFetch<InvitationStatus[]>(`/api/v1/organizations/${organizationId}/invitations`);
}
