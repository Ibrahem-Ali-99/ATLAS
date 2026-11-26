import { apiFetch } from "@/lib/api";

export type IntegrationType = "chat" | "embedding" | "n8n" | "email" | "whatsapp";
export type IntegrationStatus = "configured" | "disabled" | "verification_failed";

export type IntegrationMetadata = {
  id: string;
  organization_id: string;
  integration_type: IntegrationType;
  provider: string;
  config: Record<string, unknown>;
  status: IntegrationStatus;
  credential_version: number;
  has_credentials: boolean;
  created_at: string;
  updated_at: string;
  verified_at: string | null;
  verification_detail: string | null;
  last_inbound_at?: string | null;
};

export function integrationConnection(record?: IntegrationMetadata) {
  if (!record) return "Not configured";
  if (record.status === "disabled") return "Disconnected";
  if (record.status === "verification_failed") {
    return record.verification_detail === "WhatsApp access token expired" ? "Credentials expired" : "Verification failed";
  }
  if (!record.verified_at) return "Configured";
  return record.last_inbound_at ? "Connected" : "Verified";
}

export function modelConnection(record: IntegrationMetadata | undefined, deploymentReady: boolean | undefined) {
  if (record) return `Workspace · ${integrationConnection(record)}`;
  if (deploymentReady === undefined) return "Checking";
  return deploymentReady ? "Managed by deployment" : "Not configured";
}

export type VerificationResult = {
  integration: IntegrationMetadata | null;
  verified: boolean;
  detail: string;
};

const base = (organizationId: string) =>
  `/api/v1/organizations/${organizationId}/integration-configs`;

export function getIntegrations(organizationId: string) {
  return apiFetch<IntegrationMetadata[]>(base(organizationId));
}

export function getWebhookKeyStatus(organizationId: string) {
  return apiFetch<{
    id: string;
    created_at: string;
    rotated_at: string | null;
    revoked_at: string | null;
    last_accepted_at: string | null;
  } | null>(`/api/v1/organizations/${organizationId}/integrations/webhook-keys`);
}

export function issueWebhookKey(organizationId: string, rotate = false) {
  return apiFetch<{ id: string; secret: string }>(
    `/api/v1/organizations/${organizationId}/integrations/webhook-keys${rotate ? "/rotate" : ""}`,
    { method: "POST" },
  );
}

export function disconnectWebhookKey(organizationId: string) {
  return apiFetch<void>(`/api/v1/organizations/${organizationId}/integrations/webhook-keys/revoke`, { method: "POST" });
}

export function saveIntegration(
  organizationId: string,
  type: IntegrationType,
  body: { provider: string; config: Record<string, unknown>; credentials?: string; expected_version?: number; merge_email_credentials?: boolean },
) {
  return apiFetch<IntegrationMetadata>(`${base(organizationId)}/${type}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function replaceIntegrationCredentials(
  organizationId: string,
  type: IntegrationType,
  credentials: string,
  expectedVersion: number,
) {
  return apiFetch<IntegrationMetadata>(`${base(organizationId)}/${type}/credentials`, {
    method: "POST",
    body: JSON.stringify({ credentials, expected_version: expectedVersion }),
  });
}

export function integrationAction(
  organizationId: string,
  type: IntegrationType,
  action: "enable" | "disable" | "revoke",
  expectedVersion: number,
) {
  return apiFetch<IntegrationMetadata>(`${base(organizationId)}/${type}/${action}`, {
    method: "POST",
    body: JSON.stringify({ expected_version: expectedVersion }),
  });
}

export type WhatsAppTestStatus = {
  test_number_confirmed: boolean;
  recipient_approved: boolean;
  recipient_suffix: string | null;
  test_reply_sent: boolean;
  test_reply_pending: boolean;
  production_messaging_enabled: boolean;
};

export function getWhatsAppTestStatus(organizationId: string) {
  return apiFetch<WhatsAppTestStatus>(`${base(organizationId)}/whatsapp/test-reply`);
}

export function approveWhatsAppTestRecipient(
  organizationId: string,
  phone: string | null,
  expectedVersion: number,
) {
  return apiFetch<WhatsAppTestStatus>(`${base(organizationId)}/whatsapp/test-reply-recipient`, {
    method: "PUT",
    body: JSON.stringify({ phone, expected_version: expectedVersion }),
  });
}

export function verifyIntegration(organizationId: string, type: IntegrationType) {
  return apiFetch<VerificationResult>(`${base(organizationId)}/${type}/verify`, {
    method: "POST",
  });
}

export type EmailDomain = {
  id: string;
  organization_id: string;
  provider: string;
  domain: string;
  status: "pending" | "verified" | "failed" | "revoked";
  dns_records: { record_type: string; name: string; value: string }[];
  credential_version: number;
  verified_at?: string | null;
  checked_at?: string | null;
};

export function getEmailDomains(organizationId: string) {
  return apiFetch<EmailDomain[]>(`${base(organizationId)}/email-domains`);
}

export function registerEmailDomain(organizationId: string, domain: string) {
  return apiFetch<EmailDomain>(`${base(organizationId)}/email-domains`, {
    method: "POST",
    body: JSON.stringify({ domain }),
  });
}

export function checkEmailDomain(organizationId: string, id: string) {
  return apiFetch<EmailDomain>(`${base(organizationId)}/email-domains/${id}/check`, { method: "POST" });
}

export function revokeEmailDomain(organizationId: string, id: string) {
  return apiFetch<EmailDomain>(`${base(organizationId)}/email-domains/${id}/revoke`, { method: "POST" });
}

export type ResendTestStatus = {
  credential_configured: boolean;
  test_delivery_verified: boolean;
  sending_domain_verified: boolean;
  production_delivery_enabled: boolean;
  test_sender: string;
  approved_recipient: string | null;
  official_recipients: string[];
  last_test_recipient: string | null;
  last_test_message_id: string | null;
  last_test_at: string | null;
  provider_confirmation: "accepted" | "retrieved" | null;
};

export function getResendTestStatus(organizationId: string) {
  return apiFetch<ResendTestStatus>(`${base(organizationId)}/email/resend-test`);
}

export function approveResendTestRecipient(organizationId: string, address: string | null, expectedVersion: number) {
  return apiFetch<ResendTestStatus>(`${base(organizationId)}/email/resend-test-recipient`, {
    method: "PUT",
    body: JSON.stringify({ address, expected_version: expectedVersion }),
  });
}

export type ResendTestReceipt = {
  message_id: string;
  recipient: string;
  sender: string;
  provider_confirmation: "accepted" | "retrieved";
  status: ResendTestStatus;
};

export function sendResendTest(organizationId: string, recipient: string) {
  return apiFetch<ResendTestReceipt>(`${base(organizationId)}/email/resend-test`, {
    method: "POST",
    body: JSON.stringify({ recipient }),
  });
}
