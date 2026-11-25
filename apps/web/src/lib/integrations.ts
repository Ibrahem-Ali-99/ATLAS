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
};

export type VerificationResult = {
  integration: IntegrationMetadata;
  verified: boolean;
  detail: string;
};

const base = (organizationId: string) =>
  `/api/v1/organizations/${organizationId}/integration-configs`;

export function getIntegrations(organizationId: string) {
  return apiFetch<IntegrationMetadata[]>(base(organizationId));
}

export function saveIntegration(
  organizationId: string,
  type: IntegrationType,
  body: { provider: string; config: Record<string, unknown>; credentials?: string; expected_version?: number },
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
