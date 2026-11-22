import { apiFetch } from "@/lib/api";

function organizationPath(organizationId: string, path: string): string {
  return `/api/v1/organizations/${organizationId}${path}`;
}

export type StatusCount = { status: string; count: number };
export type DayCount = { day: string; count: number };

export type AnalyticsSnapshot = {
  window_days: number;
  synthetic_notice: string;
  leads_total: number;
  inquiries_total: number;
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
  hint_notice: string;
  failed_runs: { id: string; error_code: string | null; hint: string | null }[];
  slowest_steps: { operation: string; latency_ms: number | null; agent_run_id: string | null }[];
  retries: number;
  needs_attention: { id: string; action_type: string; hint: string | null }[];
  integration_failures: { id: string; status: string; error: string | null; hint: string | null }[];
  duration_buckets: { bucket: string; count: number }[];
  cost_usd: number | null;
  cost_notice: string;
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

export function getAnalytics(organizationId: string): Promise<AnalyticsSnapshot> {
  return apiFetch(organizationPath(organizationId, "/analytics"));
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

export function getDiagnostics(organizationId: string): Promise<Diagnostics> {
  return apiFetch(organizationPath(organizationId, "/diagnostics"));
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
