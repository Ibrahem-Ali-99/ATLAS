import Link from "next/link";
import type { ReactNode } from "react";

import { LaunchDemoButton } from "@/components/public/launch-demo-button";
import { PricingPlans } from "@/components/public/pricing-plans";
import { ProductWindow } from "@/components/public/product-shot";
import { Button } from "@/components/ui/button";
import {
  architectureSteps,
  capabilities,
  captures,
  evaluationEvidence,
  homepageStages,
  integrationGroups,
  isReleaseCapture,
  reportingRules,
  useCases,
  type ProductCapture,
} from "@/lib/public-site";

export function HomeScreen() {
  return (
    <div>
      <section className="relative overflow-hidden">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-70 [background-image:linear-gradient(to_right,var(--border)_1px,transparent_1px),linear-gradient(to_bottom,var(--border)_1px,transparent_1px)] [background-size:4.5rem_4.5rem] [mask-image:radial-gradient(ellipse_at_70%_20%,black,transparent_72%)]"
        />
        <div className="relative mx-auto grid max-w-7xl items-center gap-14 px-5 py-16 sm:px-8 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] lg:gap-16 lg:py-24">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Operations workspace</p>
            <h1 className="mt-4 max-w-xl text-4xl font-semibold tracking-[-0.03em] text-balance sm:text-5xl sm:leading-[1.08] lg:text-[3.25rem]">
              Know the customer. Cite the record. Approve the next step.
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-muted-foreground">
              ATLAS is the workspace for one organization&apos;s CRM, inbox, documents, and automation. The assistant answers from those records. A message, a booking, or a CRM change waits until an administrator approves it.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <LaunchDemoButton size="lg" />
              <Button asChild size="lg" variant="outline">
                <Link href="/demo">View the tour</Link>
              </Button>
            </div>
          </div>
          <ReleaseShot capture={homepageStages.hero} priority fallback={<DecisionRail />} />
        </div>
      </section>

      <section id="product" className="border-t border-border">
        <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
          <SectionHeading
            eyebrow="Product"
            title="Built for a team that still decides."
            body="One API and one web app serve every organization. The organization id in a URL is a lookup key. The server loads the membership for the signed-in user. On a narrow screen the same routes collapse into a drawer."
          />
          <div className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {capabilities.map((item, index) => (
              <article key={item.title} className="rounded-2xl border border-border bg-card p-6">
                <p className="text-xs font-semibold tracking-[0.16em] text-primary">{String(index + 1).padStart(2, "0")}</p>
                <h3 className="mt-4 text-lg font-semibold tracking-tight">{item.title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-border bg-card">
        <div className="mx-auto grid max-w-7xl items-start gap-10 px-5 py-20 sm:px-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] lg:gap-16 lg:py-24">
          <div>
            <SectionHeading
              eyebrow="Interactive demo"
              title="Open a private Harbor & Co. workspace."
              body="Harbor & Co. is fictional. Launch starts a short-lived organization for this browser. It expires after 45 minutes, restart replaces it, and it is not the development workspace. No password is published."
            />
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <LaunchDemoButton size="lg" />
              <Button asChild size="lg" variant="outline">
                <Link href="/demo">Read the session rules</Link>
              </Button>
            </div>
          </div>
          <ul className="grid gap-3">
            {[
              "The assistant and document search use a deterministic stand-in. A paid model is not called.",
              "Integration credentials, billing, invitations, outbound messages, and live provider calls are refused.",
              "Each session is limited to 400 requests, 12 assistant replies, 3 documents, and 500 KB of knowledge files.",
            ].map((item) => (
              <li key={item} className="rounded-2xl border border-border bg-background px-5 py-4 text-sm leading-6">
                {item}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <Feature
        id="inbox"
        eyebrow="Inbox"
        title="Email, chat, and WhatsApp in one queue."
        body="A thread keeps the customer, the company, and the draft together. Sending still waits for approval. The capture shows a Harbor & Co. conversation that has not left the workspace."
        capture={captures.inbox}
        fallback={null}
      />

      <Feature
        id="knowledge"
        eyebrow="Knowledge"
        title="The library the assistant is allowed to read."
        body="PDF and text files are stored, chunked, and embedded for that organization. In the demonstration those files are short service notes, and search does not call a paid embedding service."
        capture={captures.knowledge}
        fallback={null}
        flip
      />

      <Feature
        id="assistant"
        eyebrow="Intelligent assistant"
        title="Answers stay tied to the records you uploaded."
        body="PDF and text files are stored, chunked, and embedded for that organization. Hybrid search returns neighbors inside the distance limit. Conversation history remains with the person who started it."
        capture={homepageStages.assistant}
        fallback={<RetrievalRules />}
      />

      <section id="crm" className="border-t border-border bg-card">
        <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
          <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
            <SectionHeading
              eyebrow="CRM"
              title="The account is a stored record."
              body="Companies, contacts, leads, inquiries, opportunities, and tasks stay on the organization. Harbor & Co. is fictional. The list in the picture is the seeded workspace, not a hardcoded total."
            />
            <ReleaseShot capture={captures.crm} fallback={null} />
          </div>
          <ol className="mt-16 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {useCases.map((item, index) => (
              <li key={item.title} className="rounded-2xl border border-border bg-background p-6">
                <p className="text-xs font-semibold tracking-[0.16em] text-primary">{String(index + 1).padStart(2, "0")}</p>
                <h3 className="mt-4 text-lg font-semibold tracking-tight">{item.title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <Feature
        id="workflows"
        eyebrow="Visual automation"
        title="A visual path, then a recorded run."
        body="Definitions support all or any conditions, a matching path, and an otherwise path. Runs can pause for review. Activation and pause are explicit. Sandbox email is delivered to the local mailbox. A simulated booking is a row in ATLAS, with no external event id, until Google Calendar is connected and an administrator approves the booking."
        capture={homepageStages.automation}
        fallback={<BranchDiagram />}
        flip
      />

      <section id="analytics" className="border-t border-border bg-card">
        <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
          <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
            <SectionHeading
              eyebrow="Analytics and reporting"
              title="Reports count what is already stored."
              body="Overview and analytics read the signed-in organization for the selected period. The picture is Harbor & Co. on one day. The rules below are what the product computes."
            />
            <ReleaseShot capture={captures.analytics} fallback={null} />
          </div>
          <div className="mt-16 grid gap-4 lg:grid-cols-3">
            {reportingRules.map((item) => (
              <article key={item.title} className="rounded-2xl border border-border bg-background p-6">
                <h3 className="text-lg font-semibold tracking-tight">{item.title}</h3>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">{item.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="integrations" className="border-t border-border">
        <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
          <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16 lg:[&>*:first-child]:order-2">
            <SectionHeading
              eyebrow="Integrations"
              title="The connections the product actually ships."
              body="Credentials stay encrypted in the workspace. A public demo refuses a paid model key, live email, and an n8n URL. Empty provider keys fail closed. The picture labels each service as simulated or not connected."
            />
            <ReleaseShot capture={captures.integrations} fallback={null} />
          </div>
          <div className="mt-16 grid gap-10 lg:grid-cols-3">
            {integrationGroups.map((group) => (
              <div key={group.name}>
                <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">{group.name}</h3>
                <ul className="mt-4 grid gap-3">
                  {group.items.map((item) => (
                    <li key={item.name} className="rounded-2xl border border-border bg-card p-5">
                      <h4 className="font-semibold tracking-tight">{item.name}</h4>
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.detail}</p>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="architecture" className="border-t border-border bg-card">
        <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
          <div className="max-w-3xl">
            <SectionHeading
              eyebrow="Architecture"
              title="One API, one web app, and a person at the gate."
              body="The client is Next.js. The API is a FastAPI modular monolith on PostgreSQL and pgvector. LangGraph coordinates inquiry processing. Domain services own the rules. A read-only MCP process can supply scoped CRM and knowledge context."
            />
            <ol className="mt-8 flex flex-wrap items-center gap-2" aria-label="Request path">
              {architectureSteps.map((step, index) => (
                <li key={step} className="flex items-center gap-2">
                  <span className="rounded-full border border-border bg-background px-3 py-1.5 text-sm font-medium">{step}</span>
                  {index < architectureSteps.length - 1 ? <span aria-hidden="true" className="text-muted-foreground">→</span> : null}
                </li>
              ))}
            </ol>
            <p className="mt-4 text-sm leading-6 text-muted-foreground">
              The API also reaches sandbox SMTP and, when a webhook URL is configured, n8n. Ingestion and workflow recovery stay in the one API process.
            </p>
            <div className="mt-6">
              <Button asChild variant="outline">
                <Link href="/case-study">Read the engineering case study</Link>
              </Button>
            </div>
          </div>
        </div>
      </section>

      <section id="evidence" className="border-t border-border">
        <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
          <SectionHeading
            eyebrow="Evaluation"
            title={`Suite results from ${evaluationEvidence.checkedOn}.`}
            body="These are test counts from that working tree. They are not customer totals, revenue, or a claim that a live message or a live charge was sent."
          />
          <dl className="mt-12 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Evidence term="API" value={`${evaluationEvidence.api.passed} passed`} detail={`${evaluationEvidence.api.skipped} skipped, ${evaluationEvidence.api.failed} failed. The skip does not call Groq or Ollama.`} />
            <Evidence term="Browser" value={`${evaluationEvidence.browser.passed} passed`} detail={`${evaluationEvidence.browser.skipped} skipped, ${evaluationEvidence.browser.failed} failed. The skips are design screenshots and the Resend transport settings test.`} />
            <Evidence term="Frontend unit tests" value={`${evaluationEvidence.frontend.passed} passed`} detail={`${evaluationEvidence.frontend.failed} failed.`} />
            <Evidence term="TypeScript and build" value={evaluationEvidence.buildPassed ? "Passed" : "Not recorded"} detail={`Alembic head ${evaluationEvidence.alembicHead}.`} />
          </dl>
          <p className="mt-8 max-w-3xl text-sm leading-6 text-muted-foreground">{evaluationEvidence.caveat}</p>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">
            The case study records the answerable retrieval pipeline on Plover Dock and Orry Beacon. Plover recall cleared its target. Abstention and factual correctness did not. Public inference stays off. Product images wait for the redesigned workspace.
          </p>
        </div>
      </section>

      <section id="pricing" className="border-t border-border">
        <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
          <SectionHeading
            eyebrow="Pricing"
            title="Prices and limits from the billing catalog."
            body="Free, Starter, Pro, and Business use the limits stored with the plans. Paid amounts are the Stripe test prices: Starter $19 or $190, Pro $49 or $490, Business $99 or $990."
          />
          <div className="mt-12">
            <PricingPlans />
          </div>
        </div>
      </section>

      <section className="border-t border-border">
        <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
          <div className="rounded-3xl border border-border bg-card px-6 py-12 sm:px-12 lg:flex lg:items-end lg:justify-between lg:gap-12">
            <div className="max-w-xl">
              <h2 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">See the workspace decide, then stop.</h2>
              <p className="mt-4 text-lg leading-8 text-muted-foreground">
                Launch opens Harbor & Co. in the application. The session stays on this browser, and the development workspace stays separate.
              </p>
            </div>
            <div className="mt-8 lg:mt-0">
              <LaunchDemoButton size="lg" />
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function SectionHeading({ eyebrow, title, body }: { eyebrow: string; title: string; body: string }) {
  return (
    <div className="max-w-2xl">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-balance sm:text-4xl sm:leading-tight">{title}</h2>
      <p className="mt-4 text-base leading-7 text-muted-foreground">{body}</p>
    </div>
  );
}

function Evidence({ term, value, detail }: { term: string; value: string; detail: string }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-6">
      <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">{term}</dt>
      <dd className="mt-3 text-3xl font-semibold tracking-tight">{value}</dd>
      <dd className="mt-2 text-sm leading-6 text-muted-foreground">{detail}</dd>
    </div>
  );
}

function ReleaseShot({
  capture,
  priority = false,
  fallback,
}: {
  capture: ProductCapture;
  priority?: boolean;
  fallback: ReactNode;
}) {
  if (!isReleaseCapture(capture)) return fallback;
  return <ProductWindow capture={capture} priority={priority} />;
}

function DecisionRail() {
  const steps = [
    ["A message arrives", "Email, WhatsApp, and website chat open one Inbox thread for the organization."],
    ["The answer cites a row", "Or the assistant stores a refusal and does not call the model."],
    ["A person approves", "Execute writes the stored payload. If that payload changed, it does nothing."],
  ] as const;
  return (
    <ol className="rounded-2xl border border-border bg-card p-6 shadow-[0_32px_80px_-48px_rgba(23,25,29,0.35)] sm:p-8">
      {steps.map(([title, body], index) => (
        <li key={title} className="relative grid grid-cols-[2.75rem_minmax(0,1fr)] gap-4 pb-8 last:pb-0">
          {index < steps.length - 1 ? <span aria-hidden="true" className="absolute bottom-0 left-[1.2rem] top-10 w-px bg-border" /> : null}
          <span className="relative grid size-10 place-items-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">{index + 1}</span>
          <div className="pt-1">
            <p className="text-lg font-semibold tracking-tight">{title}</p>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">{body}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

function RetrievalRules() {
  const rules = [
    ["Distance limit", "The default maximum cosine distance is 0.55."],
    ["Shared wording", "A neighbor becomes context when it shares a content word, or when a vector-only neighbor is at or below 0.45."],
    ["Refusal", "When nothing matches, the assistant stores a refusal and does not call the model."],
  ] as const;
  return (
    <ul className="grid gap-3">
      {rules.map(([title, body]) => (
        <li key={title} className="rounded-2xl border border-border bg-card p-5">
          <p className="font-semibold tracking-tight">{title}</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{body}</p>
        </li>
      ))}
    </ul>
  );
}

function BranchDiagram() {
  return (
    <div className="rounded-2xl border border-border bg-card p-6 sm:p-8">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">How a definition runs</p>
      <p className="mt-4 rounded-xl border border-border bg-background px-4 py-3 text-sm font-medium">Trigger · lead created</p>
      <p className="mx-auto mt-2 h-4 w-px bg-border" aria-hidden="true" />
      <p className="rounded-xl border border-border bg-background px-4 py-3 text-sm font-medium">Condition · all matches, or any match</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-border bg-background p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Matching path</p>
          <p className="mt-2 text-sm leading-6">Approval, then the task. The branch is stored first.</p>
        </div>
        <div className="rounded-xl border border-border bg-background p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Otherwise path</p>
          <p className="mt-2 text-sm leading-6">The other task. A preview of either path saves nothing.</p>
        </div>
      </div>
    </div>
  );
}

function Feature({
  id,
  eyebrow,
  title,
  body,
  capture,
  fallback,
  flip = false,
}: {
  id: string;
  eyebrow: string;
  title: string;
  body: string;
  capture: ProductCapture;
  fallback: ReactNode;
  flip?: boolean;
}) {
  return (
    <section id={id} className="border-t border-border">
      <div className={`mx-auto grid max-w-7xl items-center gap-12 px-5 py-20 sm:px-8 lg:grid-cols-2 lg:gap-16 lg:py-24 ${flip ? "lg:[&>*:first-child]:order-2" : ""}`}>
        <div>
          <SectionHeading eyebrow={eyebrow} title={title} body={body} />
        </div>
        <ReleaseShot capture={capture} fallback={fallback} />
      </div>
    </section>
  );
}
