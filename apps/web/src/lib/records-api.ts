import { apiFetch, apiStream } from "@/lib/api";
import { documentUploadForm } from "@/lib/document-upload";
import type {
  AssistantReply,
  ChunkHit,
  Company,
  CompanyInput,
  Contact,
  ContactInput,
  Conversation,
  ConversationDetail,
  DocumentOrigin,
  DocumentStatus,
  Inquiry,
  InquiryInput,
  Interaction,
  InteractionKind,
  KnowledgeDocument,
  Lead,
  LeadInput,
  LeadStatus,
  PageResult,
} from "@/lib/records";

type ListParams = {
  q?: string;
  page?: number;
  pageSize?: number;
  includeArchived?: boolean;
};

function organizationPath(organizationId: string, path: string): string {
  return `/api/v1/organizations/${organizationId}${path}`;
}

function queryString(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

function listQuery(params: ListParams): string {
  return queryString({ q: params.q, page: params.page ?? 1, page_size: params.pageSize ?? 20, include_archived: params.includeArchived ? "true" : undefined });
}

export function listCompanies(organizationId: string, params: ListParams = {}): Promise<PageResult<Company>> {
  return apiFetch(organizationPath(organizationId, `/companies${listQuery(params)}`));
}

export function getCompany(organizationId: string, recordId: string): Promise<Company> {
  return apiFetch(organizationPath(organizationId, `/companies/${recordId}`));
}

export function createCompany(organizationId: string, input: CompanyInput): Promise<Company> {
  return apiFetch(organizationPath(organizationId, "/companies"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateCompany(
  organizationId: string,
  companyId: string,
  input: Partial<CompanyInput>,
): Promise<Company> {
  return apiFetch(organizationPath(organizationId, `/companies/${companyId}`), {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteCompany(organizationId: string, companyId: string): Promise<void> {
  return apiFetch(organizationPath(organizationId, `/companies/${companyId}`), { method: "DELETE" });
}

export function restoreCompany(organizationId: string, companyId: string): Promise<Company> {
  return apiFetch(organizationPath(organizationId, `/companies/${companyId}/restore`), { method: "POST" });
}

export function listContacts(organizationId: string, params: ListParams = {}): Promise<PageResult<Contact>> {
  return apiFetch(organizationPath(organizationId, `/contacts${listQuery(params)}`));
}

export function getContact(organizationId: string, recordId: string): Promise<Contact> {
  return apiFetch(organizationPath(organizationId, `/contacts/${recordId}`));
}

export function createContact(organizationId: string, input: ContactInput): Promise<Contact> {
  return apiFetch(organizationPath(organizationId, "/contacts"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateContact(
  organizationId: string,
  contactId: string,
  input: Partial<ContactInput>,
): Promise<Contact> {
  return apiFetch(organizationPath(organizationId, `/contacts/${contactId}`), {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteContact(organizationId: string, contactId: string): Promise<void> {
  return apiFetch(organizationPath(organizationId, `/contacts/${contactId}`), { method: "DELETE" });
}

export function restoreContact(organizationId: string, contactId: string): Promise<Contact> {
  return apiFetch(organizationPath(organizationId, `/contacts/${contactId}/restore`), { method: "POST" });
}

export function listLeads(
  organizationId: string,
  params: ListParams & { status?: LeadStatus | "" } = {},
): Promise<PageResult<Lead>> {
  const search = queryString({
    q: params.q,
    status: params.status,
    page: params.page ?? 1,
    page_size: params.pageSize ?? 20,
    include_archived: params.includeArchived ? "true" : undefined,
  });
  return apiFetch(organizationPath(organizationId, `/leads${search}`));
}

export function getLead(organizationId: string, recordId: string): Promise<Lead> {
  return apiFetch(organizationPath(organizationId, `/leads/${recordId}`));
}

export function createLead(organizationId: string, input: LeadInput): Promise<Lead> {
  return apiFetch(organizationPath(organizationId, "/leads"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateLead(
  organizationId: string,
  leadId: string,
  input: Partial<LeadInput>,
): Promise<Lead> {
  return apiFetch(organizationPath(organizationId, `/leads/${leadId}`), {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteLead(organizationId: string, leadId: string): Promise<void> {
  return apiFetch(organizationPath(organizationId, `/leads/${leadId}`), { method: "DELETE" });
}

export function restoreLead(organizationId: string, leadId: string): Promise<Lead> {
  return apiFetch(organizationPath(organizationId, `/leads/${leadId}/restore`), { method: "POST" });
}

export function listInteractions(organizationId: string, leadId: string): Promise<Interaction[]> {
  return apiFetch(organizationPath(organizationId, `/leads/${leadId}/interactions`));
}

export function addInteraction(
  organizationId: string,
  leadId: string,
  input: { kind: InteractionKind; body: string },
): Promise<Interaction> {
  return apiFetch(organizationPath(organizationId, `/leads/${leadId}/interactions`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listInquiries(organizationId: string, params: ListParams = {}): Promise<PageResult<Inquiry>> {
  return apiFetch(organizationPath(organizationId, `/inquiries${listQuery(params)}`));
}

export function getInquiry(organizationId: string, recordId: string): Promise<Inquiry> {
  return apiFetch(organizationPath(organizationId, `/inquiries/${recordId}`));
}

export function createInquiry(organizationId: string, input: InquiryInput): Promise<Inquiry> {
  return apiFetch(organizationPath(organizationId, "/inquiries"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateInquiry(
  organizationId: string,
  inquiryId: string,
  input: Partial<InquiryInput>,
): Promise<Inquiry> {
  return apiFetch(organizationPath(organizationId, `/inquiries/${inquiryId}`), {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteInquiry(organizationId: string, inquiryId: string): Promise<void> {
  return apiFetch(organizationPath(organizationId, `/inquiries/${inquiryId}`), { method: "DELETE" });
}

export function restoreInquiry(organizationId: string, inquiryId: string): Promise<Inquiry> {
  return apiFetch(organizationPath(organizationId, `/inquiries/${inquiryId}/restore`), { method: "POST" });
}

export function listDocuments(
  organizationId: string,
  params: ListParams & { status?: DocumentStatus; fileType?: "pdf" | "txt" } = {},
): Promise<PageResult<KnowledgeDocument>> {
  const query = queryString({
    q: params.q,
    page: params.page,
    page_size: params.pageSize,
    status: params.status,
    file_type: params.fileType,
  });
  return apiFetch(organizationPath(organizationId, `/documents${query}`));
}

export function uploadDocument(organizationId: string, file: File, origin: DocumentOrigin = "operational"): Promise<KnowledgeDocument> {
  const body = documentUploadForm(file, origin);
  return apiFetch(organizationPath(organizationId, "/documents"), { method: "POST", body });
}

export function getDocumentJob(organizationId: string, documentId: string): Promise<{ document_id: string; status: string; error_message?: string | null }> {
  return apiFetch(organizationPath(organizationId, `/documents/${documentId}/job`));
}

export function documentChunks(organizationId: string, documentId: string): Promise<{ items: ChunkHit[] }> {
  return apiFetch(organizationPath(organizationId, `/documents/${documentId}/chunks`));
}

export function searchDocuments(organizationId: string, q: string): Promise<{ items: ChunkHit[] }> {
  return apiFetch(organizationPath(organizationId, `/documents/search${queryString({ q })}`));
}

export function createKnowledgeEvaluation(organizationId: string, question: string, expectedEvidence: string[], scenario = "grounded") {
  const expectedBehavior = scenario === "grounded" ? "answer" : scenario === "human_handoff" ? "handoff" : "fallback";
  return apiFetch<{ id: string; question: string }>(organizationPath(organizationId, "/knowledge/evaluations/questions"), { method: "POST", body: JSON.stringify({ question, expected_evidence: expectedEvidence, scenario, expected_behavior: expectedBehavior }) });
}

export function runKnowledgeEvaluation(organizationId: string, questionId: string) {
  return apiFetch<{ evidence_match: boolean; answer_grounded: boolean | null; case_result: Record<string, unknown>; retrieved_sources: { document_title: string; score: number }[]; failure_reason: string | null }>(organizationPath(organizationId, `/knowledge/evaluations/questions/${questionId}/run`), { method: "POST" });
}

export function compareKnowledgeEvaluations(organizationId: string) {
  return apiFetch<{ current: Record<string, unknown> | null; previous: Record<string, unknown> | null; regressions: unknown[]; improvements: unknown[] }>(organizationPath(organizationId, "/knowledge/evaluations/compare"));
}

export function reindexDocument(organizationId: string, documentId: string): Promise<KnowledgeDocument> {
  return apiFetch(organizationPath(organizationId, `/documents/${documentId}/reindex`), { method: "POST" });
}

export function deleteDocument(organizationId: string, documentId: string): Promise<void> {
  return apiFetch(organizationPath(organizationId, `/documents/${documentId}`), { method: "DELETE" });
}

export function listConversations(organizationId: string): Promise<Conversation[]> {
  return apiFetch(organizationPath(organizationId, "/conversations"));
}

export function createConversation(organizationId: string): Promise<Conversation> {
  return apiFetch(organizationPath(organizationId, "/conversations"), {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getConversation(organizationId: string, conversationId: string): Promise<ConversationDetail> {
  return apiFetch(organizationPath(organizationId, `/conversations/${conversationId}`));
}

export function streamConversationMessage(
  organizationId: string,
  conversationId: string,
  content: string,
  onToken: (text: string) => void,
  onPhase?: (phase: string) => void,
): Promise<AssistantReply> {
  return apiStream(
    organizationPath(organizationId, `/conversations/${conversationId}/messages/stream`),
    { content },
    onToken,
    onPhase,
  );
}
