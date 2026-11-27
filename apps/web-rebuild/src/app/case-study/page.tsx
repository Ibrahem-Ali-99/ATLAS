import type { Metadata } from "next";

import { SiteFrame } from "@/presentation/site-frame";

export const metadata: Metadata = {
  title: "Case study · ATLAS",
  description:
    "How ATLAS isolates a tenant, retrieves from that tenant's records, and stops before an external action.",
};

const measures = [
  ["Recall@5", "0.9286", "0.8056", "0.85"],
  ["Abstention accuracy", "0.8000", "1.0000", "0.90"],
  ["Factual correctness", "0.7143", "0.5000", "0.85"],
  ["Citation correctness", "0.7273", "0.7222", "—"],
  ["Mean retrieval latency", "10.81 ms", "11.62 ms", "—"],
];

export default function CaseStudyPage() {
  return (
    <SiteFrame>
      <article className="site-prose">
        <p className="site-kicker">Technical case study</p>
        <h1>A workspace where the model can read, and a person still decides.</h1>
        <p>
          Harbor & Co. is fictional. The operational problem is not. A team keeps inquiries in a mailbox, company facts in a shared drive, and follow-up in a CRM that people update differently. A draft is useful when it is tied to the right customer and when a person still chooses what gets written, booked, or changed.
        </p>

        <h2>Business problem</h2>
        <p>
          The system has to keep one organization&apos;s documents and CRM rows away from another, let a model read them, and stop before an email, a booking, or a CRM change. It runs as one API, one web app, and PostgreSQL. n8n stays outside the process and is called only when an operator configures it.
        </p>

        <h2>The interface this site shows</h2>
        <p>
          The public portfolio serves the replacement client in <code>apps/web-rebuild</code>. The pictures are viewport captures of that client signed into the Harbor & Co. workspace, reading stored rows. The earlier client in <code>apps/web</code> remains the application on the development ports. The public Compose file builds the replacement client. It does not build both.
        </p>

        <h2>Product capabilities</h2>
        <ul>
          <li>Identity uses Argon2 passwords, HttpOnly server-backed sessions, CSRF, tenant roles, invitations, and email password reset.</li>
          <li>CRM covers companies, contacts, leads, inquiries, opportunities, and tasks. Inbox covers signed email, WhatsApp, and website chat, with assignment and handoff.</li>
          <li>Knowledge ingests PDF and text. The assistant answers with citations or a stored refusal. Conversations belong to the user who created them.</li>
          <li>Inquiry runs propose actions and pause. An administrator approves or rejects. Execute writes the stored payload, or does nothing if that payload changed.</li>
          <li>Workflows are a visual definition with all or any conditions, two ordered paths, manual runs, human review, activation, pause, and run inspection.</li>
          <li>Campaigns use segments, consent, suppression, a pinned transport, unsubscribe links, and recipient-level delivery feedback.</li>
          <li>Billing has a Free plan and Stripe test prices for Starter ($19 monthly or $190 yearly), Pro ($49 or $490), and Business ($99 or $990). Entitlements follow a confirmed provider event.</li>
        </ul>

        <h2>System architecture</h2>
        <p>
          The public client is Next.js 16, React, and TypeScript. The API is a Python 3.12 FastAPI modular monolith using Pydantic, SQLAlchemy, Alembic, PostgreSQL, and pgvector. LangGraph coordinates inquiry processing. Domain services own the business rules. Routes validate the contract and call the service. A read-only MCP process supplies scoped CRM and knowledge context. Ingestion, workflow recovery, and the public model budget live in the one API process.
        </p>
        <ol className="site-flow">
          <li>Browser</li>
          <li>Next.js</li>
          <li>FastAPI</li>
          <li>PostgreSQL</li>
        </ol>
        <p>The API also reaches sandbox SMTP. It reaches n8n only when a webhook URL is configured. A public demo leaves that URL empty, so the process refuses to start if one is added.</p>

        <h2>Engineering decisions</h2>
        <p>
          External side effects wait for a person. The model does not approve itself and does not choose the organization. Failed logins share one error and are limited inside the process. A public demo cannot hold a paid model key, live email, or an n8n URL. Seeding resets development passwords, so it does not run in production or on the serving demo process. Provider keys that are empty fail closed. The deterministic provider remains the stand-in for tests and for visitor document search. It is not a measure of a hosted model.
        </p>
        <p>
          The public records are written only by <code>python -m app.scripts.portfolio_demo</code>, only into a database named <code>atlas_portfolio</code>, and only from a one-off process with the public-demo flag off. That command refuses the development database and the private Harbor database.
        </p>

        <h2>Intelligent retrieval</h2>
        <p>
          Documents are chunked at 800 characters with 100 characters of overlap. Page numbers are kept when the extractor provides them. Embeddings are stored at 1536 or 768 dimensions, matching the configured model. Search stays inside the caller&apos;s organization.
        </p>
        <p>
          The assistant default is the answerable pipeline. Candidate search is an AND full-text query, an OR full-text query, and vector neighbors inside the cosine cutoff, fused by reciprocal rank. A second stage keeps a passage only when the question&apos;s rare constraints occur together as positive mentions and the passage has the kind of fact asked for. A negated mention does not count. The 0.45 and 0.55 distance gates were not moved. Dense neighbors inside 0.45 are candidates, not answers.
        </p>
        <p>
          A stored citation is a row that contains a number, code, email, or distinctive word the answer states. The model does not choose the stored ids. <code>80000</code> and <code>80,000</code> are the same figure. <code>9</code> and <code>09</code> are the same clock component. <code>19</code> is not accepted as <code>9</code>. A specific fact that appears in none of the supplied rows is replaced, in the stored message, with a sentence that the fact could not be confirmed. If neither documents nor CRM records qualify, the assistant stores a refusal and does not call the model.
        </p>

        <h2>Public model replies</h2>
        <p>
          The switch <code>ATLAS_PUBLIC_INFERENCE_ENABLED</code> defaults to off. A signed-in workspace that is not a visitor organization does not use the public budget. When the switch is on, a visitor Assistant turn and the website widget may call the process chat model. The portfolio stack points that model at Ollama on the private Compose network, with an empty API key. A paid key still prevents the process from starting. A non-visitor on that same process cannot obtain the chat client: the public-demo rule blocks every provider other than the deterministic stand-in for ordinary workspaces.
        </p>
        <p>
          An empty key is accepted only when the caller is that visitor path and the base URL host is <code>ollama</code>, loopback, or <code>host.docker.internal</code>. A keyless call to a public model host is refused. Visitor document search keeps the deterministic embedding client, so a public question does not call a paid embedding API. The portfolio environment stays <code>development</code> because production rejects that embedding stand-in. Caddy answers <code>/docs</code>, <code>/openapi.json</code>, and <code>/redoc</code> with 404.
        </p>
        <ul>
          <li>8 replies per session and 200 replies for the process, inside a one-hour window. Both counters reset when the API process restarts. A second API container would not share them.</li>
          <li>At least 2 seconds between replies, at most 2 replies in flight, and 256 output tokens.</li>
          <li>Input longer than 2,000 characters is refused. A repeated character run, a null byte, more than three links, or a prompt-injection pattern is rejected before the model is called.</li>
          <li>Login is limited to 5 failures per email and 120 per direct client address in 15 minutes. Demo launches are limited to 8 per direct client address in 15 minutes, and to 40 active visitor organizations. A client-supplied forwarded address does not open another bucket.</li>
        </ul>

        <h2>Retrieval evaluation</h2>
        <p>
          Recorded on 26 November 2026 after the answerable stage was frozen. The questions were not edited to raise these scores. Neither corpus is Harbor & Co. Both runs used hash embeddings and PostgreSQL full text on a disposable test database, and the rows were rolled back. Ranked metrics use K = 5. Generation used Groq <code>openai/gpt-oss-20b</code>. Plover Dock is 45 questions. Orry Beacon is 26 questions scored afterward. Plover recall cleared its target. Abstention and factual correctness did not. Orry abstained on every unsupported question, and its factual correctness was 0.50. Mean retrieval latency is the search itself and does not include the model call.
        </p>
        <div className="site-table-wrap">
          <table className="site-table">
            <caption className="sr-only">Plover Dock and Orry Beacon retrieval measures</caption>
            <thead>
              <tr>
                <th scope="col">Measure</th>
                <th scope="col">Plover Dock</th>
                <th scope="col">Orry Beacon</th>
                <th scope="col">Target</th>
              </tr>
            </thead>
            <tbody>
              {measures.map((row) => (
                <tr key={row[0]}>
                  {row.map((cell) => <td key={cell}>{cell}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h2>Inquiry agent and workflows</h2>
        <p>
          An inquiry run loads the inquiry, classifies it with the configured chat model, then calls three read-only tools: <code>search_company_knowledge</code>, <code>find_contact</code>, and <code>get_lead</code>. Those tools do not accept an organization id and they do not write. The run stores a lead proposal, a reply draft, and an appointment request, then pauses. The model has no approval tool.
        </p>
        <p>
          A lead create or update commits the CRM row and the executed approval in one transaction. A customer response or appointment first stores an execution intent with a stable idempotency key. One worker claims it. Sandbox SMTP uses the local mailbox. A timeout becomes needs attention and is not sent again. A refused connection can be tried twice. The calendar adapter in simulation mode writes a booking row and no provider event id. This is at-least-once delivery with reconciliation. It is not an exactly-once guarantee.
        </p>
        <p>
          Visual definitions can match all or any conditions and then follow the matching path or the otherwise path. The selected branch is stored before approval. A manual request cannot be reused for a different record. n8n receives a signed webhook only after the approval point for the lead path, and a missing callback stays visible until it arrives.
        </p>

        <h2>External integrations</h2>
        <p>
          Workspace credentials are encrypted. Connection tests and disconnect are explicit. Google Calendar uses session-bound single-use state and PKCE, checks availability again at execution, and records the owning calendar so cancellation targets that event. WhatsApp verifies signed inbound messages. Approved outbound replies use a separate live gate. Resend can record delivery, bounce, and complaint, with suppression on bounce and complaint. Stripe checkout does not change entitlements until the webhook confirms the subscription. Webhook signing secrets are sealed and returned once.
        </p>
        <p>
          The connected provider demonstration stays on the private Harbor database <code>atlas_harbor</code>. That process is not the public demo. It does not use the public-demo flag, and the public stack is not pointed at its database, its upload directory, or its password.
        </p>

        <h2>Multi-tenant security</h2>
        <p>
          A session cookie identifies the user. Organization access is loaded from memberships. Roles are admin and staff. Mutations other than login require the CSRF token issued for that server session. Retrieval, CRM, knowledge, assistant, agent, and approval routes require the membership. Approving or rejecting requires admin. Uploaded documents, retrieved passages, and model output are treated as data.
        </p>
        <p>
          A visitor organization is a separate tenant whose slug starts with <code>harbor-visitor-</code>. It cannot approve an external action. The seeded staff account on the portfolio database remains an operator login and is not published.
        </p>

        <h2>Testing and what this write-up is not</h2>
        <p>
          On 26 November 2026 a working tree that included the qualification fixes was checked without restarting the shared API or web app: API 284 passed, 1 skipped, 0 failed; browser 37 passed, 2 skipped, 0 failed; frontend unit tests 12 passed. The API skip does not call Groq or Ollama. The runs used disposable test databases, sandbox billing, and sandbox mail. They did not send a message or create a charge. The tree also held uncommitted files, so those counts are not a clean checkout. The clean command is <code>.\scripts\verify-release.ps1</code>. It had not been run on an empty tree when this page was written.
        </p>
        <p>
          This page is not a penetration test, a compliance certificate, or a customer testimonial. Exactly-once delivery to n8n or SMTP is not promised. Direct edits made in Google Calendar are not imported. Login limits and webhook limits are not shared across processes.
        </p>
      </article>
    </SiteFrame>
  );
}
