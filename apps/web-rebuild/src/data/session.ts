import { apiFetch, setCsrfToken } from "./client.ts";

export type Membership = {
  id: string;
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  role: "admin" | "staff";
};

export type Session = {
  user: { id: string; email: string; full_name: string };
  memberships: Membership[];
  csrf_token: string;
  demo?: boolean;
};

export async function getSession(): Promise<Session> {
  const session = await apiFetch<Session>("/api/v1/auth/me");
  setCsrfToken(session.csrf_token);
  return session;
}

export async function login(email: string, password: string): Promise<Session> {
  const session = await apiFetch<Session>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setCsrfToken(session.csrf_token);
  return session;
}

export async function logout(): Promise<void> {
  await apiFetch<void>("/api/v1/auth/logout", { method: "POST" });
  setCsrfToken(null);
}

export function requestPasswordReset(email: string): Promise<{ detail: string }> {
  return apiFetch("/api/v1/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
}

export function resetPassword(token: string, password: string): Promise<void> {
  return apiFetch("/api/v1/auth/reset-password", { method: "POST", body: JSON.stringify({ token, password }) });
}

export function acceptInvitation(token: string, fullName: string, password: string): Promise<{ organization_name: string }> {
  return apiFetch("/api/v1/invitations/accept", {
    method: "POST",
    body: JSON.stringify({ token, full_name: fullName, password }),
  });
}
