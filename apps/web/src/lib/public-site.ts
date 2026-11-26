export const publicNav = [
  { href: "/#product", label: "Product" },
  { href: "/#use-cases", label: "Use cases" },
  { href: "/#integrations", label: "Integrations" },
  { href: "/#pricing", label: "Pricing" },
  { href: "/case-study", label: "Case study" },
  { href: "/demo", label: "Demo" },
] as const;

export const workspaceRoutes = [
  { href: "/overview", label: "Overview" },
  { href: "/crm", label: "CRM" },
  { href: "/inbox", label: "Inbox" },
  { href: "/knowledge", label: "Knowledge" },
  { href: "/assistant", label: "Assistant" },
  { href: "/workflows", label: "Workflows" },
  { href: "/analytics", label: "Analytics" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/approvals", label: "Approvals" },
] as const;

export type ProductCapture = {
  src: string;
  alt: string;
  caption: string;
  title: string;
};

const recordNote = "Figures in the capture are stored records for that workspace.";

export const captures = {
  overview: {
    src: "/portfolio/01-overview.png",
    title: "Overview",
    alt: "ATLAS overview showing the approval queue and lead pipeline for Atlas Demo.",
    caption: `Overview for Atlas Demo. ${recordNote}`,
  },
  crm: {
    src: "/portfolio/02-crm.png",
    title: "CRM",
    alt: "ATLAS CRM with the fictional Harbor and Co. logistics account.",
    caption: "CRM companies, contacts, leads, and inquiries for one organization. Harbor & Co. is fictional.",
  },
  lead: {
    src: "/portfolio/06-crm-lead.png",
    title: "Lead",
    alt: "ATLAS lead record for the fictional North pier expansion.",
    caption: "A lead stays attached to its company and contact. The North pier expansion lead is fictional.",
  },
  knowledge: {
    src: "/portfolio/03-knowledge.png",
    title: "Knowledge",
    alt: "ATLAS knowledge library for the Atlas Demo workspace.",
    caption: "Uploaded documents are indexed for the organization that owns them.",
  },
  assistant: {
    src: "/portfolio/04-assistant.png",
    title: "Assistant",
    alt: "ATLAS assistant with a grounded answer and a citation from company records.",
    caption:
      "A citation is a retrieved row. With the deterministic provider, the stored answer is the fixed grounded sentence.",
  },
  runs: {
    src: "/portfolio/05-agent-runs.png",
    title: "Agent runs",
    alt: "ATLAS agent runs list for the Atlas Demo workspace.",
    caption: "An inquiry run pauses with proposed actions. The model does not approve itself.",
  },
  workflows: {
    src: "/portfolio/07-workflows.png",
    title: "Workflows",
    alt: "ATLAS workflow studio with triggers, conditions, and recorded runs.",
    caption:
      "Workflows record the branch that ran. An empty n8n URL is reported as not configured, and sandbox mail stays in the local mailbox.",
  },
  analytics: {
    src: "/portfolio/08-analytics.png",
    title: "Analytics",
    alt: "ATLAS analytics for stored lead and activity records.",
    caption: "Analytics reads stored rows. A conversion rate is omitted when there are no won or lost leads.",
  },
  monitoring: {
    src: "/portfolio/09-monitoring.png",
    title: "Monitoring",
    alt: "ATLAS monitoring view of worker heartbeats and recorded failures.",
    caption: "Monitoring shows worker heartbeats and recorded failures for the signed-in organization.",
  },
  rejected: {
    src: "/portfolio/11-approval-rejected.png",
    title: "Rejected approval",
    alt: "ATLAS approval that was rejected and therefore not sent.",
    caption: "A rejected customer response creates no delivery. The proposed message stays unsent.",
  },
  mobile: {
    src: "/portfolio/12-overview-mobile.png",
    title: "Overview on a phone",
    alt: "ATLAS overview on a narrow mobile viewport.",
    caption: "The same workspace at a narrow width. Navigation moves into a drawer.",
  },
} as const satisfies Record<string, ProductCapture>;

export const demoSteps: ProductCapture[] = [
  captures.overview,
  captures.crm,
  captures.lead,
  captures.knowledge,
  captures.assistant,
  captures.runs,
  captures.workflows,
  captures.analytics,
  captures.rejected,
  captures.mobile,
];

export const useCases = [
  {
    title: "An inquiry lands in one queue",
    body: "Harbor & Co. writes about bonded warehousing. Signed email, WhatsApp, and the website chat widget can all open an Inbox conversation for that organization.",
  },
  {
    title: "The conversation becomes CRM",
    body: "Staff link the thread to a contact, then record a lead and an inquiry. Retrying the intake returns the records already stored.",
  },
  {
    title: "The answer cites a document",
    body: "A service note is uploaded, chunked, and embedded. The assistant answers from retrieved passages or CRM rows, and stores a refusal when nothing matches.",
  },
  {
    title: "A person decides the side effect",
    body: "The inquiry agent proposes a lead update, a customer response, and an appointment. An administrator approves or rejects the stored payload. Staff cannot approve it.",
  },
  {
    title: "Follow-up can be a workflow",
    body: "A visual definition matches lead status, then takes the matching path or the otherwise path. A task can be created after approval. The run stores which branch executed.",
  },
  {
    title: "A campaign stays on the recorded audience",
    body: "A draft can target a segment, then wait. Scheduling pins sandbox or live transport, rechecks consent and suppression, and keeps a recipient-level result.",
  },
] as const;

export const integrations = [
  {
    name: "Email",
    detail: "Sandbox SMTP by default. Live replies use an allowlisted relay and still wait for approval.",
  },
  {
    name: "Website chat",
    detail: "A discovered embed stores visitor messages in Inbox. Pausing the embed blocks new public sessions.",
  },
  {
    name: "WhatsApp",
    detail: "Signed inbound messages can open a thread. Outbound replies stay behind approval and a separate live gate.",
  },
  {
    name: "Google Calendar",
    detail: "OAuth with PKCE. An approved booking rechecks availability, writes a private event, and can cancel it.",
  },
  {
    name: "n8n",
    detail: "Lead events and signed callbacks. The editor stays private. A public demo leaves the webhook URL empty.",
  },
  {
    name: "Chat models",
    detail: "OpenAI-compatible chat, including Groq. An empty key fails closed. A public demo refuses a paid key.",
  },
  {
    name: "Embeddings",
    detail: "OpenAI or local Ollama. A replacement index swaps vectors and provider settings together.",
  },
  {
    name: "Stripe",
    detail: "Test-mode prices for Starter, Pro, and Business. Entitlements change after the provider event, not at checkout click.",
  },
  {
    name: "Resend",
    detail: "Optional campaign transport and delivery feedback. Live campaigns stay off until that gate is enabled.",
  },
  {
    name: "MCP",
    detail: "Three read-only tools bound to the current organization: find a contact, get a lead, and search company knowledge.",
  },
] as const;
