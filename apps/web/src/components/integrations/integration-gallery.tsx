import { Badge } from "@/components/ui/badge";

const gallery = [
  {
    name: "Email",
    purpose: "Deliver approved replies and campaign messages.",
    capabilities: "A workspace can use sandbox mail or a connected relay. This demonstration keeps messages inside the session.",
    status: "Simulated",
  },
  {
    name: "Website chat",
    purpose: "Bring website conversations into Inbox.",
    capabilities: "Sample website messages are included. Connecting a site stays with an administrator.",
    status: "Included",
  },
  {
    name: "WhatsApp",
    purpose: "Receive WhatsApp messages and send approved replies.",
    capabilities: "Supported with a Meta Business account. This demonstration is not connected to WhatsApp.",
    status: "Not connected",
  },
  {
    name: "Google Calendar",
    purpose: "Place approved appointments on a calendar.",
    capabilities: "This demonstration stores the appointment in ATLAS. It does not create a Google event.",
    status: "Simulated",
  },
  {
    name: "n8n",
    purpose: "Continue a lead in an external workflow.",
    capabilities: "A workspace can connect its own n8n instance. This demonstration does not call one.",
    status: "Not connected",
  },
  {
    name: "Language model",
    purpose: "Answer from the records in the workspace.",
    capabilities: "Answers in this demonstration use the included records. A paid model is not called.",
    status: "Demonstration",
  },
  {
    name: "Document search",
    purpose: "Find passages in uploaded company documents.",
    capabilities: "Search stays inside this demonstration. A paid embedding service is not called.",
    status: "Demonstration",
  },
  {
    name: "Stripe",
    purpose: "Manage the workspace subscription.",
    capabilities: "Billing is available on a subscribed workspace. This demonstration does not open a payment account.",
    status: "Not connected",
  },
  {
    name: "Resend",
    purpose: "Send campaigns and record delivery feedback.",
    capabilities: "Optional for live campaigns. Not connected in this demonstration.",
    status: "Not connected",
  },
] as const;

export function IntegrationGallery() {
  return (
    <section className="space-y-4" aria-label="Supported integrations">
      <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
        Credentials and connection settings stay with a workspace administrator. A simulated service is not shown as connected.
      </p>
      <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {gallery.map((item) => (
          <li key={item.name} className="flex min-w-0 flex-col rounded-xl border border-border bg-card p-5">
            <div className="flex items-start justify-between gap-3">
              <h2 className="font-semibold">{item.name}</h2>
              <Badge variant="secondary">{item.status}</Badge>
            </div>
            <p className="mt-3 text-sm leading-6 text-foreground">{item.purpose}</p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.capabilities}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
