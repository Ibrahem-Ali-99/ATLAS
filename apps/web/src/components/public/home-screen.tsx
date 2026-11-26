import Link from "next/link";

import { LaunchDemoButton } from "@/components/public/launch-demo-button";
import { PricingPlans } from "@/components/public/pricing-plans";
import { ProductShot } from "@/components/public/product-shot";
import { Button } from "@/components/ui/button";
import { captures, integrations, useCases } from "@/lib/public-site";

export function HomeScreen() {
  return (
    <div className="motion-safe:animate-[atlas-rise_0.7s_ease-out]">
      <section className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[0.9fr_1.1fr] lg:py-24">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.16em] text-primary">Operations workspace</p>
          <h1 className="mt-4 max-w-xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl sm:leading-[1.08]">
            Customer work, company knowledge, and follow-up in one place.
          </h1>
          <p className="mt-5 max-w-xl text-lg leading-8 text-muted-foreground">
            ATLAS is an organization-scoped workspace for CRM, a multichannel inbox, document retrieval, and automation.
            A person approves a CRM change, a message, or a booking before it leaves the workspace.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <LaunchDemoButton size="lg" />
            <Button asChild size="lg" variant="outline">
              <Link href="/demo">View the tour</Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/#pricing">View pricing</Link>
            </Button>
            <Button asChild size="lg" variant="ghost">
              <Link href="/case-study">Read the case study</Link>
            </Button>
          </div>
        </div>
        <ProductShot {...fields(captures.overview)} priority />
      </section>

      <section id="product" className="border-t border-border bg-card">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 className="text-3xl font-semibold tracking-tight">Built for a team that still decides.</h2>
          <p className="mt-3 max-w-2xl text-muted-foreground">
            One API and one web app serve every organization. The organization id in a URL is a lookup key.
            The server loads the membership for the signed-in user.
          </p>
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            <Position
              title="One tenant boundary"
              body="Companies, documents, conversations, and approvals stay inside the organization on the membership. A second organization, Northwind in the local seed, is not listed with Atlas Demo."
            />
            <Position
              title="Evidence before an answer"
              body="Retrieval mixes vector distance and full text, then keeps a passage when it shares wording with the question. A stored citation is a row the answer actually uses."
            />
            <Position
              title="Approval before a side effect"
              body="The agent proposes a lead change, a reply, and an appointment. An administrator approves the stored payload. If that payload changes, execute does nothing."
            />
          </div>
        </div>
      </section>

      <Feature
        id="assistant"
        eyebrow="Assistant and knowledge"
        title="Answers stay tied to the records you uploaded."
        body="PDF and text files are stored, chunked, and embedded for that organization. Hybrid search returns neighbors inside the distance limit. When no document or CRM row matches, the assistant stores a refusal and does not call the model. Conversation history remains with the person who started it."
        shot={captures.assistant}
        aside={captures.knowledge}
      />

      <Feature
        id="crm"
        eyebrow="CRM and inbox"
        title="The thread and the account are the same customer."
        body="Companies, contacts, leads, inquiries, opportunities, and tasks live in the CRM. Inbox keeps email, WhatsApp, and website chat in one queue, with assignment and handoff. Staff can create a lead and an inquiry from a conversation. Archiving hides a thread and keeps its messages."
        shot={captures.crm}
        aside={captures.lead}
        flip
      />

      <Feature
        id="workflows"
        eyebrow="Workflow automation"
        title="A visual path, then a recorded run."
        body="Definitions support all or any conditions, a matching path, and an otherwise path. Runs can pause for review. Activation and pause are explicit. Sandbox email is delivered to the local mailbox. A simulated booking is a row in ATLAS, with no external event id, until Google Calendar is connected and an administrator approves the booking."
        shot={captures.workflows}
        aside={captures.rejected}
      />

      <Feature
        id="analytics"
        eyebrow="Analytics and reporting"
        title="Reports count what is already stored."
        body="Overview and analytics read the signed-in organization. Conversion is won divided by won plus lost, and the rate stays empty when that denominator is zero. Monitoring shows worker heartbeats and historical failures. Demo, operational, evaluation, and legacy origins can be filtered because one tenant can hold more than one kind of record."
        shot={captures.analytics}
        aside={captures.monitoring}
        flip
      />

      <section className="border-t border-border">
        <div className="mx-auto grid max-w-6xl items-center gap-8 px-4 py-16 sm:px-6 lg:grid-cols-2">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.16em] text-primary">Mobile</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight">The workspace fits a narrow screen.</h2>
            <p className="mt-3 text-muted-foreground">
              Navigation collapses into a drawer. Inbox threads, settings sections, and approval details remain reachable without a separate mobile product.
            </p>
          </div>
          <ProductShot {...fields(captures.mobile)} />
        </div>
      </section>

      <section id="use-cases" className="border-t border-border bg-card">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 className="text-3xl font-semibold tracking-tight">A fictional logistics account, on the real product.</h2>
          <p className="mt-3 max-w-2xl text-muted-foreground">
            Harbor & Co. is not a customer. The path below is the one the application implements: intake, CRM, retrieval, approval, sandbox delivery, and stored analytics.
          </p>
          <ol className="mt-8 grid gap-4 md:grid-cols-2">
            {useCases.map((item, index) => (
              <li key={item.title} className="rounded-xl border border-border bg-background p-5">
                <p className="text-sm font-medium text-primary">{String(index + 1).padStart(2, "0")}</p>
                <h3 className="mt-2 text-lg font-semibold">{item.title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="integrations" className="border-t border-border">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 className="text-3xl font-semibold tracking-tight">Integrations the product actually ships.</h2>
          <p className="mt-3 max-w-2xl text-muted-foreground">
            Credentials stay encrypted in the workspace. A public demo refuses a paid model key, live email, and an n8n URL. Empty provider keys fail closed.
          </p>
          <ul className="mt-8 grid gap-4 sm:grid-cols-2">
            {integrations.map((item) => (
              <li key={item.name} className="rounded-xl border border-border bg-card p-5">
                <h3 className="font-semibold">{item.name}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.detail}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section id="pricing" className="border-t border-border bg-card">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 className="text-3xl font-semibold tracking-tight">Pricing from the billing catalog.</h2>
          <p className="mt-3 max-w-2xl text-muted-foreground">
            Free, Starter, Pro, and Business use the limits stored with the plans. Paid amounts are the Stripe test prices: Starter $19 or $190, Pro $49 or $490, Business $99 or $990.
          </p>
          <div className="mt-8">
            <PricingPlans />
          </div>
        </div>
      </section>

      <section className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col items-start gap-6 px-4 py-16 sm:px-6 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-3xl font-semibold tracking-tight">Open a private Harbor & Co. workspace.</h2>
            <p className="mt-3 max-w-xl text-muted-foreground">
              Launch starts a short-lived session in the application. Restart replaces that workspace. No password is published, and the development workspace stays separate.
            </p>
          </div>
          <LaunchDemoButton size="lg" />
        </div>
      </section>
    </div>
  );
}

function fields(capture: { src: string; alt: string; caption: string }) {
  return { src: capture.src, alt: capture.alt, caption: capture.caption };
}

function Position({ title, body }: { title: string; body: string }) {
  return (
    <article className="rounded-xl border border-border bg-background p-5">
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{body}</p>
    </article>
  );
}

function Feature({
  id,
  eyebrow,
  title,
  body,
  shot,
  aside,
  flip = false,
}: {
  id: string;
  eyebrow: string;
  title: string;
  body: string;
  shot: { src: string; alt: string; caption: string };
  aside: { src: string; alt: string; caption: string };
  flip?: boolean;
}) {
  return (
    <section id={id} className="border-t border-border">
      <div className={`mx-auto grid max-w-6xl items-center gap-8 px-4 py-16 sm:px-6 lg:grid-cols-2 ${flip ? "lg:[&>*:first-child]:order-2" : ""}`}>
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.16em] text-primary">{eyebrow}</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight">{title}</h2>
          <p className="mt-4 text-muted-foreground">{body}</p>
          <div className="mt-6">
            <ProductShot {...fields(aside)} />
          </div>
        </div>
        <ProductShot {...fields(shot)} />
      </div>
    </section>
  );
}
