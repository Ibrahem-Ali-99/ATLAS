import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Case study",
  description:
    "How ATLAS keeps tenant data, retrieval, and external actions behind membership checks and human approval.",
};

export default function CaseStudyPage() {
  return (
    <article className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
      <p className="text-sm font-medium uppercase tracking-[0.16em] text-primary">Technical case study</p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight text-balance">
        A workspace where the model can read, and a person still decides.
      </h1>
      <p className="mt-4 text-lg leading-8 text-muted-foreground">
        Harbor & Co. is fictional. The operational problem is not. A team keeps inquiries in a mailbox, company facts in a shared drive, and follow-up in a CRM that people update differently. A draft is useful when it is tied to the right customer and when a person still chooses what gets written, booked, or changed.
      </p>

      <Section title="Business problem">
        <p>
          The system has to keep one organization&apos;s documents and CRM rows away from another, let a model read them, and stop before an email, a booking, or a CRM change. It also has to run as one API, one web app, and PostgreSQL, with n8n outside the process when an operator configures it.
        </p>
      </Section>

      <Section title="Product capabilities">
        <ul className="grid gap-2">
          <li>Identity uses Argon2 passwords, HttpOnly server-backed sessions, CSRF, tenant roles, invitations, and email password reset.</li>
          <li>CRM covers companies, contacts, leads, inquiries, opportunities, and tasks. Inbox covers signed email, WhatsApp, and website chat, with assignment and handoff.</li>
          <li>Knowledge ingests PDF and text, then the assistant answers with citations or a stored refusal. Conversations belong to the user who created them.</li>
          <li>Inquiry runs propose actions and pause. An administrator approves or rejects. Execute writes the stored payload, or does nothing if that payload changed.</li>
          <li>Workflows are a visual definition with all or any conditions, two ordered paths, manual runs, human review, activation, pause, and run inspection.</li>
          <li>Campaigns use segments, consent, suppression, a pinned transport, unsubscribe links, and recipient-level delivery feedback.</li>
          <li>Billing has a Free plan and Stripe test prices for Starter, Pro, and Business. Entitlements follow a confirmed provider event.</li>
        </ul>
      </Section>

      <Section title="System architecture">
        <p>
          The web client is Next.js App Router, React, TypeScript, Tailwind, Radix UI, and TanStack Query. The API is a Python 3.12 FastAPI modular monolith using Pydantic, SQLAlchemy, Alembic, PostgreSQL, and pgvector. LangGraph coordinates inquiry processing. Domain code owns the business rules. Routes validate the contract and call the service. A read-only MCP process supplies scoped CRM and knowledge context.
        </p>
        <Flow
          steps={["Browser", "Next.js", "FastAPI", "PostgreSQL"]}
          note="The API also reaches sandbox SMTP and, when configured, n8n. Workers for ingestion, workflows, and recovery run inside the API process."
        />
      </Section>

      <Section title="Engineering decisions">
        <p>
          External side effects wait for a person. The model does not approve itself and does not choose the organization. Failed logins share one error and are limited inside the process. A public demo cannot hold a paid model key, live email, or an n8n URL. Seeding resets development passwords, so it does not run in production or in that demo. Provider keys that are empty fail closed. The deterministic provider is a stand-in for tests and a public demo, not a measure of a hosted model.
        </p>
      </Section>

      <Section title="Intelligent retrieval">
        <p>
          Documents are chunked with page numbers when the extractor provides them. Embeddings are stored at 1536 or 768 dimensions, matching the configured model. Search uses cosine distance plus Postgres full text, and it only returns chunks from the caller&apos;s organization. The default maximum cosine distance is 0.55. A neighbor becomes model context when it shares a content word with the query, or when a vector-only neighbor is at or below distance 0.45. Rank alone does not put a neighbor into that context.
        </p>
        <p>
          A stored citation is chosen from the answer text: a row that contains a number, code, email, or distinctive word the answer states. The model does not choose the stored ids. A specific fact that appears in none of the supplied rows is replaced, in the stored message, with a sentence that the fact could not be confirmed. When retrieved rows are present, the server checks the completed draft before the client renders it. If neither documents nor CRM records match, the assistant stores a refusal and does not call the model.
        </p>
      </Section>

      <Section title="Workflow execution">
        <Flow
          steps={["Inquiry", "LangGraph", "MCP reads", "Stored proposal", "Admin decision", "CRM or sandbox action"]}
          note="MCP tools are find_contact, get_lead, and search_company_knowledge. They do not accept an organization id and they do not write."
        />
        <p>
          A lead create or update commits the CRM row and the executed approval in one transaction. A customer response or appointment first stores an execution intent with a stable idempotency key. One worker claims it. Sandbox SMTP uses the local mailbox. A timeout becomes needs attention and is not sent again. A refused connection can be tried twice. The calendar adapter in simulation mode writes a booking row and no provider event id. This is at-least-once delivery with reconciliation. It is not an exactly-once guarantee.
        </p>
        <p>
          Visual definitions can match all or any conditions and then follow the matching path or the otherwise path. The selected branch is stored before approval. A manual request cannot be reused for a different record. n8n receives a signed webhook only after the approval point for the lead path, and a missing callback stays visible until it arrives.
        </p>
      </Section>

      <Section title="External integrations">
        <p>
          Workspace credentials are encrypted. Connection tests and disconnect are explicit. Google Calendar uses session-bound single-use state and PKCE, checks availability again at execution, and records the owning calendar so cancellation targets that event. WhatsApp verifies signed inbound messages. Approved outbound replies use a separate live gate. Resend can record delivery, bounce, and complaint, with suppression on bounce and complaint. Stripe checkout does not change entitlements until the webhook confirms the subscription. Webhook signing secrets are sealed and returned once.
        </p>
      </Section>

      <Section title="Multi-tenant security">
        <p>
          A session cookie identifies the user. Organization access is loaded from memberships. Roles are admin and staff. Mutations other than login require the CSRF token issued for that server session. Retrieval, CRM, knowledge, assistant, agent, and approval routes require the membership. Approving or rejecting requires admin. Uploaded documents, retrieved passages, and model output are treated as data, not as instructions to execute.
        </p>
        <p>
          Record origin is operational, demo, evaluation, or unknown, stored on the row. An organization is not itself one of those kinds. Analytics and several lists default to operational rows. The local seed writes new demonstration rows as demo.
        </p>
      </Section>

      <Section title="Testing and reliability">
        <p>
          API tests cover tenant isolation, CSRF, approval integrity, webhook authentication, ingestion recovery, and the rule that an uncertain email is not sent twice. Browser acceptance walks CRM, knowledge, the assistant, an agent run, one executed approval, and one rejection. That browser path uses the deterministic providers. Login limits default to 8 failures per email and 40 per direct client address inside 15 minutes. Webhook limits default to 30 requests per minute for each integration key. Both counters live in the API process that received the request.
        </p>
        <p>
          Lead scoring trains on a documented synthetic set. A stored prediction is advisory. It does not change the lead, create an approval, or authorize an external action. The score is not a measurement of real conversion.
        </p>
      </Section>

      <Section title="Release evidence">
        <p>
          On 26 November 2026 the working tree that included b71d0de and the qualification fixes in 44631e1 was checked without restarting the shared API or web app. The API suite passed 284 tests, skipped 1, and failed 0. The skip does not call Groq or Ollama. The browser suite passed 37 tests, skipped 2, and failed 0. Those skips are design screenshots and the Resend transport settings test. Frontend unit tests passed 12. TypeScript and the production build passed.
        </p>
        <p>
          The runs used atlas_test and a disposable atlas_e2e database, sandbox billing, and sandbox mail. They did not send a message or create a charge. Alembic had one head, 20261126_0055. Stripe test-mode checkout, the portal, upgrade, downgrade, cancellation, a declined card, and a failed renewal were recorded earlier that day and were not repeated. The tree also held uncommitted demo and deployment files, so these counts are not a clean checkout of 44631e1.
        </p>
      </Section>

      <Section title="Deployment">
        <p>
          Production is one API process and one Next.js app behind one browser origin, because the session cookie is HttpOnly and SameSite=Lax and CSRF expects the browser to call the API that issued the token. PostgreSQL with pgvector holds the rows. Uploads live on a persistent disk. Staging HTTPS is served by Caddy. Migrations run before traffic. A second API process would recover the same rows, so ingestion and workflow recovery stay in the one API process.
        </p>
        <p>
          A shared demo sets the public-demo flag. The process then refuses to start with a paid model key, live email, or an n8n webhook URL. Anonymous requests still need a session. The portfolio demo command prepares fictional rows in a separate database named atlas_portfolio and refuses the development database.
        </p>
      </Section>

      <Section title="Limits">
        <p>
          Login limits and webhook limits are not shared across processes. Rotating the session secret signs everyone out and retires sealed webhook secrets. Exactly-once delivery to n8n or SMTP is not promised. Direct edits made in Google Calendar are not imported. This write-up is not a penetration test or a compliance certificate. Live provider accounts and a public URL are operator concerns and are not claimed as completed by this page.
        </p>
      </Section>
    </article>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = title.toLowerCase().replaceAll(" ", "-");
  return (
    <section className="mt-10" aria-labelledby={id}>
      <h2 id={id} className="text-2xl font-semibold tracking-tight">{title}</h2>
      <div className="mt-3 grid gap-3 text-[15px] leading-7 text-muted-foreground">{children}</div>
    </section>
  );
}

function Flow({ steps, note }: { steps: string[]; note: string }) {
  return (
    <div className="my-4">
      <ol className="flex flex-wrap items-center gap-2">
        {steps.map((step, index) => (
          <li key={step} className="flex items-center gap-2">
            <span className="rounded-full border border-border bg-card px-3 py-1 text-sm text-foreground">{step}</span>
            {index < steps.length - 1 ? <span aria-hidden="true" className="text-muted-foreground">→</span> : null}
          </li>
        ))}
      </ol>
      <p className="mt-3">{note}</p>
    </div>
  );
}
