import type { Metadata } from "next";

import { LaunchDemo } from "@/presentation/launch-demo";
import { ProductShot, SiteFrame } from "@/presentation/site-frame";

export const metadata: Metadata = {
  title: "ATLAS — the operations workspace",
  description:
    "ATLAS keeps one organization's customers, documents, and follow-up in one workspace. The assistant answers from those records. A person approves anything that would leave the building.",
};

const capabilities = [
  ["01", "One customer record", "Companies, conversations, documents, and follow-up stay on the same organization."],
  ["02", "An answer with a source", "The assistant reads that organization's files and CRM, and keeps the passage it used."],
  ["03", "A person still decides", "A reply, a booking, or a CRM change waits until an administrator approves the stored proposal."],
  ["04", "Work you can see", "Agent runs record the tools, the records, and where a run paused."],
  ["05", "Automation with a trail", "A workflow shows the matching path and the otherwise path, then stores which one ran."],
  ["06", "Numbers from the rows", "Overview and analytics count what is already stored. Currencies are not added together."],
];

export default function SitePage() {
  return (
    <SiteFrame>
      <div className="site-wrap site-hero">
        <div>
          <p className="site-kicker">Operations workspace</p>
          <h1>Know the customer. Cite the record. Approve the next step.</h1>
          <p className="site-lede">
            ATLAS is the workspace for one organization&apos;s customers, inbox, documents, and follow-up. The assistant answers from those records. A message, a booking, or a change to the CRM waits until a person approves it.
          </p>
          <div className="site-actions">
            <LaunchDemo label="Launch interactive demo" />
            <a className="site-button-secondary" href="/demo">How the demo works</a>
          </div>
          <p className="site-note">Harbor & Co. is fictional. The pictures are the replacement workspace reading stored rows.</p>
        </div>
        <ProductShot
          src="/portfolio/01-overview.png"
          alt="ATLAS overview for Harbor & Co., with counts taken from stored companies, leads, inquiries, and approvals."
          label="Harbor & Co. · Overview"
          caption="Overview reads the signed-in organization. The figures are stored records, not a designed total."
        />
      </div>

      <section className="site-band" id="product">
        <div className="site-wrap site-section">
          <p className="site-kicker">What the team gets</p>
          <h2>A desk for the work that used to live in three tools.</h2>
          <p className="site-copy">
            Inquiries arrive in one queue. The company file is already there. The assistant can draft from it. Nothing is sent, booked, or written back until someone on the account says so.
          </p>
          <div className="site-grid">
            {capabilities.map(([index, title, body]) => (
              <article className="site-card" key={title}>
                <p className="site-index">{index}</p>
                <strong>{title}</strong>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="site-wrap site-section">
        <div className="site-split">
          <div className="site-copy-block">
            <p className="site-kicker">Customers</p>
            <h2>The account, the thread, and the draft stay together.</h2>
            <p className="site-copy">
              CRM holds the company, the contact, the lead, and the opportunity. Inbox holds the conversation. A reply on screen is a draft until an administrator approves it. The Harbor thread in this picture was not sent.
            </p>
          </div>
          <ProductShot
            src="/portfolio/03-inbox.png"
            alt="ATLAS inbox for Harbor & Co. showing a customer conversation and an unsent draft."
            label="Harbor & Co. · Inbox"
            caption="One organization's queue. Email, WhatsApp, and website chat can open a thread here. Sending still waits for approval."
          />
        </div>
      </section>

      <section className="site-band">
        <div className="site-wrap site-section">
          <div className="site-split reverse">
            <div className="site-copy-block">
              <p className="site-kicker">Knowledge and the assistant</p>
              <h2>Ask the library the company already has.</h2>
              <p className="site-copy">
                Service notes are stored, split, and searched for that organization only. The assistant answers from the passages and CRM rows that qualify, and it stores a refusal when they do not. The engineering rules for that search are in the case study.
              </p>
              <p className="site-copy">
                <a href="/case-study">Read how retrieval and approval work.</a>
              </p>
            </div>
            <ProductShot
              src="/portfolio/04-assistant.png"
              alt="ATLAS assistant in the Harbor & Co. workspace."
              label="Harbor & Co. · Assistant"
              caption="A stored Harbor question. The answer names companies from the workspace and shows the records it used."
            />
          </div>
          <div className="site-grid" style={{ marginTop: 28 }}>
            <ProductShot
              src="/portfolio/05-knowledge.png"
              alt="ATLAS knowledge library for Harbor & Co."
              label="Knowledge"
              caption="Documents belong to one organization. Search does not cross that boundary."
            />
            <ProductShot
              src="/portfolio/02-crm.png"
              alt="ATLAS CRM company list for Harbor & Co."
              label="CRM"
              caption="Companies, contacts, leads, inquiries, opportunities, and tasks stay on the membership."
            />
            <figure className="site-shot">
              <div className="site-phone">
                <img src="/portfolio/11-overview-mobile.png" alt="ATLAS overview on a phone-width screen." width={390} height={844} />
              </div>
              <figcaption className="site-caption">The same workspace at a phone width. Navigation moves into a drawer.</figcaption>
            </figure>
          </div>
        </div>
      </section>

      <section className="site-wrap site-section">
        <div className="site-split">
          <div className="site-copy-block">
            <p className="site-kicker">Automation</p>
            <h2>A visible path, then a recorded run.</h2>
            <p className="site-copy">
              A workflow can match every condition or any condition, then take the matching path or the otherwise path. Runs can pause for a person. Sandbox email stays in the local mailbox. A simulated booking is a row in ATLAS until Google Calendar is connected and an administrator approves it.
            </p>
          </div>
          <ProductShot
            src="/portfolio/07-workflows.png"
            alt="ATLAS workflows for Harbor & Co."
            label="Harbor & Co. · Workflows"
            caption="Definitions and runs are stored. A preview does not send a message."
          />
        </div>
      </section>

      <section className="site-band">
        <div className="site-wrap site-section">
          <div className="site-split reverse">
            <div className="site-copy-block">
              <p className="site-kicker">Transparency</p>
              <h2>See what the agent did, and what is still waiting.</h2>
              <p className="site-copy">
                Agent runs list the stored steps. Approvals show the payload a person can accept or reject. If that payload changes before execution, the write does not happen. The model does not approve itself.
              </p>
            </div>
            <ProductShot
              src="/portfolio/08-agent-runs.png"
              alt="ATLAS agent runs for Harbor & Co."
              label="Harbor & Co. · Agent runs"
              caption="A run is a stored record of tools and pauses. It is not a claim that a message was delivered."
            />
          </div>
          <div style={{ marginTop: 28 }}>
            <ProductShot
              src="/portfolio/06-approvals.png"
              alt="ATLAS approvals for Harbor & Co."
              label="Harbor & Co. · Approvals"
              caption="Pending and historical decisions stay on the organization. Rejecting a reply leaves it unsent."
            />
          </div>
        </div>
      </section>

      <section className="site-wrap site-section" id="reporting">
        <div className="site-split">
          <div className="site-copy-block">
            <p className="site-kicker">Reporting</p>
            <h2>The chart is the table, counted.</h2>
            <p className="site-copy">
              Overview and analytics use the signed-in organization and the period on screen. A conversion rate stays blank when there is nothing to divide. Amounts in different currencies stay apart. Monitoring shows recorded issues. It does not call a provider just to draw the page.
            </p>
          </div>
          <ProductShot
            src="/portfolio/09-analytics.png"
            alt="ATLAS analytics for Harbor & Co."
            label="Harbor & Co. · Analytics"
            caption="Harbor & Co. is a prepared demonstration workspace. The counts come from its stored rows."
          />
        </div>
      </section>

      <section className="site-band" id="integrations">
        <div className="site-wrap site-section">
          <div className="site-split reverse">
            <div className="site-copy-block">
              <p className="site-kicker">Connections</p>
              <h2>Providers are explicit, and a public visitor cannot use them.</h2>
              <p className="site-copy">
                Email, WhatsApp, Resend, Google Calendar, Stripe, and n8n are real integrations in the product. Credentials stay encrypted in the workspace. The public demo refuses live email, live campaigns, live WhatsApp, a payment key, a calendar secret, and an n8n URL. The private Harbor review is a separate database and is not this public site.
              </p>
            </div>
            <ProductShot
              src="/portfolio/10-integrations.png"
              alt="ATLAS integrations for the Harbor & Co. workspace."
              label="Harbor & Co. · Integrations"
              caption="The private Harbor review. Connection state is labeled, secrets are not shown, and a public visitor cannot open these credentials."
            />
          </div>
          <div className="site-grid">
            <article className="site-card">
              <strong>Customer channels</strong>
              <p>Sandbox email by default. Website chat lands in Inbox. WhatsApp and Resend stay behind their own live gates and an approval.</p>
            </article>
            <article className="site-card">
              <strong>Calendar and automation</strong>
              <p>Google Calendar uses a signed-in consent flow. n8n receives a lead event only after the approval point, and the editor is not on the public site.</p>
            </article>
            <article className="site-card">
              <strong>Models and billing</strong>
              <p>Public replies use a local model with a session budget and a site budget. Stripe test prices change the plan only after the provider confirms the subscription.</p>
            </article>
          </div>
        </div>
      </section>

      <section className="site-wrap site-section" id="pricing">
        <p className="site-kicker">Plans</p>
        <h2>The catalog the billing screen uses.</h2>
        <p className="site-copy">
          These are the stored plan limits and the Stripe test prices. They are not a quote for a customer deployment, and a public visitor cannot open checkout.
        </p>
        <div className="site-prices">
          <article className="site-price"><strong>Free</strong><b>$0</b><p>2 seats, 100 assistant requests, 1 GB of files, 2 active workflows.</p></article>
          <article className="site-price"><strong>Starter</strong><b>$19</b><p>5 seats, 1,000 requests, 10 GB, 10 workflows. $190 a year.</p></article>
          <article className="site-price"><strong>Pro</strong><b>$49</b><p>20 seats, 5,000 requests, 100 GB, 50 workflows. $490 a year.</p></article>
          <article className="site-price"><strong>Business</strong><b>$99</b><p>100 seats, 25,000 requests, 1 TB, 200 workflows. $990 a year.</p></article>
        </div>
      </section>

      <section className="site-wrap" style={{ paddingBottom: 72 }}>
        <div className="site-close">
          <div>
            <p className="site-kicker">Interactive demo</p>
            <h2>Open a short-lived Harbor & Co. workspace.</h2>
            <p className="site-copy">No password is published. The session expires, and it is not the private Harbor review or the development workspace.</p>
          </div>
          <LaunchDemo label="Launch interactive demo" />
        </div>
      </section>
    </SiteFrame>
  );
}
