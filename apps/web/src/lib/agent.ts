import type { PageResult } from "@/lib/records";

export type RunStatus = "running" | "awaiting_approval" | "completed" | "failed";

export type ApprovalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "executing"
  | "executed"
  | "failed"
  | "expired";

export type ActionType =
  | "create_lead"
  | "update_lead"
  | "prepare_customer_response"
  | "request_appointment";

export type AgentEvent = {
  id: string;
  run_id: string;
  step: string;
  status: string;
  detail: Record<string, unknown>;
  error_message: string | null;
  created_at: string;
};

export type AgentRun = {
  id: string;
  organization_id: string;
  inquiry_id: string;
  inquiry_subject: string;
  started_by: string;
  status: RunStatus;
  qualification: string | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
};

export type ExecutionResult = {
  lead_id?: string;
  interaction_id?: string;
};

export type Approval = {
  id: string;
  organization_id: string;
  run_id: string;
  requested_by: string;
  action_type: ActionType;
  position: number;
  payload: Record<string, unknown>;
  payload_hash: string;
  status: ApprovalStatus;
  expires_at: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  executed_at: string | null;
  execution_result: ExecutionResult | null;
  execution_error: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentRunDetail = {
  run: AgentRun;
  events: AgentEvent[];
  approvals: Approval[];
};

export type AgentRunPage = PageResult<AgentRun>;
export type ApprovalPage = PageResult<Approval>;
