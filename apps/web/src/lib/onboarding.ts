import { apiFetch } from "@/lib/api";

export type OnboardingState = { organization: { id: string; name: string }; setup: { business_description: string | null; industry: string | null; timezone: string; language: string; completed: boolean }; agent: { assistant_name: string; purpose: string; tone: string; response_language: string; business_instructions: string } };
export const getOnboarding = (id: string) => apiFetch<OnboardingState>(`/api/v1/organizations/${id}/onboarding`);
type OnboardingProgress = Record<"profile" | "company" | "contact" | "lead" | "inquiry" | "knowledge" | "assistant" | "workflow", boolean>;
export const getOnboardingProgress = (id: string) => apiFetch<OnboardingProgress>(`/api/v1/organizations/${id}/onboarding/progress`);
export const saveOnboarding = (id: string, body: unknown) => apiFetch<OnboardingState>(`/api/v1/organizations/${id}/onboarding`, { method: "PATCH", body: JSON.stringify(body) });
export const saveAgentConfiguration = (id: string, body: unknown) => apiFetch<OnboardingState["agent"]>(`/api/v1/organizations/${id}/agent-configuration`, { method: "PATCH", body: JSON.stringify(body) });
export const testOnboardingAssistant = (id: string, question: string) => apiFetch<{ message: string; sources: { title?: string; document_title?: string }[] }>(`/api/v1/organizations/${id}/onboarding/assistant-test`, { method: "POST", body: JSON.stringify({ question }) });
