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
   * True when this file is a 1440×900 capture of the redesigned Harbor workspace.
   * The assistant frame stays false until that workstream replaces it.
   */
  releaseReady: boolean;
  /** Name shown in the product-window chrome. */
  frame?: string;
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

const recordNote = "Figures in the capture are stored Harbor & Co. records.";
/**
 * Held off the site until the redesigned workspace is captured.
 * The files on disk are an earlier pass and are not the release set.
 */
const harbor = { width: 1440, height: 900, releaseReady: false, frame: "Harbor & Co." } as const;

export const captures = {
  overview: {
    src: "/portfolio/01-overview.png",
    title: "Overview",
    alt: "ATLAS overview for Harbor & Co., with company, lead, inquiry, and approval counts from stored records.",
    caption: `Overview for the fictional Harbor & Co. workspace. ${recordNote}`,
    ...harbor,
  },
  crm: {
    src: "/portfolio/02-crm.png",
    title: "CRM",
    alt: "ATLAS CRM company list for Harbor & Co., including Brine & Barrel, Lumen Freight, and Harbor & Co.",
    caption: "Companies for one organization. Harbor & Co. is fictional, and the rows are stored CRM records.",
    ...harbor,
  },
  inbox: {
    src: "/portfolio/14-inbox.png",
    title: "Inbox",
    alt: "ATLAS inbox thread from Mina Patel about cold storage at the north pier, with an unsent reply draft.",
    caption: "One inbox thread for Harbor & Co. The reply on screen is a draft. Nothing in this capture was sent.",
    ...harbor,
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
    alt: "ATLAS knowledge library for Harbor & Co., with the bonded warehousing note marked ready.",
    caption: "Service notes are stored for Harbor & Co. Search uses those files. A paid embedding service is not called.",
    ...harbor,
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
    alt: "ATLAS workflow canvas for a qualified-lead follow-up, with a matching path and an otherwise path.",
    caption: "The qualified-lead workflow is inactive in the demonstration. The canvas shows both paths. A preview saves nothing.",
    ...harbor,
  },
  analytics: {
    src: "/portfolio/08-analytics.png",
    title: "Analytics",
    alt: "ATLAS analytics for Harbor & Co. showing 20 companies, 50 leads, and 40 open inquiries from stored rows.",
    caption: "Analytics reads stored rows for the selected period. Amounts in different currencies are not added together.",
    ...harbor,
  },
  integrations: {
    src: "/portfolio/15-integrations.png",
    title: "Integrations",
    alt: "ATLAS integrations for the Harbor & Co. demonstration, with simulated email and calendar and no live connections.",
    caption: "The demonstration lists supported services. Simulated and not-connected states are labeled. No live provider is called.",
    ...harbor,
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
 * Product surfaces to photograph at 1440×900 after the redesigned workspace
 * is the one on screen. Earlier files stay off the site.
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
  captures.inbox,
  captures.knowledge,
  captures.assistant,
  captures.workflows,
  captures.analytics,
  captures.integrations,
];

export const capabilities = [
  {
    title: "One tenant boundary",
    body: "Companies, documents, conversations, and approvals stay on the membership. A second organization, Northwind in the local seed, is not listed with Atlas Demo.",
  },
  {
    title: "A cited answer, or a refusal",
    body: "The assistant searches this organization's documents and CRM, then keeps a passage only when it contains the requested fact. When nothing qualifies, it stores a refusal and does not call the model.",
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
 * Measured on 26 November 2026 after the answerable pipeline was frozen.
 * Plover Dock is the fresh set. Orry Beacon was scored later and was not
 * used to change the rules. Neither corpus is Harbor & Co.
 */
export const retrievalComparison = {
  recordedOn: "26 November 2026",
  pipeline: "answerable",
  ploverQuestions: 45,
  orryQuestions: 26,
  publicInference: false,
  rows: [
    { measure: "Recall@5", plover: "0.9286", orry: "0.8056", target: "0.85" },
    { measure: "Abstention accuracy", plover: "0.8000", orry: "1.0000", target: "0.90" },
    { measure: "Factual correctness", plover: "0.7143", orry: "0.5000", target: "0.85" },
    { measure: "Citation correctness", plover: "0.7273", orry: "0.7222", target: "—" },
    { measure: "Mean retrieval latency", plover: "10.81 ms", orry: "11.62 ms", target: "—" },
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
