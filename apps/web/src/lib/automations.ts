import { apiFetch } from "@/lib/api";
import type { DataScope } from "@/lib/provenance";

export type WorkflowAttempt = {
  outcome: string;
  error: string | null;
  external_id: string | null;
  started_at: string;
};

export type WorkflowRun = {
  id: string;
  kind: string;
  status: string;
  lead_id: string | null;
  agent_run_id: string | null;
  attempt_count: number;
  last_error: string | null;
  created_at: string;
  lead_title: string | null;
  company_name: string | null;
  attempts: WorkflowAttempt[];
};

export type EmailDelivery = {
  id: string;
  lead_id: string | null;
  status: string;
  mode: string;
  provider_message_id: string | null;
  error: string | null;
  sent_at: string | null;
};

export type CalendarBooking = {
  id: string;
  lead_id: string;
  status: string;
  provider: string;
  starts_at: string;
  ends_at: string;
  provider_event_id: string | null;
};

export type AutomationSnapshot = {
  email_mode: string;
  calendar_provider: string;
  n8n_configured: boolean;
  webhook_configured: boolean;
  automations: {
    name: string;
    trigger: string;
    description: string;
    kind: string;
    completed: number;
    awaiting_review: number;
    needs_attention: number;
    failed: number;
    configured: boolean;
  }[];
  runs: WorkflowRun[];
  emails: EmailDelivery[];
  bookings: CalendarBooking[];
};

function organizationPath(organizationId: string, path: string): string {
  return `/api/v1/organizations/${organizationId}${path}`;
}

export function getAutomations(
  organizationId: string,
  scope: DataScope = "operational",
): Promise<AutomationSnapshot> {
  return apiFetch(organizationPath(organizationId, `/automations?scope=${scope}`));
}

export function cancelBooking(organizationId: string, bookingId: string): Promise<CalendarBooking> {
  return apiFetch(organizationPath(organizationId, `/calendar/bookings/${bookingId}/cancel`), {
    method: "POST",
  });
}
