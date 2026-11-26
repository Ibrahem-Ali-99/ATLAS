import type { Metadata } from "next";

import { LaunchDemoButton } from "@/components/public/launch-demo-button";
import { DemoTour } from "@/components/public/demo-tour";

export const metadata: Metadata = {
  title: "Demo",
  description:
    "Launch a short-lived Harbor & Co. session in the ATLAS workspace, or walk the captured tour.",
};

const sessionRules = [
  "Launch creates a new organization for this browser. Another visitor cannot read it, and it is not the development workspace.",
  "The session lasts 45 minutes. Restart deletes that organization and opens a fresh Harbor & Co. workspace.",
  "CRM, inbox, knowledge, the assistant, workflows, analytics, and campaigns use the stored demonstration records.",
  "The assistant and document search use a deterministic stand-in. A paid model is not called for this session.",
  "Integration credentials, billing, invitations, outbound messages, and live provider calls are refused.",
  "Each session is limited to 400 requests, 12 assistant replies, 3 documents, and 500 KB of knowledge files.",
];

const guards = [
  "The portfolio command writes only a database named atlas_portfolio. It refuses the development database, the test databases, and production.",
  "It also refuses a public-demo process, live email, live campaigns, live WhatsApp, an n8n URL, a paid chat or embedding key, Stripe, and a Google Calendar client secret.",
  "Documents are written outside the active upload directory. No integration credential is stored.",
  "Fictional CRM rows use demo origin. Several workspace lists default to operational records, so Demo or All records is the view that includes them.",
  "The prepared organization stays on the Free plan until a confirmed subscription says otherwise: 2 seats, 100 assistant requests, 1 GB of knowledge files, and 2 active workflows.",
  "Sign-in stays on the administrator and staff accounts. Launch interactive demo does not use those passwords, and a visitor cannot approve an external action.",
  "External messages, bookings, and CRM changes proposed by the agent still wait for an administrator. A rejected response is not sent. Sandbox email stays on the local mailbox.",
];

export default function DemoPage() {
  return (
    <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-20">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Interactive demo</p>
      <h1 className="mt-4 max-w-3xl text-4xl font-semibold tracking-[-0.03em] text-balance sm:text-5xl sm:leading-[1.08]">
        Explore Harbor & Co. in the application.
      </h1>
      <p className="mt-6 max-w-3xl text-lg leading-8 text-muted-foreground">
        Mina Patel asks about bonded warehousing. Northwind is a second organization used to show that its records stay hidden. Launch interactive demo opens a separate Harbor & Co. workspace in the application. That session expires, restart replaces it, and it does not publish a password. The chapter list below is the redesigned workspace. The assistant chapter is not pictured yet.
      </p>
      <div className="mt-8">
        <LaunchDemoButton size="lg" />
      </div>
      <section className="mt-14" aria-labelledby="session-title">
        <h2 id="session-title" className="text-2xl font-semibold tracking-tight sm:text-3xl">What the launched session can do</h2>
        <ul className="mt-6 grid gap-3 md:grid-cols-2">
          {sessionRules.map((item) => (
            <li key={item} className="rounded-2xl border border-border bg-card p-5 text-sm leading-6">
              {item}
            </li>
          ))}
        </ul>
      </section>
      <section className="mt-14" aria-labelledby="sandbox-title">
        <h2 id="sandbox-title" className="text-2xl font-semibold tracking-tight sm:text-3xl">Separate portfolio database</h2>
        <ul className="mt-6 grid gap-3 md:grid-cols-2">
          {guards.map((item) => (
            <li key={item} className="rounded-2xl border border-border bg-card p-5 text-sm leading-6">
              {item}
            </li>
          ))}
        </ul>
      </section>
      <section className="mt-16" aria-labelledby="tour-title">
        <h2 id="tour-title" className="text-2xl font-semibold tracking-tight sm:text-3xl">Product tour</h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">
          Choose a chapter. The pictures are 1440×900 captures of the redesigned Harbor & Co. workspace. The assistant chapter waits for the retrieval work and is not pictured.
        </p>
        <div className="mt-8">
          <DemoTour />
        </div>
      </section>
    </div>
  );
}
