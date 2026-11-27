import type { Metadata } from "next";

import { LaunchDemo } from "@/presentation/launch-demo";
import { SiteFrame } from "@/presentation/site-frame";

export const metadata: Metadata = {
  title: "Demo · ATLAS",
  description: "What a public ATLAS visitor can open, and what stays refused.",
};

const allowed = [
  "Overview, CRM, inbox, knowledge, the assistant, workflows, analytics, campaigns, and approvals for a fictional Harbor & Co. organization.",
  "A new company, a knowledge note inside the visitor allowance, and an assistant question inside the reply budget.",
  "Rejecting a prepared customer message, and approving a prepared note that only changes a lead record.",
];

const refused = [
  "Live email, live campaigns, live WhatsApp, Google Calendar connect, n8n, billing checkout, invitations, and webhook keys.",
  "Executing a customer message or a new appointment. The API returns a refusal and does not stage the send.",
  "The administrator password, the staff password, the private Harbor review database, and any other organization's rows.",
];

export default function DemoPage() {
  return (
    <SiteFrame>
      <article className="site-prose">
        <p className="site-kicker">Interactive demo</p>
        <h1>A private Harbor & Co. for this browser.</h1>
        <p>
          Launch creates a short-lived organization, sets an HttpOnly cookie, and opens the workspace. The organization expires after 45 minutes. Restart replaces it. The address cannot sign in or reset a password. No staff password is on this site.
        </p>
        <div className="site-actions">
          <LaunchDemo label="Launch interactive demo" />
          <a className="site-button-secondary" href="/case-study">Read the case study</a>
        </div>

        <h2>What you can do</h2>
        <ul>
          {allowed.map((item) => <li key={item}>{item}</li>)}
        </ul>

        <h2>What stays closed</h2>
        <ul>
          {refused.map((item) => <li key={item}>{item}</li>)}
        </ul>

        <h2>The assistant on this site</h2>
        <p>
          A visitor question can call a local language model when the public deployment has that switch on. Each browser session has a reply budget, the whole site has a shared budget, and messages are rate limited. A message that tries to override those instructions is rejected. Document search for a visitor still uses the built-in stand-in, so a public question is not a paid embedding call.
        </p>
        <p>
          If the local model is not answering, the workspace says so. The product does not invent a successful reply. The private Harbor review, where connected providers are demonstrated, is a different database and is not opened by this button.
        </p>

        <h2>Limits on one session</h2>
        <ul>
          <li>400 requests, 12 assistant replies, 3 uploaded documents, and 500 KB of knowledge files.</li>
          <li>Prepared demonstration files do not count toward that allowance. A file you upload does.</li>
          <li>At most 40 visitor organizations exist at once. A later launch removes expired ones. Cleanup only deletes organizations whose slug starts with <code>harbor-visitor-</code>.</li>
          <li>Login failures are limited per email and per client address inside the one API process. Do not run a second API container. The counters are not shared.</li>
        </ul>
      </article>
    </SiteFrame>
  );
}
