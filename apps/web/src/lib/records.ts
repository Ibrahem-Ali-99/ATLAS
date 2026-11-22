export type PageResult<T> = {
  page: number;
  page_size: number;
  total: number;
  items: T[];
};

export type Company = {
  id: string;
  organization_id: string;
  name: string;
  website: string | null;
  industry: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type CompanyInput = {
  name: string;
  website?: string | null;
  industry?: string | null;
  notes?: string | null;
};

export type Contact = {
  id: string;
  organization_id: string;
  company_id: string | null;
  full_name: string;
  email: string | null;
  phone: string | null;
  title: string | null;
  created_at: string;
  updated_at: string;
};

export type ContactInput = {
  full_name: string;
  email?: string | null;
  phone?: string | null;
  title?: string | null;
  company_id?: string | null;
};

export const leadStatuses = [
  "new",
  "contacted",
  "qualified",
  "unqualified",
  "won",
  "lost",
] as const;

export type LeadStatus = (typeof leadStatuses)[number];

export type Lead = {
  id: string;
  organization_id: string;
  company_id: string | null;
  contact_id: string | null;
  owner_user_id: string;
  title: string;
  status: LeadStatus;
  source: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type LeadInput = {
  title: string;
  status?: LeadStatus;
  company_id?: string | null;
  contact_id?: string | null;
  source?: string | null;
  notes?: string | null;
};

export type Inquiry = {
  id: string;
  organization_id: string;
  company_id: string | null;
  lead_id: string | null;
  subject: string;
  body: string;
  created_at: string;
};

export type InquiryInput = {
  subject: string;
  body: string;
  company_id?: string | null;
  lead_id?: string | null;
};

export const interactionKinds = ["note", "call", "email"] as const;

export type InteractionKind = (typeof interactionKinds)[number];

export type Interaction = {
  id: string;
  organization_id: string;
  lead_id: string;
  author_user_id: string;
  kind: InteractionKind;
  body: string;
  created_at: string;
};

export const documentStatuses = ["pending", "processing", "ready", "failed"] as const;

export type DocumentStatus = (typeof documentStatuses)[number];

export type KnowledgeDocument = {
  id: string;
  organization_id: string;
  uploaded_by: string;
  title: string;
  filename: string;
  media_type: string;
  byte_size: number;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type ChunkHit = {
  id: string;
  document_id: string;
  document_title: string;
  chunk_index: number;
  page_number: number | null;
  content: string;
  score: number;
};

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type MessageSource = {
  kind: "document" | "crm";
  title: string;
  excerpt: string;
  document_id: string | null;
  chunk_id: string | null;
  page_number: number | null;
  record_type: string | null;
  record_id: string | null;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  sources: MessageSource[];
};

export type ConversationDetail = Conversation & {
  messages: ChatMessage[];
};

export type AssistantReply = {
  conversation_id: string;
  message: ChatMessage;
  document_search: "ready" | "empty" | "unconfigured";
};

export function blankToNull(value: string | null | undefined): string | null {
  const trimmed = value?.trim() ?? "";
  return trimmed.length === 0 ? null : trimmed;
}
