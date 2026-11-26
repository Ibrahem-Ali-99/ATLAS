export const publicNav = [
  { href: "/#product", label: "Product" },
  { href: "/demo", label: "Demo" },
  { href: "/#integrations", label: "Integrations" },
  { href: "/#pricing", label: "Pricing" },
  { href: "/case-study", label: "Case study" },
] as const;

export const footerNav = [
  { href: "/#product", label: "Product" },
  { href: "/#assistant", label: "Assistant" },
  { href: "/#crm", label: "CRM" },
  { href: "/#workflows", label: "Automation" },
  { href: "/#analytics", label: "Analytics" },
  { href: "/#integrations", label: "Integrations" },
  { href: "/#architecture", label: "Architecture" },
  { href: "/#evidence", label: "Evaluation" },
  { href: "/#pricing", label: "Pricing" },
  { href: "/case-study", label: "Case study" },
  { href: "/demo", label: "Demo" },
  { href: "/login", label: "Sign in" },
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

/**
 * Desktop product frames are 16:10, matching a 1440×900 workspace viewport.
 * A capture may sit in that frame only when the hidden strip is at most 10%
 * of its height. Taller full-page captures stay on the demo tour until a
 * viewport screenshot replaces them.
 */
export const landscapeFrame = { width: 1440, height: 900 } as const;
export const landscapeCropLimit = 0.1;

/** One phone viewport. Full-page mobile captures scroll inside this frame. */
export const phoneFrame = { width: 390, height: 844 } as const;

export type ProductCapture = {
  src: string;
  alt: string;
  caption: string;
  title: string;
  width: number;
  height: number;
  /**
   * True only after a 1440×900 capture of the redesigned workspace replaces
   * the file. The current portfolio files are not that set.
   */
  releaseReady: boolean;
};

export function landscapeCropFraction(width: number, height: number): number {
  const visibleHeight = width * (landscapeFrame.height / landscapeFrame.width);
  if (height <= visibleHeight) return 0;
  return (height - visibleHeight) / height;
}

export function fitsLandscapeFrame(capture: Pick<ProductCapture, "width" | "height">): boolean {
  return landscapeCropFraction(capture.width, capture.height) <= landscapeCropLimit;
}

export function isReleaseCapture(capture: ProductCapture): boolean {
  return (
    capture.releaseReady &&
    capture.width === landscapeFrame.width &&
    capture.height === landscapeFrame.height
  );
}

const recordNote = "Figures in the capture are stored records for that workspace.";

export const captures = {
  overview: {
    src: "/portfolio/01-overview.png",
    title: "Overview",
    alt: "ATLAS overview showing the approval queue and lead pipeline for Atlas Demo.",
    caption: `Overview for Atlas Demo. ${recordNote}`,
    width: 1440,
    height: 975,
    releaseReady: false,
  },
  crm: {
    src: "/portfolio/02-crm.png",
    title: "CRM",
    alt: "ATLAS CRM with customer records for the Atlas Demo workspace.",
    caption: "CRM companies, contacts, leads, and inquiries for one organization. Harbor & Co. is fictional.",
    width: 1440,
    height: 1388,
    releaseReady: false,
  },
  lead: {
    src: "/portfolio/06-crm-lead.png",
    title: "Lead",
    alt: "ATLAS lead record for the fictional North pier expansion.",
    caption: "A lead stays attached to its company and contact. The North pier expansion lead is fictional.",
    width: 1440,
    height: 1339,
    releaseReady: false,
  },
  knowledge: {
    src: "/portfolio/03-knowledge.png",
    title: "Knowledge",
    alt: "ATLAS knowledge library for the Atlas Demo workspace.",
    caption: "Uploaded documents are indexed for the organization that owns them.",
    width: 1440,
    height: 4470,
    releaseReady: false,
  },
  assistant: {
    src: "/portfolio/04-assistant.png",
    title: "Assistant",
    alt: "ATLAS assistant with a grounded answer and a citation from company records.",
    caption:
      "A citation is a retrieved row. With the deterministic provider, the stored answer is the fixed grounded sentence.",
    width: 1440,
    height: 900,
    releaseReady: false,
  },
  runs: {
    src: "/portfolio/05-agent-runs.png",
    title: "Agent runs",
    alt: "ATLAS agent runs list for the Atlas Demo workspace.",
    caption: "An inquiry run pauses with proposed actions. The model does not approve itself.",
    width: 1440,
    height: 1903,
    releaseReady: false,
  },
  workflows: {
    src: "/portfolio/07-workflows.png",
    title: "Workflows",
    alt: "ATLAS workflow studio with triggers, conditions, and recorded runs.",
    caption:
      "Workflows record the branch that ran. An empty n8n URL is reported as not configured, and sandbox mail stays in the local mailbox.",
    width: 1440,
    height: 976,
    releaseReady: false,
  },
  analytics: {
    src: "/portfolio/08-analytics.png",
    title: "Analytics",
    alt: "ATLAS analytics for stored lead and activity records.",
    caption: "Analytics reads stored rows. A conversion rate is omitted when there are no won or lost leads.",
    width: 1440,
    height: 1250,
    releaseReady: false,
  },
  monitoring: {
    src: "/portfolio/09-monitoring.png",
    title: "Monitoring",
    alt: "ATLAS monitoring view of recorded issues for one organization.",
    caption: "Monitoring shows recorded issues for the signed-in organization.",
    width: 1440,
    height: 1083,
    releaseReady: false,
  },
  settings: {
    src: "/portfolio/10-settings.png",
    title: "Settings",
    alt: "ATLAS settings showing the account, organization membership, model names, and sandbox delivery status. Secrets are not shown.",
    caption: "Settings for Atlas Demo. API keys are not shown. Email is sandbox, the calendar is simulated, and n8n is not configured.",
    width: 1440,
    height: 900,
    releaseReady: false,
  },
  rejected: {
    src: "/portfolio/11-approval-rejected.png",
    title: "Rejected approval",
    alt: "ATLAS approval that was rejected and therefore not sent.",
    caption: "A rejected customer response creates no delivery. The proposed message stays unsent.",
    width: 1440,
    height: 1808,
    releaseReady: false,
  },
  mobile: {
    src: "/portfolio/12-overview-mobile.png",
    title: "Overview on a phone",
    alt: "ATLAS overview on a narrow mobile viewport.",
    caption: "The same workspace at a narrow width. Navigation moves into a drawer.",
    width: 390,
    height: 1898,
    releaseReady: false,
  },
} as const satisfies Record<string, ProductCapture>;

/**
 * Surfaces the release pass will photograph at 1440×900 once the redesigned
 * workspace and Harbor demonstration rows are the ones on screen.
 */
export const releaseShotPlan = [
  "Overview",
  "CRM",
  "Inbox",
  "Assistant",
  "Knowledge",
  "Workflows",
  "Analytics",
  "Integrations",
] as const;

/** Homepage stages. Each one fits the 16:10 frame without a heavy crop. */
export const homepageStages = {
  hero: captures.overview,
  assistant: captures.assistant,
  automation: captures.workflows,
  architecture: captures.settings,
} as const;

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

export const capabilities = [
  {
    title: "One tenant boundary",
    body: "Companies, documents, conversations, and approvals stay on the membership. A second organization, Northwind in the local seed, is not listed with Atlas Demo.",
  },
  {
    title: "A cited answer, or a refusal",
    body: "Retrieval mixes vector distance and full text, then keeps a passage when it shares wording with the question. When nothing matches, the assistant stores a refusal and does not call the model.",
  },
  {
    title: "Approval before a side effect",
    body: "The agent proposes a lead change, a reply, and an appointment. An administrator approves the stored payload. If that payload changes, execute does nothing.",
  },
  {
    title: "A recorded workflow path",
    body: "A visual definition matches all or any conditions, then follows the matching path or the otherwise path. The run stores which branch executed.",
  },
] as const;

export const useCases = [
  {
    title: "An inquiry lands in one queue",
    body: "Harbor & Co. writes about bonded warehousing. Signed email, WhatsApp, and the website chat widget can all open an Inbox conversation for that organization.",
  },
  {
    title: "The conversation becomes CRM",
    body: "Staff link the thread to a contact, then record a lead and an inquiry. Doing it again returns the records already stored.",
  },
  {
    title: "The answer cites a document",
    body: "A service note is uploaded, chunked, and embedded. The assistant answers from retrieved passages or CRM rows, and stores a refusal when nothing matches.",
  },
  {
    title: "A person decides what happens next",
    body: "ATLAS can propose a lead update, a reply, and an appointment. An administrator approves or rejects it. Staff cannot approve it.",
  },
  {
    title: "Follow-up can be a workflow",
    body: "A visual definition matches lead status, then takes the matching path or the otherwise path. A task can be created after approval. The run stores which branch executed.",
  },
  {
    title: "A campaign stays with the people who agreed",
    body: "A draft can target a segment, then wait. Scheduling pins sandbox or live transport, rechecks consent and suppression, and keeps a recipient-level result.",
  },
] as const;

export const reportingRules = [
  {
    title: "Counts come from stored rows",
    body: "Overview and analytics read the signed-in organization. Demo, operational, evaluation, and legacy origins can be filtered, because one tenant can hold more than one kind of record.",
  },
  {
    title: "An empty rate stays empty",
    body: "Conversion is won divided by won plus lost. The rate stays blank when that denominator is zero. A missing amount is not drawn as a zero.",
  },
  {
    title: "Currencies are not added together",
    body: "Pipeline amounts stay in their own currency. Monitoring shows worker heartbeats and recorded failures for the same organization.",
  },
] as const;

export const integrationGroups = [
  {
    name: "Customer channels",
    items: [
      {
        name: "Email",
        detail: "Sandbox SMTP by default. Live replies use an allowlisted relay and still wait for approval.",
      },
      {
        name: "Website chat",
        detail: "Website conversations arrive in Inbox. Pausing the embed stops new public chats.",
      },
      {
        name: "WhatsApp",
        detail: "Signed inbound messages can open a thread. Outbound replies stay behind approval and a separate live gate.",
      },
      {
        name: "Resend",
        detail: "Optional campaign delivery and feedback. Live campaigns stay off until they are enabled.",
      },
    ],
  },
  {
    name: "Calendar and automation",
    items: [
      {
        name: "Google Calendar",
        detail: "OAuth with PKCE. An approved booking rechecks availability, writes a private event, and can cancel it.",
      },
      {
        name: "n8n",
        detail: "Lead events and signed callbacks. The editor stays private. A public demo leaves the webhook URL empty.",
      },
    ],
  },
  {
    name: "Models and billing",
    items: [
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
        name: "MCP",
        detail: "Three read-only tools bound to the current organization: find a contact, get a lead, and search company knowledge.",
      },
    ],
  },
] as const;

export const integrations = integrationGroups.flatMap((group) =>
  group.items.map((item): { name: string; detail: string } => ({
    name: item.name,
    detail: item.detail,
  })),
);

export const architectureSteps = ["Browser", "Next.js", "FastAPI", "PostgreSQL"] as const;

/**
 * Recorded hybrid-versus-baseline comparison on a separate fictional corpus.
 * Hash embeddings, K = 5. This is not the held-out evaluation.
 */
export const retrievalComparison = {
  recordedOn: "26 November 2026",
  documents: 7,
  questions: 8,
  heldOutRecorded: false,
  rows: [
    { measure: "Recall@5", baseline: "0.4167", hybrid: "1.0000" },
    { measure: "MRR", baseline: "0.5000", hybrid: "1.0000" },
    { measure: "nDCG@5", baseline: "0.4355", hybrid: "1.0000" },
    { measure: "Answer relevance", baseline: "0.4167", hybrid: "0.9167" },
    { measure: "Faithfulness", baseline: "0.5000", hybrid: "1.0000" },
    { measure: "Citation accuracy", baseline: "0.5000", hybrid: "1.0000" },
    { measure: "Abstention accuracy", baseline: "0.6250", hybrid: "1.0000" },
    { measure: "Mean retrieval latency", baseline: "7.88 ms", hybrid: "9.73 ms" },
  ],
} as const;

/**
 * Recorded on 26 November 2026 for the working tree that included b71d0de
 * and the qualification fixes in 44631e1. These are suite results, not
 * customer or revenue figures.
 */
export const evaluationEvidence = {
  checkedOn: "26 November 2026",
  api: { passed: 284, skipped: 1, failed: 0 },
  browser: { passed: 37, skipped: 2, failed: 0 },
  frontend: { passed: 12, failed: 0 },
  buildPassed: true,
  alembicHead: "20261126_0055",
  caveat:
    "The working tree also held uncommitted demo and deployment files, so these counts are not a clean checkout of 44631e1. The runs used atlas_test and a disposable atlas_e2e database, sandbox billing, and sandbox mail. They did not send a message or create a charge.",
} as const;
