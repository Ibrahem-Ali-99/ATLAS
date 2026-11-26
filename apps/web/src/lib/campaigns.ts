import { apiFetch } from "@/lib/api";
export type Segment = { id: string; name: string; definition: { logic: string; conditions: { field: string; operator: string; value: string }[] }; preview: { contacts: number; leads: number } };
type DeliveryMode = "sandbox" | "live";
export type Campaign = { id: string; name: string; status: string; channel: string; segment_id: string | null; subject: string | null; body: string | null; description: string | null; updated_at: string; scheduled_at: string | null; finished_at: string | null; delivery_mode: DeliveryMode };
export type CampaignDeliveryStatus = "queued" | "sending" | "accepted" | "delivered" | "bounced" | "complained" | "skipped" | "failed" | "needs_attention" | "cancelled";
type CampaignDetail = Campaign & { deliveries: Partial<Record<CampaignDeliveryStatus, number>> };
type CampaignRecipient = { id: string; email: string; status: CampaignDeliveryStatus };
type CampaignSuppression = { email: string; reason: string; created_at: string };
const base = (id: string) => `/api/v1/organizations/${id}`;
export const listSegments = (id: string) => apiFetch<Segment[]>(`${base(id)}/segments`);
export const createSegment = (id: string, body: unknown) => apiFetch<Segment>(`${base(id)}/segments`, { method: "POST", body: JSON.stringify(body) });
export const listCampaigns = (id: string) => apiFetch<Campaign[]>(`${base(id)}/campaigns`);
export const createCampaign = (id: string, body: unknown) => apiFetch<Campaign>(`${base(id)}/campaigns`, { method: "POST", body: JSON.stringify(body) });

export type CampaignDraft = { name: string; subject: string | null; body: string | null; segment_id: string | null };
export type RecipientPreview = { matching_contacts: number; valid_email: number; suppressed: number; consented: number; missing_consent: number; eligible: number };
export const updateCampaign = (id: string, campaignId: string, body: CampaignDraft) => apiFetch<Campaign>(`${base(id)}/campaigns/${campaignId}`, { method: "PATCH", body: JSON.stringify(body) });
export const previewCampaign = (id: string, campaignId: string) => apiFetch<RecipientPreview>(`${base(id)}/campaigns/${campaignId}/recipients/preview`, { method: "POST" });
export const getCampaign = (id: string, campaignId: string) =>
  apiFetch<CampaignDetail>(`${base(id)}/campaigns/${campaignId}`);
export const getCampaignTransport = (id: string) =>
  apiFetch<{ mode: DeliveryMode; ready: boolean; detail: string | null }>(`${base(id)}/campaign-transport`);
export const scheduleCampaign = (id: string, campaignId: string, scheduledAt: string | null, deliveryMode: DeliveryMode) =>
  apiFetch<CampaignDetail>(`${base(id)}/campaigns/${campaignId}/schedule`, {
    method: "POST",
    body: JSON.stringify({ scheduled_at: scheduledAt, delivery_mode: deliveryMode }),
  });
export const cancelCampaign = (id: string, campaignId: string) =>
  apiFetch<CampaignDetail>(`${base(id)}/campaigns/${campaignId}/cancel`, { method: "POST" });
export const listCampaignRecipients = (id: string, campaignId: string, offset: number) =>
  apiFetch<CampaignRecipient[]>(`${base(id)}/campaigns/${campaignId}/deliveries?offset=${offset}`);
export const listCampaignSuppressions = (id: string, offset: number) =>
  apiFetch<CampaignSuppression[]>(`${base(id)}/campaign-suppressions?offset=${offset}`);
export const suppressCampaignAddress = (id: string, email: string) =>
  apiFetch<{ email: string; suppressed: boolean }>(
    `${base(id)}/campaign-suppressions`, { method: "POST", body: JSON.stringify({ email }) },
  );

export type ConsentStatus = "granted" | "revoked";
type MarketingConsent = { contact_id: string; status: ConsentStatus | null; source: string | null };
const consentPath = (id: string, contactId: string) => `${base(id)}/contacts/${contactId}/marketing-consent`;
export const getMarketingConsent = (id: string, contactId: string) =>
  apiFetch<MarketingConsent>(consentPath(id, contactId));
export const recordMarketingConsent = (id: string, contactId: string, status: ConsentStatus, source: string) =>
  apiFetch<MarketingConsent>(consentPath(id, contactId), {
    method: "POST",
    body: JSON.stringify({ status, source }),
  });
