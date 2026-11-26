import { apiFetch } from "@/lib/api";

const base = (id: string) => `/api/v1/organizations/${id}/calendar`;
type Times = { starts_at: string; ends_at: string };
export type CalendarConnection = { available: boolean; connected: boolean; calendar_name: string | null; connection_error: string | null };

export const getCalendarConnection = (id: string) =>
  apiFetch<CalendarConnection>(`${base(id)}/google`);
export const connectCalendar = (id: string) =>
  apiFetch<{ url: string }>(`${base(id)}/google/connect`, { method: "POST" });
export const disconnectCalendar = (id: string) =>
  apiFetch<{ grant_revoked: boolean }>(`${base(id)}/google/disconnect`, { method: "POST" });
export const checkCalendarAvailability = (id: string, times: Times) =>
  apiFetch<{ available: boolean; provider: "google" | "workspace" }>(
    `${base(id)}/availability`, { method: "POST", body: JSON.stringify(times) },
  );
export const requestAppointment = (id: string, leadId: string, times: Times) =>
  apiFetch<{ approval_id: string }>(`${base(id)}/requests`, {
    method: "POST", body: JSON.stringify({ lead_id: leadId, ...times }),
  });
