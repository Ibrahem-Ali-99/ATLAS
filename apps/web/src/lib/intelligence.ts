import { apiFetch } from "@/lib/api";
import type { DataScope } from "@/lib/provenance";

function organizationPath(organizationId: string, path: string): string {
  return `/api/v1/organizations/${organizationId}${path}`;
}

export type StatusCount = { status: string; count: number };
export type DayCount = { day: string; count: number };
export type RecentInteraction = { id: string; lead_id: string; kind: string; summary: string; created_at: string };
export type RecentAgentActivity = { id: string; status: string; inquiry_id: string; updated_at: string };

export type AnalyticsSnapshot = {
  window_days: number;
  scope: string;
  lead_origins: { operational: number; demo: number; evaluation: number; unknown: number };
  provenance_notice: string;
  companies_total: number;
  leads_total: number;
  inquiries_total: number;
  open_inquiries: number;
  lead_status: StatusCount[];
  qualification: {
    qualified: number;
    unqualified: number;
    open: number;
    closed: number;
    definition: string;
  };
  conversion: {
    won: number;
    lost: number;
    denominator: number;
    rate: number | null;
    definition: string;
  };
  lead_trend: DayCount[];
  agent_outcomes: StatusCount[];
  failed_runs: number;
  approvals: {
    pending: number;
    completed: number;
    needs_attention: number;
    approved: number;
    executing: number;
  };
  automation: {
    succeeded: number;
    failed: number;
    other: number;
    success_rate: number | null;
    definition: string;
  };
  follow_ups: { approval_requests: number; interactions: number };
  email: { sandbox_sent: number; live_sent: number; failed: number };
  calendar: { booked: number; cancelled: number; providers: string[]; notice: string };
  recent_interactions: RecentInteraction[];
  recent_agent_activity: RecentAgentActivity[];
  sales?: { opportunities_total: number; by_stage: { stage: string; count: number; value: number }[]; stage_trend: { day: string; stage: string; currency: string; count: number; value: number }[]; won: { count: number; value: number }; lost: { count: number; value: number }; tasks_completed: number; tasks_overdue: number; win_rate: number | null; average_won_value: number | null; currencies: { currency: string; count: number; value: number }[]; lead_to_opportunity: { eligible_leads: number; converted_leads: number; rate: number | null; definition: string } };
  support?: { by_channel: { channel: string; status: string; count: number }[]; handoffs: number; volume_trend: { day: string; channel: string; count: number }[]; average_first_response_seconds: number | null; first_response_sample_size: number };
  ai?: { requests: number; failed: number; failure_rate: number | null; trend: { day: string; status: string; count: number }[] };
  evaluation?: { executed: number; passed: number; pass_rate: number | null };
  workflow_performance?: { total: number; successful: number; failed: number; pending: number; running: number; success_rate: number | null; denominator: number; trend: { day: string; status: string; count: number }[] };
};

export type LeadPrediction = {
  id: string;
  lead_id: string;
  label: string;
  probability: number;
  confidence: number | null;
  contributions: { feature: string; contribution: number; relation?: string; threshold?: number }[];
  synthetic: boolean;
  model_version: string;
  notice: string;
  explanation: string;
};

export type DiagnosticRun = {
  hint_notice: string;
  inquiry: { id: string; subject: string; lead_id: string | null } | null;
  run: { id: string; status: string; error_code: string | null; hint: string | null };
  events: { step: string; status: string }[];
  approvals: { id: string; action_type: string; status: string }[];
  workflows: { id: string; status: string; error: string | null; hint: string | null }[];
  traces: {
    operation: string;
    status: string;
    latency_ms: number | null;
    tokens_in: number | null;
    tokens_out: number | null;
    cost_usd: number | null;
    error_code: string | null;
    langfuse_status: string;
  }[];
  emails: { id: string; status: string; mode: string }[];
  bookings: { id: string; status: string; provider: string }[];
};

export type Diagnostics = {
  scope: string;
  hint_notice: string;
  failed_runs: { id: string; error_code: string | null; hint: string | null }[];
  slowest_steps: { operation: string; latency_ms: number | null; agent_run_id: string | null }[];
  retries: number;
  needs_attention: { id: string; action_type: string; hint: string | null }[];
  integration_failures: { id: string; status: string; error: string | null; hint: string | null }[];
  duration_buckets: { bucket: string; count: number }[];
  cost_usd: number | null;
  cost_notice: string;
  workers: { id: string; kind: string; status: string; heartbeat_at: string; last_success_at: string | null; processed_count: number; last_error_code: string | null }[];
  ingestion_jobs: { id: string; document_id: string; status: string; attempts: number; max_attempts: number; error_code: string | null; next_attempt_at: string; updated_at: string }[];
};

export type EvaluationItem = {
  id: string;
  dataset_version: string;
  method: string;
  model_configuration: string;
  status: string;
  executed_count: number;
  passed_count: number;
  results: {
    notice?: string;
    live_model?: boolean;
    failure_cases?: { id: string; error: string | null; evidence: string }[];
  };
  created_at: string;
};

export function getAnalytics(
  organizationId: string,
  scope: DataScope = "operational",
  filters: { period?: string; startDate?: string; endDate?: string; ownerUserId?: string; channel?: string } = {},
): Promise<AnalyticsSnapshot> {
  const query = new URLSearchParams({ scope, period: filters.period ?? "30d" });
  if (filters.startDate) query.set("start_date", filters.startDate);
  if (filters.endDate) query.set("end_date", filters.endDate);
  if (filters.ownerUserId) query.set("owner_user_id", filters.ownerUserId);
  if (filters.channel) query.set("channel", filters.channel);
  return apiFetch(organizationPath(organizationId, `/analytics?${query.toString()}`));
}

export function scoreLead(organizationId: string, leadId: string): Promise<LeadPrediction> {
  return apiFetch(organizationPath(organizationId, `/leads/${leadId}/predictions`), { method: "POST" });
}

export function getLeadPrediction(organizationId: string, leadId: string): Promise<LeadPrediction> {
  return apiFetch(organizationPath(organizationId, `/leads/${leadId}/predictions`));
}

export function trainModel(organizationId: string): Promise<{ status: string }> {
  return apiFetch(organizationPath(organizationId, "/ml/train"), { method: "POST" });
}

export function getDiagnostics(
  organizationId: string,
  scope: DataScope = "operational",
): Promise<Diagnostics> {
  return apiFetch(organizationPath(organizationId, `/diagnostics?scope=${scope}`));
}

export function getDiagnosticRun(organizationId: string, runId: string): Promise<DiagnosticRun> {
  return apiFetch(organizationPath(organizationId, `/diagnostics/runs/${runId}`));
}

export function startEvaluation(organizationId: string): Promise<{ status: string }> {
  return apiFetch(organizationPath(organizationId, "/evaluations"), { method: "POST" });
}

export function listEvaluations(organizationId: string): Promise<{ notice: string; items: EvaluationItem[] }> {
  return apiFetch(organizationPath(organizationId, "/evaluations"));
}
